import logging
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query, status

from backend_v2.app.config import get_settings
from backend_v2.app.models import (
    HealthResponse,
    TurnRecordResponse,
    TurnRequest,
    TurnResponse,
    WorldCreateRequest,
    WorldResponse,
)
from backend_v2.app.persistence import PersistenceError, SQLiteRepository
from backend_v2.app.providers.base import ProviderError
from backend_v2.app.providers.openrouter import OpenRouterProvider
from backend_v2.app.services.orchestrator import GameOrchestrator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI(
    title="Last Strawberry Backend V2",
    version="2.0.0-alpha",
    description="OpenRouter-first restart backend for game orchestration.",
)


@lru_cache
def get_orchestrator() -> GameOrchestrator:
    settings = get_settings()
    provider = OpenRouterProvider(settings)
    return GameOrchestrator(provider=provider, settings=settings)


@lru_cache
def get_repository() -> SQLiteRepository:
    settings = get_settings()
    return SQLiteRepository(database_url=settings.database_url, auto_init=settings.database_auto_init)


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
async def run_turn(request: TurnRequest) -> TurnResponse:
    orchestrator = get_orchestrator()
    repository = get_repository()
    try:
        response = await orchestrator.run_turn(request)
        repository.save_turn(request, response)
        return response
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except PersistenceError as exc:
        logger.exception("Persistence error while saving turn.")
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
    except Exception as exc:
        logger.exception("Unexpected v2 turn processing error.")
        raise HTTPException(status_code=500, detail="Internal v2 error.") from exc


@app.post("/v2/worlds", response_model=WorldResponse, status_code=status.HTTP_201_CREATED)
async def create_world(request: WorldCreateRequest) -> WorldResponse:
    repository = get_repository()
    try:
        world = repository.create_world(
            owner_id=request.owner_id,
            name=request.name,
            description=request.description,
        )
    except PersistenceError as exc:
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
    return WorldResponse.model_validate(world)


@app.get("/v2/worlds/{world_id}", response_model=WorldResponse)
async def get_world(world_id: int) -> WorldResponse:
    repository = get_repository()
    try:
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
) -> list[TurnRecordResponse]:
    repository = get_repository()
    try:
        turns = repository.list_turns(world_id=world_id, limit=limit)
    except PersistenceError as exc:
        raise HTTPException(status_code=500, detail=f"Persistence error: {exc}") from exc
    return [TurnRecordResponse.model_validate(turn) for turn in turns]


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": "last-strawberry-backend-v2", "docs": "/docs", "health": "/v2/health"}
