import logging
from contextvars import ContextVar
from functools import lru_cache
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from backend_v2.app.auth import AuthUser, create_access_token, decode_access_token, get_current_user
from backend_v2.app.config import Settings, get_settings
from backend_v2.app.models import (
    HealthResponse,
    LoginRequest,
    LoginResponse,
    MemoryItemResponse,
    TurnRecordResponse,
    TurnRequest,
    TurnResponse,
    WorldCreateRequest,
    WorldResponse,
)
from backend_v2.app.persistence import PersistenceError, SQLiteRepository
from backend_v2.app.providers.embeddings_openrouter import OpenRouterEmbeddingsProvider
from backend_v2.app.providers.base import ProviderError
from backend_v2.app.providers.openrouter import OpenRouterProvider
from backend_v2.app.security import parse_content_length_header, redact_sensitive_text, sanitize_for_log
from backend_v2.app.services.embeddings import EmbeddingsProvider, HashEmbeddingsProvider, NoopEmbeddingsProvider
from backend_v2.app.services.memory import MemoryWritePolicy
from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.metrics_prometheus import snapshot_to_prometheus
from backend_v2.app.services.orchestrator import GameOrchestrator
from backend_v2.app.services.rate_limit import SlidingWindowRateLimiter
from backend_v2.app.services.retrieval import (
    HybridMemoryRetriever,
    LexicalMemoryRetriever,
    MemoryRetriever,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
REQUEST_ID_HEADER = "X-Request-ID"
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
ERROR_CATEGORY_HEADER = "X-LS-Error-Category"
BODY_LIMIT_METHODS = {"POST", "PUT", "PATCH"}

app = FastAPI(
    title="Last Strawberry Backend V2",
    version="2.0.0-alpha",
    description="OpenRouter-first restart backend for game orchestration.",
)


def get_request_id() -> str:
    return _request_id_ctx.get()


async def _maybe_reject_request_body(request: Request, max_body_bytes: int) -> Response | None:
    if request.method.upper() not in BODY_LIMIT_METHODS:
        return None

    try:
        declared_length = parse_content_length_header(request.headers.get("content-length"))
    except ValueError:
        return JSONResponse(
            status_code=400,
            content={"detail": "Invalid Content-Length header."},
            headers={ERROR_CATEGORY_HEADER: "security"},
        )

    if declared_length is not None and declared_length > max_body_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large."},
            headers={ERROR_CATEGORY_HEADER: "security"},
        )

    body = await request.body()
    if len(body) > max_body_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": "Request body too large."},
            headers={ERROR_CATEGORY_HEADER: "security"},
        )

    async def receive() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = receive  # type: ignore[attr-defined]
    return None


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
    token = _request_id_ctx.set(request_id)
    started_at = perf_counter()
    status_code: str | int = "error"
    response = None
    try:
        settings = get_settings()
        rejected = await _maybe_reject_request_body(request, settings.max_request_body_bytes)
        response = rejected if rejected is not None else await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        if isinstance(status_code, int) and response is not None:
            collector = get_retrieval_metrics_collector()
            collector.record_http_status(status_code)

            response_category = response.headers.get(ERROR_CATEGORY_HEADER)
            if response_category:
                collector.record_error_category(response_category)
                del response.headers[ERROR_CATEGORY_HEADER]
            elif status_code in (401, 403):
                collector.record_error_category("auth")
            elif status_code == 429:
                collector.record_error_category("rate_limit")
            elif status_code == 413:
                collector.record_error_category("security")
            elif status_code == 502:
                collector.record_error_category("provider")
            elif 500 <= status_code <= 599:
                collector.record_error_category("server")

            request_path = str(request.url.path)
            if status_code == 401 and request_path.startswith("/v2/") and request_path != "/v2/auth/login":
                collector.record_audit_event("auth_failed")
            elif status_code == 403:
                collector.record_audit_event("auth_forbidden")

        logger.info(
            "request_id=%s method=%s path=%s status=%s latency_ms=%.2f",
            sanitize_for_log(request_id, max_length=64),
            sanitize_for_log(request.method, max_length=16),
            sanitize_for_log(request.url.path, max_length=256),
            status_code,
            (perf_counter() - started_at) * 1000,
        )
        _request_id_ctx.reset(token)


