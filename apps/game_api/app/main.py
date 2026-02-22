from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from apps.game_api.app.config import settings
from apps.game_api.app.persistence import WorldRepository
from apps.game_api.app.services.bootstrap_preview import build_world_bootstrap_preview
from apps.game_api.app.services.intent_analysis_preview import analyze_player_input_preview
from apps.game_api.app.services.narration_preview import build_narrative_from_resolution
from ls_rules_engine import RulesEngine
from ls_shared_schemas.character import CharacterState
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.turns import (
    NarrativeEnvelope,
    PersistedTurnRecord,
    TurnIntent,
    TurnResolution,
    TurnRunRequest,
    TurnRunResponse,
)
from ls_shared_schemas.world import WorldBootstrapRequest, WorldBootstrapResult, WorldSessionResponse


class TurnResolvePreviewRequest(BaseModel):
    intent: TurnIntent
    character_state: CharacterState
    inventory: list[InventoryItemInstance] = Field(default_factory=list)


class TurnAnalyzePreviewRequest(BaseModel):
    player_input: str = Field(min_length=1, max_length=2000)


engine = RulesEngine()
world_repository = WorldRepository(settings.database_path)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    world_repository.initialize()
    app_instance.state.world_repository = world_repository
    yield


app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)


def _get_world_repository(request: Request) -> WorldRepository:
    repository = getattr(request.app.state, "world_repository", None)
    if repository is None:
        raise RuntimeError("World repository is not configured.")
    return repository


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "greenfield-game-api",
        "environment": settings.environment,
        "public_game_domain": settings.public_game_domain,
    }


@app.post("/v1/worlds/bootstrap/preview", response_model=WorldBootstrapResult)
def world_bootstrap_preview(request: WorldBootstrapRequest) -> WorldBootstrapResult:
    return build_world_bootstrap_preview(request)


@app.post("/v1/worlds/bootstrap", response_model=WorldSessionResponse)
def world_bootstrap_create(request: WorldBootstrapRequest, fastapi_request: Request) -> WorldSessionResponse:
    bootstrap_result = build_world_bootstrap_preview(request)
    repository = _get_world_repository(fastapi_request)
    return repository.create_world_session(request=request, bootstrap=bootstrap_result)


@app.get("/v1/worlds/{world_id}", response_model=WorldSessionResponse)
def get_world_session(world_id: str, fastapi_request: Request) -> WorldSessionResponse:
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    return session


@app.post("/v1/worlds/{world_id}/turns/analyze/preview", response_model=TurnIntent)
def analyze_turn_preview(world_id: str, request: TurnAnalyzePreviewRequest, fastapi_request: Request) -> TurnIntent:
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    return analyze_player_input_preview(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        player_input=request.player_input,
        inventory=session.inventory,
    )


@app.post("/v1/turns/resolve/preview", response_model=TurnResolution)
def resolve_turn_preview(request: TurnResolvePreviewRequest) -> TurnResolution:
    return engine.resolve(intent=request.intent, character_state=request.character_state, inventory=request.inventory)


@app.post("/v1/turns/narrate/preview", response_model=NarrativeEnvelope)
def narrate_turn_preview(resolution: TurnResolution) -> NarrativeEnvelope:
    return build_narrative_from_resolution(resolution)


@app.post("/v1/worlds/{world_id}/turns/run", response_model=TurnRunResponse)
def run_turn(world_id: str, request: TurnRunRequest, fastapi_request: Request) -> TurnRunResponse:
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")

    intent = analyze_player_input_preview(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        player_input=request.player_input,
        inventory=session.inventory,
    )
    resolution = engine.resolve(
        intent=intent,
        character_state=session.character_state,
        inventory=session.inventory,
    )
    narrative = build_narrative_from_resolution(resolution)
    turn_record, journal_entries = repository.save_turn_run(
        world_id=world_id,
        intent=intent,
        resolution=resolution,
        narrative=narrative,
    )
    return TurnRunResponse(
        turn=turn_record,
        resulting_character_state=resolution.resulting_character_state,
        resulting_inventory=resolution.resulting_inventory,
        journal_entry_ids=[entry.journal_entry_id for entry in journal_entries],
    )


@app.get("/v1/worlds/{world_id}/turns", response_model=list[PersistedTurnRecord])
def list_world_turns(world_id: str, fastapi_request: Request, limit: int = 50) -> list[PersistedTurnRecord]:
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    return repository.list_turns(world_id=world_id, limit=limit)
