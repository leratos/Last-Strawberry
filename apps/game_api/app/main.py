from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, UTC
import json
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from apps.game_api.app.config import settings
from apps.game_api.app.persistence import QuestSpecApplyRepositoryError, WorldRepository
from apps.game_api.app.services.bootstrap_preview import build_world_bootstrap_preview
from apps.game_api.app.services.context_assembly import assemble_game_context
from apps.game_api.app.services.llm_runtime import build_llm_runtime
from apps.game_api.app.services.quest_authoring import (
    build_npc_dialog_hints_for_context,
    build_npc_dialog_topics_for_context,
)
from apps.game_api.app.services.quest_authoring_api import (
    format_authoring_domain_errors,
    format_authoring_schema_errors,
    parse_apply_request_payload,
    parse_dry_run_request_payload,
    parse_validate_request_payload,
    quest_spec_payload_to_spec,
)
from apps.game_api.app.services.quest_specs import (
    QuestSpec,
    build_effect_schema_document,
    build_predicate_schema_document,
    compile_quest_spec_to_world_state,
    validate_quest_specs_for_activation,
)
from ls_rules_engine import RulesEngine
from ls_shared_schemas.character import CharacterState
from ls_shared_schemas.game_context import GameContextResponse
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.npc_memory import NPCMemoryBundle, NPCProfile
from ls_shared_schemas.turns import (
    LlmCapabilityTrace,
    NarrativeEnvelope,
    PersistedTurnRecord,
    TurnIntent,
    TurnIntentAction,
    TurnResolution,
    TurnProviderTrace,
    TurnRunRequest,
    TurnRunResponse,
)
from ls_shared_schemas.world import ScenePointSeed, WorldBootstrapRequest, WorldBootstrapResult, WorldSessionResponse


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


class DevGenerateScenePointProposalsRequest(BaseModel):
    location_name: str | None = Field(default=None, max_length=120)
    max_items: int = Field(default=2, ge=1, le=5)
    requested_by: str | None = Field(default=None, max_length=120)
    source: str | None = Field(default="devtest_scene_point_proposals", max_length=120)


class DevReviewScenePointProposalRequest(BaseModel):
    reviewed_by: str | None = Field(default=None, max_length=120)
    decision_note: str | None = Field(default=None, max_length=500)


class DevScenePointProposalRecord(BaseModel):
    proposal_id: str
    world_id: str
    world_character_id: str
    status: str
    scene_point: ScenePointSeed
    source: str | None = None
    requested_by: str | None = None
    provider_trace: LlmCapabilityTrace | None = None
    decision_note: str | None = None
    reviewed_by: str | None = None
    applied_to_world_seed: bool = False
    created_at: str
    updated_at: str
    reviewed_at: str | None = None


