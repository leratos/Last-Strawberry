from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from apps.game_api.app.config import settings
from apps.game_api.app.persistence import WorldRepository
from apps.game_api.app.services.bootstrap_preview import build_world_bootstrap_preview
from apps.game_api.app.services.context_assembly import assemble_game_context
from apps.game_api.app.services.llm_runtime import build_llm_runtime
from ls_rules_engine import RulesEngine
from ls_shared_schemas.character import CharacterState
from ls_shared_schemas.game_context import GameContextResponse
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.npc_memory import NPCMemoryBundle, NPCProfile
from ls_shared_schemas.turns import (
    NarrativeEnvelope,
    PersistedTurnRecord,
    TurnIntent,
    TurnIntentAction,
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


class DevSpawnNpcRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="npc", min_length=1, max_length=120)
    faction: str | None = Field(default=None, max_length=120)
    location_name: str | None = Field(default=None, max_length=120)
    scene_zone_id: str | None = Field(default=None, max_length=120)
    scene_zone_name: str | None = Field(default=None, max_length=120)
    personality_tags: list[str] = Field(default_factory=list)
    stats: dict[str, int | float | str] = Field(default_factory=dict)
    npc_id: str | None = Field(default=None, max_length=120)
    standing_for_player: int | None = Field(default=None, ge=-100, le=100)
    revealed_to_player: bool = True


engine = RulesEngine()
world_repository = WorldRepository(settings.database_path)
llm_runtime = build_llm_runtime(settings)


@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    world_repository.initialize()
    app_instance.state.world_repository = world_repository
    yield


