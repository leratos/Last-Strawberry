from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.game_api.app.services.quest_specs import (
    EffectSpec,
    ObjectiveSpec,
    ObjectiveTriggerSpec,
    PredicateSpec,
    QuestSpec,
    TransitionSpec,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EffectSetStoryFlagParams(StrictModel):
    quest_id: str | None = None
    flag_name: str
    value: str | int | float | bool | None = None


class EffectIncrementStoryFlagParams(StrictModel):
    quest_id: str | None = None
    flag_name: str
    step: int


class EffectSetObjectiveHintParams(StrictModel):
    quest_id: str | None = None
    objective_id: str
    hint: str


class EffectSetObjectiveStatusParams(StrictModel):
    quest_id: str | None = None
    objective_id: str
    status: str


class EffectSetQuestStateParams(StrictModel):
    quest_id: str | None = None
    stage: str | None = None
    status: str | None = None


class EffectEmitSystemEventParams(StrictModel):
    quest_id: str | None = None
    code: str
    message: str
    severity: str | None = None
    metadata: dict[str, str | int | float | bool | None] | None = None


class EffectSetStoryFlagPayload(StrictModel):
    effect_id: str
    kind: Literal["set_story_flag"]
    params: EffectSetStoryFlagParams
    priority: int = 100


class EffectIncrementStoryFlagPayload(StrictModel):
    effect_id: str
    kind: Literal["increment_story_flag"]
    params: EffectIncrementStoryFlagParams
    priority: int = 100


class EffectSetObjectiveHintPayload(StrictModel):
    effect_id: str
    kind: Literal["set_objective_hint"]
    params: EffectSetObjectiveHintParams
    priority: int = 100


class EffectSetObjectiveStatusPayload(StrictModel):
    effect_id: str
    kind: Literal["set_objective_status"]
    params: EffectSetObjectiveStatusParams
    priority: int = 100


class EffectSetQuestStatePayload(StrictModel):
    effect_id: str
    kind: Literal["set_quest_state"]
    params: EffectSetQuestStateParams
    priority: int = 100


class EffectEmitSystemEventPayload(StrictModel):
    effect_id: str
    kind: Literal["emit_system_event"]
    params: EffectEmitSystemEventParams
    priority: int = 100


AuthoringEffectPayload = Annotated[
    (
        EffectSetStoryFlagPayload
        | EffectIncrementStoryFlagPayload
        | EffectSetObjectiveHintPayload
        | EffectSetObjectiveStatusPayload
        | EffectSetQuestStatePayload
        | EffectEmitSystemEventPayload
    ),
    Field(discriminator="kind"),
]


class PredicateActionSeenPayload(StrictModel):
    predicate_id: str
    kind: Literal["action_seen"]
    action_types: list[str]
    target_ids: list[str] = Field(default_factory=list)
    target_id_contains: list[str] = Field(default_factory=list)
    target_names: list[str] = Field(default_factory=list)
    target_name_contains: list[str] = Field(default_factory=list)
    target_kinds: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)


class PredicateStoryFlagTruePayload(StrictModel):
    predicate_id: str
    kind: Literal["story_flag_true"]
    flag_name: str
    expected_bool: bool = True


class PredicateSystemEventSeenPayload(StrictModel):
    predicate_id: str
    kind: Literal["system_event_seen"]
    event_codes: list[str] = Field(default_factory=list)
    event_code_prefixes: list[str] = Field(default_factory=list)
    event_severities: list[str] = Field(default_factory=list)
    event_message_contains: list[str] = Field(default_factory=list)


class PredicateInventoryItemPresentPayload(StrictModel):
    predicate_id: str
    kind: Literal["inventory_item_present"]
    inventory_item_def_ids: list[str] = Field(default_factory=list)
    inventory_item_ids: list[str] = Field(default_factory=list)
    inventory_item_names: list[str] = Field(default_factory=list)
    inventory_item_name_contains: list[str] = Field(default_factory=list)
    inventory_categories: list[str] = Field(default_factory=list)
    inventory_min_quantity: int | None = None