class DevGenerateScenePointProposalsResponse(BaseModel):
    generated_count: int
    stored_count: int
    trace: LlmCapabilityTrace
    proposals: list[DevScenePointProposalRecord] = Field(default_factory=list)


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
    allow_origin_regex=settings.cors_allow_origin_regex or None,
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
    quests = repository.list_world_quest_states(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
    )
    story_flags = repository.get_world_story_flags(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
    )
    visible_scene_points = repository.list_visible_scene_points_in_location(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        location_name=session.character_state.location_name,
    )
    context = assemble_game_context(
        world=session,
        turns=turns,
        npc_memory=npc_memory,
        story_flags=story_flags,
        quests=quests,
        retrieval_player_input=player_input,
        scene_points=visible_scene_points,
        journal_limit=journal_limit,
        turn_limit=turn_limit,
        memory_per_npc=memory_per_npc,
    )
    hidden_npc_count = repository.count_hidden_npcs_in_location(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        location_name=session.character_state.location_name,
    )
    context.discovery_counts["hidden_npc_count"] = int(hidden_npc_count)
    if hidden_npc_count > 0:
        context.retrieval_notes.append(
            f"Es gibt {hidden_npc_count} unbekannte Praesenz(en) an diesem Ort. Umsehen/Untersuchen kann neue Ziele aufdecken."
        )
    hidden_scene_points = repository.count_hidden_scene_points_in_location(
        world_id=world_id,
        world_character_id=session.character_state.world_character_id,
        location_name=session.character_state.location_name,
    )
    context.discovery_counts["visible_scene_point_count"] = int(len(context.target_catalog.scene_points))
    context.discovery_counts["detail_verified_scene_point_count"] = int(
        sum(1 for point in context.target_catalog.scene_points if int(point.detail_level or 0) >= 2)
    )
    context.discovery_counts["hidden_scene_point_count"] = int(hidden_scene_points)
    if hidden_scene_points > 0:
        context.retrieval_notes.append(
            f"Es gibt {hidden_scene_points} unerkundete Interaktions-/Objektpunkt(e) an diesem Ort. 'schau mich um' kann sie sichtbar machen."
        )
    for npc_ref in context.target_catalog.npcs:
        hints = build_npc_dialog_hints_for_context(
            quests=context.quests,
            npc_id=npc_ref.ref_id,
            npc_name=npc_ref.name,
            npc_role=npc_ref.role,
        )
        if hints:
            npc_ref.discovery_state.update(hints)
        dialog_topics = build_npc_dialog_topics_for_context(
            quests=context.quests,
            story_flags=context.story_flags,
            npc_id=npc_ref.ref_id,
            npc_name=npc_ref.name,
            npc_role=npc_ref.role,
        )
        if dialog_topics:
            npc_ref.discovery_state["dialog_topics_json"] = json.dumps(dialog_topics, ensure_ascii=True)
    return context


def _build_bootstrap_result_with_llm(
    request: WorldBootstrapRequest,
) -> tuple[WorldBootstrapResult, LlmCapabilityTrace]:
    preview = build_world_bootstrap_preview(request)
    return llm_runtime.enrich_world_bootstrap_preview_with_trace(request=request, preview=preview)


def _target_quest_id_for_effect(*, effect_params: dict[str, object], default_quest_id: str) -> str:
    target_quest = str(effect_params.get("quest_id") or "").strip()
    return target_quest or default_quest_id