app = FastAPI(title=settings.api_title, version=settings.api_version, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_allowed_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_world_repository(request: Request) -> WorldRepository:
    repository = getattr(request.app.state, "world_repository", None)
    if repository is None:
        raise RuntimeError("World repository is not configured.")
    return repository


def _assemble_context_for_world(
    *,
    repository: WorldRepository,
    world_id: str,
    player_input: str | None = None,
    journal_limit: int = 20,
    turn_limit: int = 10,
    memory_per_npc: int = 3,
) -> GameContextResponse:
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    turns = repository.list_turns(world_id=world_id, limit=max(1, turn_limit))
    npc_memory = repository.list_npc_memory_bundles(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        limit_memories_per_npc=max(1, memory_per_npc),
    )
    context = assemble_game_context(
        world=session,
        turns=turns,
        npc_memory=npc_memory,
        retrieval_player_input=player_input,
        journal_limit=journal_limit,
        turn_limit=turn_limit,
        memory_per_npc=memory_per_npc,
    )
    hidden_npc_count = repository.count_hidden_npcs_in_location(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        location_name=session.character_state.location_name,
    )
    if hidden_npc_count > 0:
        context.retrieval_notes.append(
            f"Es gibt {hidden_npc_count} unbekannte Praesenz(en) an diesem Ort. Umsehen/Untersuchen kann neue Ziele aufdecken."
        )
    return context


@app.get("/health")
def health() -> dict[str, str]:
    llm_status = llm_runtime.status()
    return {
        "status": "ok",
        "service": "greenfield-game-api",
        "environment": settings.environment,
        "public_game_domain": settings.public_game_domain,
        "llm_mode": llm_status.mode,
        "llm_fallback_to_preview": str(llm_status.fallback_to_preview).lower(),
        "intent_provider": llm_status.intent_provider,
        "narration_provider": llm_status.narration_provider,
        "openrouter_configured": str(llm_status.openrouter_configured).lower(),
        "openrouter_intent_model": llm_status.intent_model,
        "openrouter_narrator_model": llm_status.narrator_model,
        "openrouter_json_repair_attempts": str(settings.openrouter_json_repair_attempts),
    }


@app.get("/v1/worlds/{world_id}/context", response_model=GameContextResponse)
def get_world_context(
    world_id: str,
    fastapi_request: Request,
    player_input: str | None = None,
    journal_limit: int = 20,
    turn_limit: int = 10,
    memory_per_npc: int = 3,
) -> GameContextResponse:
    repository = _get_world_repository(fastapi_request)
    return _assemble_context_for_world(
        repository=repository,
        world_id=world_id,
        player_input=player_input,
        journal_limit=journal_limit,
        turn_limit=turn_limit,
        memory_per_npc=memory_per_npc,
    )


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


@app.post("/v1/devtest/worlds/{world_id}/npcs/spawn", response_model=NPCProfile)
def devtest_spawn_npc(world_id: str, request: DevSpawnNpcRequest, fastapi_request: Request) -> NPCProfile:
    if settings.environment.lower() == "production":
        raise HTTPException(status_code=403, detail="Dev/Test NPC spawn endpoint is disabled in production.")

    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")

    raw_name = request.name.strip()
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in raw_name)
    slug = "-".join(part for part in slug.split("-") if part)[:40] or "npc"
    npc_id = (request.npc_id or f"npc-dev-{slug}").strip()
    profile = NPCProfile(
        npc_id=npc_id,
        name=raw_name,
        role=request.role.strip(),
        faction=request.faction.strip() if request.faction else None,
        location_name=(request.location_name or session.character_state.location_name).strip(),
        scene_zone_id=request.scene_zone_id.strip() if request.scene_zone_id else None,
        scene_zone_name=request.scene_zone_name.strip() if request.scene_zone_name else None,
        personality_tags=[tag.strip() for tag in request.personality_tags if str(tag).strip()],
        stats=dict(request.stats),
    )
    try:
        return repository.spawn_npc_for_devtest(
            world_id=world_id,
            profile=profile,
            standing_for_player=request.standing_for_player,
            revealed_to_player=request.revealed_to_player,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/worlds/{world_id}/turns/analyze/preview", response_model=TurnIntent)
def analyze_turn_preview(world_id: str, request: TurnAnalyzePreviewRequest, fastapi_request: Request) -> TurnIntent:
    repository = _get_world_repository(fastapi_request)
    context = _assemble_context_for_world(
        repository=repository,
        world_id=world_id,
        player_input=request.player_input,
        turn_limit=5,
        memory_per_npc=3,
    )
    session = context.world
    npc_refs = [
        {
            "ref_id": entry.ref_id,
            "name": entry.name,
            "role": entry.role,
            "location_name": entry.location_name,
            "scene_zone_id": entry.scene_zone_id,
            "scene_zone_name": entry.scene_zone_name,
            "distance_band_to_player": entry.distance_band_to_player,
        }
        for entry in context.target_catalog.npcs
    ]
    location_refs = [
        {
            "ref_id": entry.ref_id,
            "name": entry.name,
            "location_name": entry.location_name,
            "scene_zone_id": entry.scene_zone_id,
            "scene_zone_name": entry.scene_zone_name,
            "distance_band_to_player": entry.distance_band_to_player,
        }
        for entry in context.target_catalog.locations
    ]
    item_refs = [
        {"ref_id": entry.ref_id, "name": entry.name}
        for entry in context.target_catalog.items
    ]
    return llm_runtime.analyze_intent(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        player_input=request.player_input,
        inventory=session.inventory,
        known_npc_names=[entry.bundle.profile.name for entry in context.npc_memory],
        known_locations=[session.character_state.location_name, session.world_seed.start_location_name],
        known_npc_refs=npc_refs,
        known_location_refs=location_refs,
        known_item_refs=item_refs,
        context=context,
    )


@app.post("/v1/turns/resolve/preview", response_model=TurnResolution)
def resolve_turn_preview(request: TurnResolvePreviewRequest) -> TurnResolution:
    return engine.resolve(intent=request.intent, character_state=request.character_state, inventory=request.inventory)


@app.post("/v1/turns/narrate/preview", response_model=NarrativeEnvelope)
def narrate_turn_preview(resolution: TurnResolution) -> NarrativeEnvelope:
    return llm_runtime.narrate(resolution=resolution, context_before=None)


@app.post("/v1/worlds/{world_id}/turns/run", response_model=TurnRunResponse)
def run_turn(world_id: str, request: TurnRunRequest, fastapi_request: Request) -> TurnRunResponse:
    repository = _get_world_repository(fastapi_request)
    context_before = _assemble_context_for_world(
        repository=repository,
        world_id=world_id,
        player_input=request.player_input,
        turn_limit=8,
        memory_per_npc=4,
    )
    session = context_before.world

    known_npc_names = [entry.bundle.profile.name for entry in context_before.npc_memory]
    known_locations = [session.character_state.location_name, session.world_seed.start_location_name]
    known_npc_refs = [
        {
            "ref_id": entry.ref_id,
            "name": entry.name,
            "role": entry.role,
            "location_name": entry.location_name,
            "scene_zone_id": entry.scene_zone_id,
            "scene_zone_name": entry.scene_zone_name,
            "distance_band_to_player": entry.distance_band_to_player,
        }
        for entry in context_before.target_catalog.npcs
    ]
    known_location_refs = [
        {
            "ref_id": entry.ref_id,
            "name": entry.name,
            "location_name": entry.location_name,
            "scene_zone_id": entry.scene_zone_id,
            "scene_zone_name": entry.scene_zone_name,
            "distance_band_to_player": entry.distance_band_to_player,
        }
        for entry in context_before.target_catalog.locations
    ]
    known_item_refs = [{"ref_id": entry.ref_id, "name": entry.name} for entry in context_before.target_catalog.items]

    if request.actions_override:
        normalized_actions = _normalize_override_actions(request.actions_override)
        intent = TurnIntent(
            world_id=world_id,
            world_character_id=session.character_state.world_character_id,
            raw_player_input=request.player_input,
            actions=normalized_actions,
            analysis_notes=["UI structured action override verwendet."],
        )
    else:
        intent = llm_runtime.analyze_intent(
            world_id=world_id,
            world_character_id=session.character_state.world_character_id,
            player_input=request.player_input,
            inventory=session.inventory,
            known_npc_names=known_npc_names,
            known_locations=known_locations,
            known_npc_refs=known_npc_refs,
            known_location_refs=known_location_refs,
            known_item_refs=known_item_refs,
            context=context_before,
        )
    resolution = engine.resolve(
        intent=intent,
        character_state=session.character_state,
        inventory=session.inventory,
    )
    narrative = llm_runtime.narrate(
        resolution=resolution,
        context_before=context_before,
    )
    turn_record, journal_entries = repository.save_turn_run(
        world_id=world_id,
        intent=intent,
        resolution=resolution,
        narrative=narrative,
    )
    context_after = None
    if request.include_context_after_turn:
        context_after = _assemble_context_for_world(
            repository=repository,
            world_id=world_id,
            player_input=request.player_input,
            turn_limit=8,
            memory_per_npc=4,
        )
    return TurnRunResponse(
        turn=turn_record,
        resulting_character_state=resolution.resulting_character_state,
        resulting_inventory=resolution.resulting_inventory,
        journal_entry_ids=[entry.journal_entry_id for entry in journal_entries],
        analysis_context_notes=context_before.retrieval_notes,
        context_before_turn=context_before.model_dump(mode="json") if request.include_context_before_turn else None,
        context_after_turn=context_after.model_dump(mode="json") if context_after is not None else None,
    )


def _normalize_override_actions(actions: list[TurnIntentAction]) -> list[TurnIntentAction]:
    normalized: list[TurnIntentAction] = []
    for action in actions:
        updates: dict[str, object] = {"analysis_source": "ui_structured_override"}
        params = dict(action.parameters)
        if action.action_type.value == "MOVE":
            destination_name = str(params.get("destination_name") or action.destination or "").strip()
            destination_id = str(params.get("destination_id") or action.target_ref or "").strip()
            if destination_name:
                updates["destination"] = destination_name
            if destination_id:
                updates["target_ref"] = destination_id
            params.setdefault("destination_name", destination_name or None)
            params.setdefault("destination_id", destination_id or None)
        if action.action_type.value in {"APPROACH", "RETREAT"}:
            target_name = str(params.get("target_name") or "").strip()
            target_id = str(params.get("target_id") or action.target_ref or "").strip()
            if target_id:
                updates["target_ref"] = target_id
            params.setdefault("target_name", target_name or None)
            params.setdefault("target_id", target_id or None)
        if action.action_type.value in {"TALK", "ATTACK"}:
            target_name = str(params.get("target_name") or "").strip()
            target_id = str(params.get("target_id") or action.target_ref or "").strip()
            if target_id:
                updates["target_ref"] = target_id
            params.setdefault("target_name", target_name or None)
            params.setdefault("target_id", target_id or None)
        if action.action_type.value == "USE_ITEM":
            item_id = str(params.get("item_id") or action.item_ref or "").strip()
            item_name = str(params.get("item_name") or params.get("target_name") or "").strip()
            if item_id:
                updates["item_ref"] = item_id
            if item_name and not action.target_ref:
                updates["target_ref"] = item_name
            params.setdefault("item_id", item_id or None)
            params.setdefault("item_name", item_name or None)
        updates["parameters"] = params
        normalized.append(action.model_copy(update=updates))
    return normalized


@app.get("/v1/worlds/{world_id}/turns", response_model=list[PersistedTurnRecord])
def list_world_turns(world_id: str, fastapi_request: Request, limit: int = 50) -> list[PersistedTurnRecord]:
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    return repository.list_turns(world_id=world_id, limit=limit)


@app.get("/v1/worlds/{world_id}/npc-memory", response_model=list[NPCMemoryBundle])
def list_world_npc_memory(
    world_id: str,
    fastapi_request: Request,
    limit_memories_per_npc: int = 5,
) -> list[NPCMemoryBundle]:
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    return repository.list_npc_memory_bundles(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        limit_memories_per_npc=limit_memories_per_npc,
    )