class PredicateInventoryDeltaSeenPayload(StrictModel):
    predicate_id: str
    kind: Literal["inventory_delta_seen"]
    inventory_delta_kind: str
    inventory_item_def_ids: list[str] = Field(default_factory=list)
    inventory_item_ids: list[str] = Field(default_factory=list)
    inventory_item_names: list[str] = Field(default_factory=list)
    inventory_item_name_contains: list[str] = Field(default_factory=list)
    inventory_min_quantity: int | None = None


class PredicateRelationshipChangeSeenPayload(StrictModel):
    predicate_id: str
    kind: Literal["relationship_change_seen"]
    relationship_npc_ids: list[str] = Field(default_factory=list)
    relationship_npc_names: list[str] = Field(default_factory=list)
    relationship_delta_sign: str | None = None
    relationship_min_delta: int | None = None
    relationship_max_delta: int | None = None


AuthoringPredicatePayload = Annotated[
    (
        PredicateActionSeenPayload
        | PredicateStoryFlagTruePayload
        | PredicateSystemEventSeenPayload
        | PredicateInventoryItemPresentPayload
        | PredicateInventoryDeltaSeenPayload
        | PredicateRelationshipChangeSeenPayload
    ),
    Field(discriminator="kind"),
]


class ObjectivePayload(StrictModel):
    objective_id: str
    title: str
    hint: str


class ObjectiveHintUpdatePayload(StrictModel):
    objective_id: str
    hint: str


class ObjectiveTriggerPayload(StrictModel):
    trigger_id: str
    objective_id: str
    predicates: list[AuthoringPredicatePayload]
    require_all_predicates: bool = True
    requires_objectives_completed: list[str] = Field(default_factory=list)
    requires_story_flags_true: list[str] = Field(default_factory=list)
    set_status: str = "completed"
    set_hint: str | None = None
    effects: list[AuthoringEffectPayload] = Field(default_factory=list)
    priority: int = 100
    only_if_objective_status_in: list[str] = Field(default_factory=lambda: ["pending", "active"])


class TransitionPayload(StrictModel):
    transition_id: str
    to_stage: str
    to_status: str = "active"
    requires_all_objectives_completed: bool = False
    requires_objectives_completed: list[str] = Field(default_factory=list)
    requires_story_flags_true: list[str] = Field(default_factory=list)
    objective_hint_updates: list[ObjectiveHintUpdatePayload] = Field(default_factory=list)
    effects: list[AuthoringEffectPayload] = Field(default_factory=list)
    priority: int = 100


class QuestSpecPayload(StrictModel):
    quest_id: str
    title: str
    description: str
    initial_stage: str
    tags: list[str] = Field(default_factory=list)
    objectives: list[ObjectivePayload]
    objective_triggers: list[ObjectiveTriggerPayload] = Field(default_factory=list)
    transitions: list[TransitionPayload] = Field(default_factory=list)


class QuestSpecsValidateRequestPayload(StrictModel):
    specs: list[QuestSpecPayload] = Field(default_factory=list)
    existing_quest_ids: list[str] = Field(default_factory=list)


class QuestSpecsDryRunRequestPayload(StrictModel):
    world_id: str
    specs: list[QuestSpecPayload] = Field(default_factory=list)
    existing_quest_ids: list[str] = Field(default_factory=list)


class QuestSpecsApplyRequestPayload(StrictModel):
    world_id: str
    specs: list[QuestSpecPayload] = Field(default_factory=list)
    existing_quest_ids: list[str] = Field(default_factory=list)
    requested_by: str | None = None
    source: str | None = None


def _effect_payload_to_spec(effect: AuthoringEffectPayload) -> EffectSpec:
    return EffectSpec(
        effect_id=effect.effect_id,
        kind=effect.kind,
        params=effect.params.model_dump(exclude_none=True),
        priority=int(effect.priority),
    )