@lru_cache
def get_orchestrator() -> GameOrchestrator:
    settings = get_settings()
    provider = OpenRouterProvider(settings)
    return GameOrchestrator(
        provider=provider,
        settings=settings,
        metrics_collector=get_retrieval_metrics_collector(),
    )


@lru_cache
def get_repository() -> SQLiteRepository:
    settings = get_settings()
    return SQLiteRepository(database_url=settings.database_url, auto_init=settings.database_auto_init)


@lru_cache
def get_memory_policy() -> MemoryWritePolicy:
    settings = get_settings()
    return MemoryWritePolicy(min_importance=settings.memory_min_importance)


@lru_cache
def get_embeddings_provider() -> EmbeddingsProvider:
    settings = get_settings()
    if settings.embeddings_provider == "none":
        return NoopEmbeddingsProvider(dimensions=settings.embeddings_dimensions)
    if settings.embeddings_provider == "openrouter":
        if not settings.openrouter_api_key:
            logger.warning("LS_EMBEDDINGS_PROVIDER=openrouter but no API key configured. Falling back to hash embeddings.")
            return HashEmbeddingsProvider(dimensions=settings.embeddings_dimensions)
        return OpenRouterEmbeddingsProvider(settings=settings)
    return HashEmbeddingsProvider(dimensions=settings.embeddings_dimensions)


@lru_cache
def get_memory_retriever() -> MemoryRetriever:
    settings = get_settings()
    if settings.memory_retrieval_strategy == "lexical":
        return LexicalMemoryRetriever()
    return HybridMemoryRetriever(
        embeddings_provider=get_embeddings_provider(),
        vector_weight=settings.retrieval_vector_weight,
        semantic_min_similarity=settings.retrieval_semantic_min_similarity,
    )


@lru_cache
def get_retrieval_metrics_collector() -> RetrievalMetricsCollector:
    return RetrievalMetricsCollector()


@lru_cache
def get_turn_rate_limiter() -> SlidingWindowRateLimiter:
    settings = get_settings()
    return SlidingWindowRateLimiter(
        limit=settings.turn_rate_limit_requests,
        window_seconds=settings.turn_rate_limit_window_seconds,
        enabled=settings.turn_rate_limit_enabled,
    )


@lru_cache
def get_login_rate_limiter() -> SlidingWindowRateLimiter:
    settings = get_settings()
    return SlidingWindowRateLimiter(
        limit=settings.login_rate_limit_requests,
        window_seconds=settings.login_rate_limit_window_seconds,
        enabled=settings.login_rate_limit_enabled,
    )


def _assert_world_access(repository: SQLiteRepository, world_id: int, user_id: int) -> None:
    world = repository.get_world(world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="World not found.")
    if int(world["owner_id"]) != user_id:
        raise HTTPException(status_code=403, detail="World access forbidden.")