def _build_dry_run_diff(*, specs: list[QuestSpec], existing_quest_ids: set[str]) -> dict[str, object]:
    quests_added = sorted(spec.quest_id for spec in specs if spec.quest_id not in existing_quest_ids)
    flags_index: dict[tuple[str, str, str], dict[str, str | None]] = {}
    objectives_index: dict[tuple[str, str, str], dict[str, str]] = {}
    events_index: dict[tuple[str, str, str], dict[str, str | None]] = {}

    def add_flag(*, quest_id: str, flag_name: str, mode: str, source: str) -> None:
        key = (quest_id, flag_name, mode)
        if key in flags_index:
            return
        flags_index[key] = {
            "quest_id": quest_id,
            "flag_name": flag_name,
            "mode": mode,
            "source": source,
        }

    def add_objective(*, quest_id: str, objective_id: str, change: str, source: str) -> None:
        key = (quest_id, objective_id, change)
        if key in objectives_index:
            return
        objectives_index[key] = {
            "quest_id": quest_id,
            "objective_id": objective_id,
            "change": change,
            "source": source,
        }

    def add_event(*, code: str, severity: str | None, source: str) -> None:
        safe_severity = str(severity or "").strip() or "info"
        key = (code, safe_severity, source)
        if key in events_index:
            return
        events_index[key] = {
            "code": code,
            "severity": safe_severity,
            "source": source,
        }

    for spec in specs:
        for trigger in spec.objective_triggers:
            add_objective(
                quest_id=spec.quest_id,
                objective_id=trigger.objective_id,
                change=f"set_status:{trigger.set_status}",
                source=f"trigger:{trigger.trigger_id}",
            )
            if trigger.set_hint:
                add_objective(
                    quest_id=spec.quest_id,
                    objective_id=trigger.objective_id,
                    change="set_hint",
                    source=f"trigger:{trigger.trigger_id}",
                )
            for effect in trigger.effects:
                effect_params = dict(effect.params or {})
                target_quest_id = _target_quest_id_for_effect(effect_params=effect_params, default_quest_id=spec.quest_id)
                source = f"trigger_effect:{trigger.trigger_id}:{effect.effect_id}"
                if effect.kind == "set_story_flag":
                    flag_name = str(effect_params.get("flag_name") or "").strip()
                    if flag_name:
                        add_flag(quest_id=target_quest_id, flag_name=flag_name, mode="set", source=source)
                elif effect.kind == "increment_story_flag":
                    flag_name = str(effect_params.get("flag_name") or "").strip()
                    if flag_name:
                        add_flag(quest_id=target_quest_id, flag_name=flag_name, mode="increment", source=source)
                elif effect.kind in {"set_objective_hint", "set_objective_status"}:
                    objective_id = str(effect_params.get("objective_id") or "").strip()
                    if objective_id:
                        change = "set_hint" if effect.kind == "set_objective_hint" else f"set_status:{effect_params.get('status')}"
                        add_objective(
                            quest_id=target_quest_id,
                            objective_id=objective_id,
                            change=change,
                            source=source,
                        )
                elif effect.kind == "emit_system_event":
                    code = str(effect_params.get("code") or "").strip()
                    if code:
                        add_event(code=code, severity=str(effect_params.get("severity") or "info"), source=source)

        for transition in spec.transitions:
            for objective_id, _hint in transition.objective_hint_updates:
                add_objective(
                    quest_id=spec.quest_id,
                    objective_id=objective_id,
                    change="set_hint",
                    source=f"transition:{transition.transition_id}",
                )
            for effect in transition.effects:
                effect_params = dict(effect.params or {})
                target_quest_id = _target_quest_id_for_effect(effect_params=effect_params, default_quest_id=spec.quest_id)
                source = f"transition_effect:{transition.transition_id}:{effect.effect_id}"
                if effect.kind == "set_story_flag":
                    flag_name = str(effect_params.get("flag_name") or "").strip()
                    if flag_name:
                        add_flag(quest_id=target_quest_id, flag_name=flag_name, mode="set", source=source)
                elif effect.kind == "increment_story_flag":
                    flag_name = str(effect_params.get("flag_name") or "").strip()
                    if flag_name:
                        add_flag(quest_id=target_quest_id, flag_name=flag_name, mode="increment", source=source)
                elif effect.kind in {"set_objective_hint", "set_objective_status"}:
                    objective_id = str(effect_params.get("objective_id") or "").strip()
                    if objective_id:
                        change = "set_hint" if effect.kind == "set_objective_hint" else f"set_status:{effect_params.get('status')}"
                        add_objective(
                            quest_id=target_quest_id,
                            objective_id=objective_id,
                            change=change,
                            source=source,
                        )
                elif effect.kind == "emit_system_event":
                    code = str(effect_params.get("code") or "").strip()
                    if code:
                        add_event(code=code, severity=str(effect_params.get("severity") or "info"), source=source)

    return {
        "quests_added": quests_added,
        "flags_changed": [
            flags_index[key]
            for key in sorted(flags_index.keys(), key=lambda item: (item[0], item[1], item[2]))
        ],
        "objectives_changed": [
            objectives_index[key]
            for key in sorted(objectives_index.keys(), key=lambda item: (item[0], item[1], item[2]))
        ],
        "events_expected": [
            events_index[key]
            for key in sorted(events_index.keys(), key=lambda item: (item[0], item[1], item[2]))
        ],
    }


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
        "hybrid_intent_llm_for_complex_inputs": str(llm_status.hybrid_intent_llm_for_complex_inputs).lower(),
        "bootstrap_provider": llm_status.bootstrap_provider,
        "intent_provider": llm_status.intent_provider,
        "narration_provider": llm_status.narration_provider,
        "openrouter_configured": str(llm_status.openrouter_configured).lower(),
        "openrouter_bootstrap_model": llm_status.bootstrap_model,
        "openrouter_intent_model": llm_status.intent_model,
        "openrouter_narrator_model": llm_status.narrator_model,
        "openrouter_json_repair_attempts": str(settings.openrouter_json_repair_attempts),
    }


