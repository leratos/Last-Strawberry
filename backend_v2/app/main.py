import logging
from contextvars import ContextVar
from functools import lru_cache
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status

from backend_v2.app.auth import AuthUser, create_access_token, get_current_user
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
from backend_v2.app.services.embeddings import EmbeddingsProvider, HashEmbeddingsProvider, NoopEmbeddingsProvider
from backend_v2.app.services.memory import MemoryWritePolicy
from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.orchestrator import GameOrchestrator
from backend_v2.app.services.retrieval import (
    HybridMemoryRetriever,
    LexicalMemoryRetriever,
    MemoryRetriever,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
REQUEST_ID_HEADER = "X-Request-ID"
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

app = FastAPI(
    title="Last Strawberry Backend V2",
    version="2.0.0-alpha",
    description="OpenRouter-first restart backend for game orchestration.",
)


def get_request_id() -> str:
    return _request_id_ctx.get()


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
    token = _request_id_ctx.set(request_id)
    started_at = perf_counter()
    status_code: str | int = "error"
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        logger.info(
            "request_id=%s method=%s path=%s status=%s latency_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            status_code,
            (perf_counter() - started_at) * 1000,
        )
        _request_id_ctx.reset(token)


@lru_cache
def get_orchestrator() -> GameOrchestrator:
    settings = get_settings()
    provider = OpenRouterProvider(settings)
    return GameOrchestrator(provider=provider, settings=settings)


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


def _assert_world_access(repository: SQLiteRepository, world_id: int, user_id: int) -> None:
    world = repository.get_world(world_id)
    if world is None:
        raise HTTPException(status_code=404, detail="World not found.")
    if int(world["owner_id"]) != user_id:
        raise HTTPException(status_code=403, detail="World access forbidden.")


@app.post("/v2/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest, settings: Settings = Depends(get_settings)) -> LoginResponse:
    token = create_access_token(user_id=request.user_id, username=request.username, settings=settings)
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
    try:
        _assert_world_access(repository, request.world_id, current_user.user_id)
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
            retrieval_result.stats.strategy,
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
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PersistenceError as exc:
        logger.exception("request_id=%s Persistence error while saving turn.", get_request_id())
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
    except Exception as exc:
        logger.exception("request_id=%s Unexpected v2 turn processing error.", get_request_id())
        raise HTTPException(status_code=500, detail="Internal v2 error.") from exc


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
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
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
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
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
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
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
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
    return [MemoryItemResponse.model_validate(item) for item in memory_items]


@app.get("/v2/metrics/retrieval")
async def get_retrieval_metrics(current_user: AuthUser = Depends(get_current_user)) -> dict:
    _ = current_user
    collector = get_retrieval_metrics_collector()
    return collector.snapshot()


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "last-strawberry-backend-v2", "docs": "/docs", "health": "/v2/health"}