@app.post("/v2/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, request: Request, settings: Settings = Depends(get_settings)) -> LoginResponse:
    login_limiter = get_login_rate_limiter()
    client_host = request.client.host if request.client and request.client.host else "unknown"
    decision = login_limiter.check(f"login_ip:{client_host}")
    if not decision.allowed:
        retry_after = decision.retry_after_seconds or 1
        get_retrieval_metrics_collector().record_audit_event("auth_login_rate_limited")
        raise HTTPException(
            status_code=429,
            detail="Login rate limit exceeded.",
            headers={"Retry-After": str(retry_after), ERROR_CATEGORY_HEADER: "rate_limit"},
        )

    token = create_access_token(user_id=payload.user_id, username=payload.username, settings=settings)
    get_retrieval_metrics_collector().record_audit_event("auth_login_success")
    return LoginResponse(access_token=token, expires_in_seconds=settings.jwt_expire_minutes * 60)


@app.get("/v2/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok" if settings.openrouter_api_key else "degraded",
        provider="openrouter",
        configured_models={
            "analysis": settings.analysis_model,
            "narrative": settings.narrative_model,
        },
    )


@app.post("/v2/game/turn", response_model=TurnResponse)
async def run_turn(
    request: TurnRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> TurnResponse:
    settings = get_settings()
    orchestrator = get_orchestrator()
    repository = get_repository()
    memory_policy = get_memory_policy()
    memory_retriever = get_memory_retriever()
    metrics_collector = get_retrieval_metrics_collector()
    rate_limiter = get_turn_rate_limiter()
    try:
        _assert_world_access(repository, request.world_id, current_user.user_id)
        limit_check = rate_limiter.check(f"user:{current_user.user_id}")
        if not limit_check.allowed:
            retry_after = limit_check.retry_after_seconds or 1
            metrics_collector.record_audit_event("rate_limit_exceeded")
            logger.warning(
                "request_id=%s rate_limit_exceeded user_id=%s retry_after_s=%s",
                get_request_id(),
                current_user.user_id,
                retry_after,
            )
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded.",
                headers={"Retry-After": str(retry_after), ERROR_CATEGORY_HEADER: "rate_limit"},
            )
        recent_events = repository.list_recent_turn_events(request.world_id, limit=3)
        retrieval_started_at = perf_counter()
        retrieval_result = memory_retriever.retrieve(
            repository=repository,
            world_id=request.world_id,
            query=request.player_command,
            limit=settings.memory_context_limit,
            min_importance=settings.memory_min_importance,
        )
        retrieval_latency_ms = (perf_counter() - retrieval_started_at) * 1000
        metrics_collector.record(retrieval_result.stats, retrieval_latency_ms)
        memory_matches = retrieval_result.items
        logger.info(
            "request_id=%s retrieval world_id=%s user_id=%s strategy=%s scanned=%s lexical_hits=%s semantic_hits=%s cache_hits=%s cache_misses=%s returned=%s fallback=%s latency_ms=%.2f",
            get_request_id(),
            request.world_id,
            current_user.user_id,
            sanitize_for_log(retrieval_result.stats.strategy),
            retrieval_result.stats.candidates_scanned,
            retrieval_result.stats.lexical_hits,
            retrieval_result.stats.semantic_hits,
            retrieval_result.stats.cache_hits,
            retrieval_result.stats.cache_misses,
            retrieval_result.stats.returned,
            retrieval_result.stats.fallback_used,
            retrieval_latency_ms,
        )
        memory_context = [f"{item['memory_type']}: {item['content']}" for item in memory_matches]

        enriched_request = request.model_copy(
            update={
                "recent_events": recent_events or request.recent_events,
                "memory_context": memory_context,
            }
        )
        response = await orchestrator.run_turn(enriched_request)
        saved_turn = repository.save_turn(enriched_request, response)
        memory_items = memory_policy.build_items(enriched_request, response)
        repository.save_memory_items(
            world_id=request.world_id,
            items=memory_items,
            source_turn_id=int(saved_turn["id"]),
        )
        return response
    except HTTPException:
        raise
    except ProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail=redact_sensitive_text(exc, max_length=280),
            headers={ERROR_CATEGORY_HEADER: "provider"},
        ) from exc
    except PersistenceError as exc:
        logger.exception("request_id=%s Persistence error while saving turn.", get_request_id())
        raise HTTPException(
            status_code=500,
            detail="Persistence error.",
            headers={ERROR_CATEGORY_HEADER: "persistence"},
        ) from exc
    except Exception as exc:
        logger.exception("request_id=%s Unexpected v2 turn processing error.", get_request_id())
        raise HTTPException(
            status_code=500,
            detail="Internal v2 error.",
            headers={ERROR_CATEGORY_HEADER: "server"},
        ) from exc