@app.get("/v1/quest-specs/effects/schema")
def get_quest_effect_schema() -> dict[str, object]:
    return build_effect_schema_document()


@app.get("/v1/quest-specs/predicates/schema")
def get_quest_predicate_schema() -> dict[str, object]:
    return build_predicate_schema_document()


@app.post("/v1/quest-specs/validate")
def validate_quest_specs(raw_payload: dict[str, Any]) -> dict[str, object]:
    try:
        payload = parse_validate_request_payload(raw_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "authoring_schema_validation_failed",
                "errors": format_authoring_schema_errors(exc),
            },
        ) from exc

    specs = [quest_spec_payload_to_spec(spec) for spec in payload.specs]
    result = validate_quest_specs_for_activation(
        specs,
        existing_quest_ids=set(payload.existing_quest_ids),
    )
    return {
        "ok": result.ok,
        "spec_count": len(specs),
        "error_count": len(result.errors),
        "errors": list(result.errors),
        "errors_structured": format_authoring_domain_errors(result.errors),
    }


@app.post("/v1/quest-specs/preview/dry-run")
def dry_run_quest_specs(raw_payload: dict[str, Any], fastapi_request: Request) -> dict[str, object]:
    try:
        payload = parse_dry_run_request_payload(raw_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "authoring_schema_validation_failed",
                "errors": format_authoring_schema_errors(exc),
            },
        ) from exc

    repository = _get_world_repository(fastapi_request)
    context = _assemble_context_for_world(
        repository=repository,
        world_id=payload.world_id,
        journal_limit=10,
        turn_limit=10,
        memory_per_npc=3,
    )
    specs = [quest_spec_payload_to_spec(spec) for spec in payload.specs]
    existing_quest_ids = set(payload.existing_quest_ids)
    existing_quest_ids.update(quest.quest_id for quest in context.quests)

    validation = validate_quest_specs_for_activation(specs, existing_quest_ids=existing_quest_ids)
    compiled_preview = [compile_quest_spec_to_world_state(spec).model_dump(mode="json") for spec in specs]
    diff_summary = _build_dry_run_diff(specs=specs, existing_quest_ids=existing_quest_ids)
    return {
        "ok": validation.ok,
        "world_id": payload.world_id,
        "validated_at_utc": datetime.now(UTC).isoformat(),
        "spec_count": len(specs),
        "validation": {
            "ok": validation.ok,
            "error_count": len(validation.errors),
            "errors": list(validation.errors),
            "errors_structured": format_authoring_domain_errors(validation.errors),
        },
        "world_context": {
            "quest_count": len(context.quests),
            "quest_ids": [quest.quest_id for quest in context.quests],
            "story_flag_count": len(context.story_flags),
            "story_flags": dict(context.story_flags),
        },
        "compiled_preview": {
            "quest_count": len(compiled_preview),
            "quests": compiled_preview,
        },
        "diff": diff_summary,
    }