def _predicate_payload_to_spec(predicate: AuthoringPredicatePayload) -> PredicateSpec:
    data = predicate.model_dump(exclude_none=True)
    data["action_types"] = tuple(data.get("action_types", []))
    data["target_ids"] = tuple(data.get("target_ids", []))
    data["target_id_contains"] = tuple(data.get("target_id_contains", []))
    data["target_names"] = tuple(data.get("target_names", []))
    data["target_name_contains"] = tuple(data.get("target_name_contains", []))
    data["target_kinds"] = tuple(data.get("target_kinds", []))
    data["target_roles"] = tuple(data.get("target_roles", []))
    data["event_codes"] = tuple(data.get("event_codes", []))
    data["event_code_prefixes"] = tuple(data.get("event_code_prefixes", []))
    data["event_severities"] = tuple(data.get("event_severities", []))
    data["event_message_contains"] = tuple(data.get("event_message_contains", []))
    data["inventory_item_def_ids"] = tuple(data.get("inventory_item_def_ids", []))
    data["inventory_item_ids"] = tuple(data.get("inventory_item_ids", []))
    data["inventory_item_names"] = tuple(data.get("inventory_item_names", []))
    data["inventory_item_name_contains"] = tuple(data.get("inventory_item_name_contains", []))
    data["inventory_categories"] = tuple(data.get("inventory_categories", []))
    data["relationship_npc_ids"] = tuple(data.get("relationship_npc_ids", []))
    data["relationship_npc_names"] = tuple(data.get("relationship_npc_names", []))
    return PredicateSpec(**data)


def quest_spec_payload_to_spec(payload: QuestSpecPayload) -> QuestSpec:
    return QuestSpec(
        quest_id=payload.quest_id,
        title=payload.title,
        description=payload.description,
        initial_stage=payload.initial_stage,
        tags=tuple(payload.tags),
        objectives=tuple(
            ObjectiveSpec(
                objective_id=objective.objective_id,
                title=objective.title,
                hint=objective.hint,
            )
            for objective in payload.objectives
        ),
        objective_triggers=tuple(
            ObjectiveTriggerSpec(
                trigger_id=trigger.trigger_id,
                objective_id=trigger.objective_id,
                predicates=tuple(_predicate_payload_to_spec(predicate) for predicate in trigger.predicates),
                require_all_predicates=trigger.require_all_predicates,
                requires_objectives_completed=tuple(trigger.requires_objectives_completed),
                requires_story_flags_true=tuple(trigger.requires_story_flags_true),
                set_status=trigger.set_status,
                set_hint=trigger.set_hint,
                effects=tuple(_effect_payload_to_spec(effect) for effect in trigger.effects),
                priority=trigger.priority,
                only_if_objective_status_in=tuple(trigger.only_if_objective_status_in),
            )
            for trigger in payload.objective_triggers
        ),
        transitions=tuple(
            TransitionSpec(
                transition_id=transition.transition_id,
                to_stage=transition.to_stage,
                to_status=transition.to_status,
                requires_all_objectives_completed=transition.requires_all_objectives_completed,
                requires_objectives_completed=tuple(transition.requires_objectives_completed),
                requires_story_flags_true=tuple(transition.requires_story_flags_true),
                objective_hint_updates=tuple(
                    (update.objective_id, update.hint) for update in transition.objective_hint_updates
                ),
                effects=tuple(_effect_payload_to_spec(effect) for effect in transition.effects),
                priority=transition.priority,
            )
            for transition in payload.transitions
        ),
    )


def format_authoring_schema_errors(exc: ValidationError) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for item in exc.errors():
        loc = item.get("loc", ())
        path = ".".join(str(part) for part in loc)
        error_type = str(item.get("type") or "validation_error")
        message = str(item.get("msg") or "Invalid value.")
        errors.append(
            {
                "code": f"schema_invalid_{error_type.replace('.', '_')}",
                "field": path or "payload",
                "message": message,
            }
        )
    return errors


def parse_validate_request_payload(raw_payload: dict[str, Any]) -> QuestSpecsValidateRequestPayload:
    return QuestSpecsValidateRequestPayload.model_validate(raw_payload)


def parse_dry_run_request_payload(raw_payload: dict[str, Any]) -> QuestSpecsDryRunRequestPayload:
    return QuestSpecsDryRunRequestPayload.model_validate(raw_payload)


def parse_apply_request_payload(raw_payload: dict[str, Any]) -> QuestSpecsApplyRequestPayload:
    return QuestSpecsApplyRequestPayload.model_validate(raw_payload)