@app.post("/v2/worlds", response_model=WorldResponse, status_code=status.HTTP_201_CREATED)
async def create_world(
    request: WorldCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
) -> WorldResponse:
    repository = get_repository()
    try:
        world = repository.create_world(
            owner_id=current_user.user_id,
            name=request.name,
            description=request.description,
        )
    except PersistenceError as exc:
        raise HTTPException(
            status_code=500,
            detail="Persistence error.",
            headers={ERROR_CATEGORY_HEADER: "persistence"},
        ) from exc
    return WorldResponse.model_validate(world)


@app.get("/v2/worlds/{world_id}", response_model=WorldResponse)
async def get_world(
    world_id: int,
    current_user: AuthUser = Depends(get_current_user),
) -> WorldResponse:
    repository = get_repository()
    try:
        _assert_world_access(repository, world_id, current_user.user_id)
        world = repository.get_world(world_id)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=500,
            detail="Persistence error.",
            headers={ERROR_CATEGORY_HEADER: "persistence"},
        ) from exc
    if world is None:
        raise HTTPException(status_code=404, detail="World not found.")
    return WorldResponse.model_validate(world)


@app.get("/v2/worlds/{world_id}/turns", response_model=list[TurnRecordResponse])
async def list_world_turns(
    world_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: AuthUser = Depends(get_current_user),
) -> list[TurnRecordResponse]:
    repository = get_repository()
    try:
        _assert_world_access(repository, world_id, current_user.user_id)
        turns = repository.list_turns(world_id=world_id, limit=limit)
    except PersistenceError as exc:
        raise HTTPException(
            status_code=500,
            detail="Persistence error.",
            headers={ERROR_CATEGORY_HEADER: "persistence"},
        ) from exc
    return [TurnRecordResponse.model_validate(turn) for turn in turns]


@app.get("/v2/worlds/{world_id}/memory", response_model=list[MemoryItemResponse])
async def list_world_memory(
    world_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    min_importance: float = Query(default=0.0, ge=0.0, le=1.0),
    current_user: AuthUser = Depends(get_current_user),
) -> list[MemoryItemResponse]:
    repository = get_repository()
    try:
        _assert_world_access(repository, world_id, current_user.user_id)
        memory_items = repository.list_memory_items(
            world_id=world_id,
            limit=limit,
            min_importance=min_importance,
        )
    except PersistenceError as exc:
        raise HTTPException(
            status_code=500,
            detail="Persistence error.",
            headers={ERROR_CATEGORY_HEADER: "persistence"},
        ) from exc
    return [MemoryItemResponse.model_validate(item) for item in memory_items]


@app.get("/v2/metrics/retrieval")
async def get_retrieval_metrics(current_user: AuthUser = Depends(get_current_user)) -> dict:
    _ = current_user
    collector = get_retrieval_metrics_collector()
    return collector.snapshot()


@app.get("/v2/metrics/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics(
    request: Request,
) -> PlainTextResponse:
    settings = get_settings()
    if settings.metrics_api_key:
        provided_key = request.headers.get(settings.metrics_api_key_header)
        if provided_key != settings.metrics_api_key:
            raise HTTPException(status_code=401, detail="Missing or invalid metrics API key.")
    else:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing bearer token.")
        token = auth_header.split(" ", 1)[1].strip()
        decode_access_token(token, settings)

    collector = get_retrieval_metrics_collector()
    payload = snapshot_to_prometheus(collector.snapshot())
    return PlainTextResponse(content=payload, media_type="text/plain; version=0.0.4")


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "last-strawberry-backend-v2", "docs": "/docs", "health": "/v2/health"}