@app.post("/v1/quest-specs/apply")
def apply_quest_specs(raw_payload: dict[str, Any], fastapi_request: Request) -> dict[str, object]:
    try:
        payload = parse_apply_request_payload(raw_payload)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "authoring_schema_validation_failed",
                "errors": format_authoring_schema_errors(exc),
            },
        ) from exc

    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(payload.world_id)
    if session is None:
        raise HTTPException(status_code=404, detail={"code": "world_not_found", "message": "World session not found."})

    specs = [quest_spec_payload_to_spec(spec) for spec in payload.specs]
    existing_quest_ids = set(payload.existing_quest_ids)

    validation = validate_quest_specs_for_activation(specs, existing_quest_ids=existing_quest_ids)
    if not validation.ok:
        audit_id = repository.record_authoring_audit_log(
            world_id=payload.world_id,
            world_character_id=session.character_state.world_character_id,
            action="quest_specs_apply",
            status="failed",
            request_payload={
                "world_id": payload.world_id,
                "spec_count": len(specs),
                "quest_ids": [spec.quest_id for spec in specs],
            },
            result_payload={"ok": False, "errors": list(validation.errors)},
            error_code="authoring_domain_validation_failed",
            requested_by=payload.requested_by,
            source=payload.source,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "authoring_domain_validation_failed",
                "audit_id": audit_id,
                "errors": list(validation.errors),
                "errors_structured": format_authoring_domain_errors(validation.errors),
            },
        )

    try:
        result = repository.apply_authored_quest_specs(
            world_id=payload.world_id,
            specs=specs,
            requested_by=payload.requested_by,
            source=payload.source,
        )
    except QuestSpecApplyRepositoryError as exc:
        status_code = 500
        if exc.code == "world_not_found":
            status_code = 404
        elif exc.code == "quest_id_conflict":
            status_code = 409
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": str(exc)},
        ) from exc

    return {
        "ok": True,
        "world_id": payload.world_id,
        "audit_id": result["audit_id"],
        "applied_count": result["applied_count"],
        "applied_quest_ids": result["applied_quest_ids"],
        "world_character_id": result["world_character_id"],
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
    result, trace = _build_bootstrap_result_with_llm(request)
    return result.model_copy(update={"bootstrap_trace": trace})


@app.post("/v1/worlds/bootstrap", response_model=WorldSessionResponse)
def world_bootstrap_create(request: WorldBootstrapRequest, fastapi_request: Request) -> WorldSessionResponse:
    bootstrap_result, bootstrap_trace = _build_bootstrap_result_with_llm(request)
    repository = _get_world_repository(fastapi_request)
    session = repository.create_world_session(request=request, bootstrap=bootstrap_result)
    return session.model_copy(update={"bootstrap_trace": bootstrap_trace})


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


@app.post(
    "/v1/devtest/worlds/{world_id}/scene-points/proposals/generate",
    response_model=DevGenerateScenePointProposalsResponse,
)
def devtest_generate_scene_point_proposals(
    world_id: str,
    request: DevGenerateScenePointProposalsRequest,
    fastapi_request: Request,
) -> DevGenerateScenePointProposalsResponse:
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="Dev/Test scene-point proposal endpoint is disabled in production.",
        )
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    context = _assemble_context_for_world(
        repository=repository,
        world_id=world_id,
        player_input=None,
        journal_limit=10,
        turn_limit=8,
        memory_per_npc=4,
    )
    generated, trace = llm_runtime.propose_scene_points_with_trace(
        world=session,
        context=context,
        location_name=request.location_name,
        max_items=request.max_items,
    )
    try:
        stored = repository.create_scene_point_proposals(
            world_id=world_id,
            proposals=generated,
            source=request.source,
            requested_by=request.requested_by,
            provider_trace=trace,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DevGenerateScenePointProposalsResponse(
        generated_count=len(generated),
        stored_count=len(stored),
        trace=trace,
        proposals=[DevScenePointProposalRecord.model_validate(entry) for entry in stored],
    )


@app.get(
    "/v1/devtest/worlds/{world_id}/scene-points/proposals",
    response_model=list[DevScenePointProposalRecord],
)
def devtest_list_scene_point_proposals(
    world_id: str,
    fastapi_request: Request,
    status: str | None = None,
    limit: int = 50,
) -> list[DevScenePointProposalRecord]:
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="Dev/Test scene-point proposal endpoint is disabled in production.",
        )
    repository = _get_world_repository(fastapi_request)
    session = repository.get_world_session(world_id)
    if session is None:
        raise HTTPException(status_code=404, detail="World session not found.")
    try:
        rows = repository.list_scene_point_proposals(
            world_id=world_id,
            status=status,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [DevScenePointProposalRecord.model_validate(row) for row in rows]


@app.post(
    "/v1/devtest/worlds/{world_id}/scene-points/proposals/{proposal_id}/approve",
    response_model=DevScenePointProposalRecord,
)
def devtest_approve_scene_point_proposal(
    world_id: str,
    proposal_id: str,
    request: DevReviewScenePointProposalRequest,
    fastapi_request: Request,
) -> DevScenePointProposalRecord:
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="Dev/Test scene-point proposal endpoint is disabled in production.",
        )
    repository = _get_world_repository(fastapi_request)
    try:
        row = repository.approve_scene_point_proposal(
            world_id=world_id,
            proposal_id=proposal_id,
            reviewed_by=request.reviewed_by,
            decision_note=request.decision_note,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "not pending" in detail.lower() else 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return DevScenePointProposalRecord.model_validate(row)


@app.post(
    "/v1/devtest/worlds/{world_id}/scene-points/proposals/{proposal_id}/reject",
    response_model=DevScenePointProposalRecord,
)
def devtest_reject_scene_point_proposal(
    world_id: str,
    proposal_id: str,
    request: DevReviewScenePointProposalRequest,
    fastapi_request: Request,
) -> DevScenePointProposalRecord:
    if settings.environment.lower() == "production":
        raise HTTPException(
            status_code=403,
            detail="Dev/Test scene-point proposal endpoint is disabled in production.",
        )
    repository = _get_world_repository(fastapi_request)
    try:
        row = repository.reject_scene_point_proposal(
            world_id=world_id,
            proposal_id=proposal_id,
            reviewed_by=request.reviewed_by,
            decision_note=request.decision_note,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 409 if "not pending" in detail.lower() else 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return DevScenePointProposalRecord.model_validate(row)


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
    scene_point_refs = [
        {
            "ref_id": entry.ref_id,
            "name": entry.name,
            "kind": entry.kind,
            "aliases_csv": ",".join(entry.aliases or []),
            "location_name": entry.location_name,
            "scene_zone_id": entry.scene_zone_id,
            "scene_zone_name": entry.scene_zone_name,
        }
        for entry in context.target_catalog.scene_points
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
        known_scene_point_refs=scene_point_refs,
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
    known_scene_point_refs = [
        {
            "ref_id": entry.ref_id,
            "name": entry.name,
            "kind": entry.kind,
            "aliases_csv": ",".join(entry.aliases or []),
            "location_name": entry.location_name,
            "scene_zone_id": entry.scene_zone_id,
            "scene_zone_name": entry.scene_zone_name,
        }
        for entry in context_before.target_catalog.scene_points
    ]

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
        intent, intent_trace = llm_runtime.analyze_intent_with_trace(
            world_id=world_id,
            world_character_id=session.character_state.world_character_id,
            player_input=request.player_input,
            inventory=session.inventory,
            known_npc_names=known_npc_names,
            known_locations=known_locations,
            known_npc_refs=known_npc_refs,
            known_location_refs=known_location_refs,
            known_item_refs=known_item_refs,
            known_scene_point_refs=known_scene_point_refs,
            context=context_before,
        )
    if request.actions_override:
        intent_trace = LlmCapabilityTrace(
            capability="intent",
            mode=settings.llm_mode,
            provider_policy="ui_structured_override",
            provider_used="ui_structured_override",
            model=None,
            fallback_used=False,
        )
    resolution = engine.resolve(
        intent=intent,
        character_state=session.character_state,
        inventory=session.inventory,
    )
    narrative, narration_trace = llm_runtime.narrate_with_trace(
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
        provider_trace=TurnProviderTrace(intent=intent_trace, narration=narration_trace),
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
        if action.action_type.value in {"INSPECT", "OPEN", "SEARCH", "TAKE"}:
            target_id = str(params.get("target_id") or action.target_ref or "").strip()
            target_name = str(params.get("target_name") or "").strip()
            if target_id:
                updates["target_ref"] = target_id
            params.setdefault("target_id", target_id or None)
            params.setdefault("target_name", target_name or None)
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
