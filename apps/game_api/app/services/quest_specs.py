from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
import re

from ls_shared_schemas.quests import QuestObjectiveState, WorldQuestState
from ls_shared_schemas.turns import TurnResolution, TurnSystemEvent


@dataclass(frozen=True)
class ObjectiveSpec:
    objective_id: str
    title: str
    hint: str


@dataclass(frozen=True)
class TransitionSpec:
    transition_id: str
    to_stage: str
    to_status: str = "active"
    requires_all_objectives_completed: bool = False
    requires_objectives_completed: tuple[str, ...] = ()
    requires_story_flags_true: tuple[str, ...] = ()
    objective_hint_updates: tuple[tuple[str, str], ...] = ()
    effects: tuple["EffectSpec", ...] = ()
    priority: int = 100


@dataclass(frozen=True)
class EffectSpec:
    effect_id: str
    kind: str
    params: dict[str, str | int | float | bool | None | dict[str, str | int | float | bool | None]] = field(
        default_factory=dict
    )
    priority: int = 100


@dataclass(frozen=True)
class PredicateSpec:
    predicate_id: str
    kind: str
    action_types: tuple[str, ...] = ()
    target_ids: tuple[str, ...] = ()
    target_id_contains: tuple[str, ...] = ()
    target_names: tuple[str, ...] = ()
    target_name_contains: tuple[str, ...] = ()
    target_kinds: tuple[str, ...] = ()
    target_roles: tuple[str, ...] = ()
    event_codes: tuple[str, ...] = ()
    event_code_prefixes: tuple[str, ...] = ()
    event_severities: tuple[str, ...] = ()
    event_message_contains: tuple[str, ...] = ()
    inventory_item_def_ids: tuple[str, ...] = ()
    inventory_item_ids: tuple[str, ...] = ()
    inventory_item_names: tuple[str, ...] = ()
    inventory_item_name_contains: tuple[str, ...] = ()
    inventory_categories: tuple[str, ...] = ()
    inventory_min_quantity: int | None = None
    inventory_delta_kind: str | None = None  # gained | consumed
    relationship_npc_ids: tuple[str, ...] = ()
    relationship_npc_names: tuple[str, ...] = ()
    relationship_delta_sign: str | None = None  # positive | negative | nonzero
    relationship_min_delta: int | None = None
    relationship_max_delta: int | None = None
    flag_name: str | None = None
    expected_bool: bool = True


@dataclass(frozen=True)
class ObjectiveTriggerSpec:
    trigger_id: str
    objective_id: str
    predicates: tuple[PredicateSpec, ...]
    require_all_predicates: bool = True
    requires_objectives_completed: tuple[str, ...] = ()
    requires_story_flags_true: tuple[str, ...] = ()
    set_status: str = "completed"
    set_hint: str | None = None
    effects: tuple[EffectSpec, ...] = ()
    priority: int = 100
    only_if_objective_status_in: tuple[str, ...] = ("pending", "active")


@dataclass(frozen=True)
class QuestSpec:
    quest_id: str
    title: str
    description: str
    initial_stage: str
    tags: tuple[str, ...]
    objectives: tuple[ObjectiveSpec, ...]
    objective_triggers: tuple[ObjectiveTriggerSpec, ...] = ()
    transitions: tuple[TransitionSpec, ...] = ()


@dataclass(frozen=True)
class QuestSpecValidationResult:
    ok: bool
    errors: tuple[str, ...]


_FLAG_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_EVENT_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_EFFECT_ALLOWED_PARAMS_BY_KIND: dict[str, set[str]] = {
    "set_story_flag": {"quest_id", "flag_name", "value"},
    "increment_story_flag": {"quest_id", "flag_name", "step"},
    "set_objective_hint": {"quest_id", "objective_id", "hint"},
    "set_objective_status": {"quest_id", "objective_id", "status"},
    "set_quest_state": {"quest_id", "stage", "status"},
    "emit_system_event": {"quest_id", "code", "message", "severity", "metadata"},
}
_EFFECT_REQUIRED_PARAMS_BY_KIND: dict[str, tuple[str, ...]] = {
    "set_story_flag": ("flag_name",),
    "increment_story_flag": ("flag_name", "step"),
    "set_objective_hint": ("objective_id", "hint"),
    "set_objective_status": ("objective_id", "status"),
    "set_quest_state": (),
    "emit_system_event": ("code", "message"),
}
_EFFECT_KIND_DESCRIPTIONS: dict[str, str] = {
    "set_story_flag": "Sets or overwrites a story flag value.",
    "increment_story_flag": "Increments an integer-like story flag by step.",
    "set_objective_hint": "Updates objective hint text.",
    "set_objective_status": "Sets objective status (pending|active|completed|failed).",
    "set_quest_state": "Sets quest stage and/or quest status.",
    "emit_system_event": "Emits a system event into turn resolution.",
}
_EFFECT_PARAM_DOCS: dict[str, dict[str, str]] = {
    "quest_id": {"type": "string", "description": "Optional target quest id. Defaults to current quest."},
    "flag_name": {"type": "string", "description": "Story flag key (pattern: ^[a-z][a-z0-9_]*$)."},
    "value": {"type": "string|int|float|bool|null", "description": "Primitive story flag value."},
    "step": {"type": "int", "description": "Increment step for integer-like story flags."},
    "objective_id": {"type": "string", "description": "Objective id in target quest."},
    "hint": {"type": "string", "description": "Human-readable objective hint text."},
    "status": {"type": "string", "description": "Objective/quest status value."},
    "stage": {"type": "string", "description": "Quest stage identifier."},
    "code": {"type": "string", "description": "System event code (pattern: ^[a-z][a-z0-9_]*$)."},
    "message": {"type": "string", "description": "System event message."},
    "severity": {"type": "string", "description": "One of: info, warning, error."},
    "metadata": {"type": "object<string, primitive>", "description": "Optional flat metadata map."},
}
_PREDICATE_ALLOWED_FIELDS_BY_KIND: dict[str, set[str]] = {
    "action_seen": {
        "action_types",
        "target_ids",
        "target_id_contains",
        "target_names",
        "target_name_contains",
        "target_kinds",
        "target_roles",
    },
    "story_flag_true": {"flag_name", "expected_bool"},
    "system_event_seen": {"event_codes", "event_code_prefixes", "event_severities", "event_message_contains"},
    "inventory_item_present": {
        "inventory_item_def_ids",
        "inventory_item_ids",
        "inventory_item_names",
        "inventory_item_name_contains",
        "inventory_categories",
        "inventory_min_quantity",
    },
    "inventory_delta_seen": {
        "inventory_delta_kind",
        "inventory_item_def_ids",
        "inventory_item_ids",
        "inventory_item_names",
        "inventory_item_name_contains",
        "inventory_min_quantity",
    },
    "relationship_change_seen": {
        "relationship_npc_ids",
        "relationship_npc_names",
        "relationship_delta_sign",
        "relationship_min_delta",
        "relationship_max_delta",
    },
}
_PREDICATE_REQUIRED_FIELDS_BY_KIND: dict[str, tuple[str, ...]] = {
    "action_seen": ("action_types",),
    "story_flag_true": ("flag_name",),
    "system_event_seen": (),
    "inventory_item_present": (),
    "inventory_delta_seen": ("inventory_delta_kind",),
    "relationship_change_seen": (),
}
_PREDICATE_KIND_DESCRIPTIONS: dict[str, str] = {
    "action_seen": "Matches if an applied action satisfies action/target filters.",
    "story_flag_true": "Matches if a story flag equals expected_bool (default true).",
    "system_event_seen": "Matches if a system event satisfies code/severity/message filters.",
    "inventory_item_present": "Matches against resulting inventory snapshot.",
    "inventory_delta_seen": "Matches against inventory_gained or inventory_consumed deltas.",
    "relationship_change_seen": "Matches against relationship delta entries in state_delta.",
}
_PREDICATE_FIELD_DOCS: dict[str, dict[str, str]] = {
    "action_types": {"type": "array<string>", "description": "Action types like TALK/INSPECT/OPEN."},
    "target_ids": {"type": "array<string>", "description": "Exact target ids."},
    "target_id_contains": {"type": "array<string>", "description": "Target id substrings."},
    "target_names": {"type": "array<string>", "description": "Exact target names (case-insensitive)."},
    "target_name_contains": {"type": "array<string>", "description": "Target name substrings (case-insensitive)."},
    "target_kinds": {"type": "array<string>", "description": "Target kinds (npc/container/scene_object/...)."},
    "target_roles": {"type": "array<string>", "description": "NPC role filters."},
    "flag_name": {"type": "string", "description": "Story flag key to read."},
    "expected_bool": {"type": "bool", "description": "Expected boolean value (default true)."},
    "event_codes": {"type": "array<string>", "description": "Exact event code match list."},
    "event_code_prefixes": {"type": "array<string>", "description": "Event code prefixes."},
    "event_severities": {"type": "array<string>", "description": "Event severities (info/warning/error)."},
    "event_message_contains": {"type": "array<string>", "description": "Event message substring filters."},
    "inventory_item_def_ids": {"type": "array<string>", "description": "Inventory item definition ids."},
    "inventory_item_ids": {"type": "array<string>", "description": "Inventory instance ids."},
    "inventory_item_names": {"type": "array<string>", "description": "Exact item names."},
    "inventory_item_name_contains": {"type": "array<string>", "description": "Item name substrings."},
    "inventory_categories": {"type": "array<string>", "description": "Item category filters."},
    "inventory_min_quantity": {"type": "int", "description": "Minimum quantity threshold."},
    "inventory_delta_kind": {"type": "string", "description": "One of: gained, consumed."},
    "relationship_npc_ids": {"type": "array<string>", "description": "Relationship delta NPC ids."},
    "relationship_npc_names": {"type": "array<string>", "description": "Relationship delta NPC names."},
    "relationship_delta_sign": {"type": "string", "description": "One of: positive, negative, nonzero."},
    "relationship_min_delta": {"type": "int", "description": "Minimum standing delta."},
    "relationship_max_delta": {"type": "int", "description": "Maximum standing delta."},
}


def build_effect_schema_document() -> dict[str, object]:
    effect_kinds: list[dict[str, object]] = []
    for kind in sorted(_EFFECT_ALLOWED_PARAMS_BY_KIND.keys()):
        allowed = sorted(_EFFECT_ALLOWED_PARAMS_BY_KIND[kind])
        required = list(_EFFECT_REQUIRED_PARAMS_BY_KIND.get(kind, ()))
        params: dict[str, dict[str, object]] = {}
        for param_name in allowed:
            doc = _EFFECT_PARAM_DOCS.get(param_name, {})
            params[param_name] = {
                "type": str(doc.get("type") or "unknown"),
                "required": param_name in required,
                "description": str(doc.get("description") or ""),
            }
        effect_kinds.append(
            {
                "kind": kind,
                "description": _EFFECT_KIND_DESCRIPTIONS.get(kind, ""),
                "required_params": required,
                "allowed_params": allowed,
                "params": params,
            }
        )
    return {
        "schema_version": "1.0.0",
        "effect_kind_count": len(effect_kinds),
        "effect_kinds": effect_kinds,
    }


def build_predicate_schema_document() -> dict[str, object]:
    predicate_kinds: list[dict[str, object]] = []
    for kind in sorted(_PREDICATE_ALLOWED_FIELDS_BY_KIND.keys()):
        allowed = sorted(_PREDICATE_ALLOWED_FIELDS_BY_KIND[kind])
        required = list(_PREDICATE_REQUIRED_FIELDS_BY_KIND.get(kind, ()))
        fields: dict[str, dict[str, object]] = {}
        for field_name in allowed:
            doc = _PREDICATE_FIELD_DOCS.get(field_name, {})
            fields[field_name] = {
                "type": str(doc.get("type") or "unknown"),
                "required": field_name in required,
                "description": str(doc.get("description") or ""),
            }
        predicate_kinds.append(
            {
                "kind": kind,
                "description": _PREDICATE_KIND_DESCRIPTIONS.get(kind, ""),
                "required_fields": required,
                "allowed_fields": allowed,
                "fields": fields,
            }
        )
    return {
        "schema_version": "1.0.0",
        "predicate_kind_count": len(predicate_kinds),
        "predicate_kinds": predicate_kinds,
    }


def _is_primitive_value(value: object) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _validate_effect_spec(effect: EffectSpec) -> tuple[str, ...]:
    errors: list[str] = []
    if not effect.effect_id.strip():
        errors.append("effect_id_empty")
    if effect.kind not in {
        "set_story_flag",
        "increment_story_flag",
        "set_objective_hint",
        "set_objective_status",
        "set_quest_state",
        "emit_system_event",
    }:
        errors.append(f"effect_unknown_kind:{effect.effect_id}:{effect.kind}")
        return tuple(errors)

    params = dict(effect.params or {})
    allowed_params = _EFFECT_ALLOWED_PARAMS_BY_KIND.get(effect.kind, set())
    for param_name in sorted(params.keys()):
        if param_name not in allowed_params:
            errors.append(f"effect_unknown_param:{effect.effect_id}:{param_name}")
    quest_id_raw = params.get("quest_id")
    if quest_id_raw is not None:
        if not isinstance(quest_id_raw, str):
            errors.append(f"effect_invalid_quest_id_type:{effect.effect_id}")
        elif not str(quest_id_raw).strip():
            errors.append(f"effect_invalid_quest_id:{effect.effect_id}")

    if effect.kind in {"set_story_flag", "increment_story_flag"}:
        flag_name_raw = params.get("flag_name")
        flag_name = str(flag_name_raw or "").strip()
        if not flag_name:
            errors.append(f"effect_missing_flag_name:{effect.effect_id}")
        elif not _FLAG_NAME_PATTERN.match(flag_name):
            errors.append(f"effect_invalid_flag_name:{effect.effect_id}:{flag_name}")
        if flag_name_raw is not None and not isinstance(flag_name_raw, str):
            errors.append(f"effect_invalid_flag_name_type:{effect.effect_id}")

    if effect.kind == "set_story_flag" and "value" in params:
        if not _is_primitive_value(params.get("value")):
            errors.append(f"effect_invalid_flag_value_type:{effect.effect_id}")

    if effect.kind == "increment_story_flag":
        step = params.get("step")
        if type(step) is not int:
            errors.append(f"effect_increment_step_invalid:{effect.effect_id}")

    if effect.kind in {"set_objective_hint", "set_objective_status"}:
        objective_id_raw = params.get("objective_id")
        objective_id = str(objective_id_raw or "").strip()
        if not objective_id:
            errors.append(f"effect_missing_objective_id:{effect.effect_id}")
        if objective_id_raw is not None and not isinstance(objective_id_raw, str):
            errors.append(f"effect_invalid_objective_id_type:{effect.effect_id}")

    if effect.kind == "set_objective_hint":
        hint_raw = params.get("hint")
        hint = str(hint_raw or "").strip()
        if not hint:
            errors.append(f"effect_missing_hint:{effect.effect_id}")
        if hint_raw is not None and not isinstance(hint_raw, str):
            errors.append(f"effect_invalid_hint_type:{effect.effect_id}")

    if effect.kind == "set_objective_status":
        status_raw = params.get("status")
        status = str(status_raw or "").strip()
        if status not in {"pending", "active", "completed", "failed"}:
            errors.append(f"effect_invalid_objective_status:{effect.effect_id}")
        if status_raw is not None and not isinstance(status_raw, str):
            errors.append(f"effect_invalid_objective_status_type:{effect.effect_id}")

    if effect.kind == "set_quest_state":
        stage_raw = params.get("stage")
        status_raw = params.get("status")
        stage = str(stage_raw or "").strip()
        status = str(status_raw or "").strip()
        if not stage and not status:
            errors.append(f"effect_missing_quest_state_fields:{effect.effect_id}")
        if stage_raw is not None and not isinstance(stage_raw, str):
            errors.append(f"effect_invalid_stage_type:{effect.effect_id}")
        if status_raw is not None and not isinstance(status_raw, str):
            errors.append(f"effect_invalid_quest_status_type:{effect.effect_id}")

    if effect.kind == "emit_system_event":
        event_code_raw = params.get("code")
        event_code = str(event_code_raw or "").strip()
        if not event_code:
            errors.append(f"effect_missing_event_code:{effect.effect_id}")
        elif not _EVENT_CODE_PATTERN.match(event_code):
            errors.append(f"effect_invalid_event_code:{effect.effect_id}:{event_code}")
        if event_code_raw is not None and not isinstance(event_code_raw, str):
            errors.append(f"effect_invalid_event_code_type:{effect.effect_id}")
        message_raw = params.get("message")
        if not str(message_raw or "").strip():
            errors.append(f"effect_missing_event_message:{effect.effect_id}")
        if message_raw is not None and not isinstance(message_raw, str):
            errors.append(f"effect_invalid_event_message_type:{effect.effect_id}")
        severity_raw = params.get("severity")
        severity = str(severity_raw or "info").strip().lower()
        if severity not in {"info", "warning", "error"}:
            errors.append(f"effect_invalid_event_severity:{effect.effect_id}:{severity}")
        if severity_raw is not None and not isinstance(severity_raw, str):
            errors.append(f"effect_invalid_event_severity_type:{effect.effect_id}")
        metadata_raw = params.get("metadata")
        if metadata_raw is not None:
            if not isinstance(metadata_raw, dict):
                errors.append(f"effect_invalid_event_metadata_type:{effect.effect_id}")
            else:
                for metadata_key, metadata_value in metadata_raw.items():
                    if not isinstance(metadata_key, str):
                        errors.append(f"effect_invalid_event_metadata_key_type:{effect.effect_id}")
                        break
                    if not _is_primitive_value(metadata_value):
                        errors.append(f"effect_invalid_event_metadata_value_type:{effect.effect_id}:{metadata_key}")
                        break
    return tuple(errors)


def _validate_effect_references(
    *,
    effect: EffectSpec,
    source_id: str,
    source_type: str,
    default_quest_id: str,
    known_quest_ids: set[str],
    objective_ids_by_quest: dict[str, set[str]],
    allow_unknown_external_quest: bool = False,
) -> tuple[str, ...]:
    errors: list[str] = []
    params = dict(effect.params or {})
    target_quest_id = str(params.get("quest_id") or "").strip() or default_quest_id

    if effect.kind in {"set_objective_hint", "set_objective_status"}:
        objective_id = str(params.get("objective_id") or "").strip()
        if allow_unknown_external_quest and target_quest_id != default_quest_id and target_quest_id not in known_quest_ids:
            return tuple(errors)
        if target_quest_id not in known_quest_ids:
            errors.append(
                f"{source_type}_effect_error:{source_id}:effect_unknown_target_quest:{effect.effect_id}:{target_quest_id}"
            )
            return tuple(errors)
        known_objectives = objective_ids_by_quest.get(target_quest_id)
        if known_objectives is not None and objective_id not in known_objectives:
            errors.append(
                f"{source_type}_effect_error:{source_id}:effect_unknown_target_objective:{effect.effect_id}:{target_quest_id}:{objective_id}"
            )

    if effect.kind == "set_quest_state":
        if allow_unknown_external_quest and target_quest_id != default_quest_id and target_quest_id not in known_quest_ids:
            return tuple(errors)
        if target_quest_id not in known_quest_ids:
            errors.append(
                f"{source_type}_effect_error:{source_id}:effect_unknown_target_quest:{effect.effect_id}:{target_quest_id}"
            )

    return tuple(errors)


def compile_quest_spec_to_world_state(spec: QuestSpec, *, now: datetime | None = None) -> WorldQuestState:
    created_at = now or datetime.now(UTC)
    return WorldQuestState(
        quest_id=spec.quest_id,
        title=spec.title,
        description=spec.description,
        status="active",
        current_stage=spec.initial_stage,
        objectives=[
            QuestObjectiveState(
                objective_id=objective.objective_id,
                title=objective.title,
                status="pending",
                hint=objective.hint,
            )
            for objective in spec.objectives
        ],
        tags=list(spec.tags),
        updated_at=created_at,
    )


def validate_quest_spec(spec: QuestSpec) -> QuestSpecValidationResult:
    errors: list[str] = []
    if not spec.quest_id.strip():
        errors.append("quest_id_empty")
    if not spec.title.strip():
        errors.append("title_empty")
    if not spec.initial_stage.strip():
        errors.append("initial_stage_empty")
    if not spec.objectives:
        errors.append("missing_objectives")

    objective_ids = [objective.objective_id for objective in spec.objectives]
    duplicate_objective_ids = {objective_id for objective_id in objective_ids if objective_ids.count(objective_id) > 1}
    for objective_id in sorted(duplicate_objective_ids):
        errors.append(f"duplicate_objective_id:{objective_id}")

    known_objectives = set(objective_ids)
    known_quest_ids = {spec.quest_id}
    objective_ids_by_quest = {spec.quest_id: known_objectives}
    trigger_ids: list[str] = []
    for trigger in spec.objective_triggers:
        if not trigger.trigger_id.strip():
            errors.append("objective_trigger_id_empty")
        trigger_ids.append(trigger.trigger_id)
        if trigger.objective_id not in known_objectives:
            errors.append(f"objective_trigger_unknown_objective:{trigger.trigger_id}:{trigger.objective_id}")
        for objective_id in trigger.requires_objectives_completed:
            if objective_id not in known_objectives:
                errors.append(f"objective_trigger_requires_unknown_objective:{trigger.trigger_id}:{objective_id}")
        if not trigger.predicates:
            errors.append(f"objective_trigger_missing_predicates:{trigger.trigger_id}")
        for predicate in trigger.predicates:
            if not predicate.predicate_id.strip():
                errors.append(f"predicate_id_empty:{trigger.trigger_id}")
            if predicate.kind not in {
                "action_seen",
                "story_flag_true",
                "system_event_seen",
                "inventory_item_present",
                "inventory_delta_seen",
                "relationship_change_seen",
            }:
                errors.append(f"predicate_unknown_kind:{trigger.trigger_id}:{predicate.predicate_id}:{predicate.kind}")
            if predicate.kind == "action_seen":
                if not predicate.action_types:
                    errors.append(f"predicate_action_missing_types:{trigger.trigger_id}:{predicate.predicate_id}")
            if predicate.kind == "story_flag_true":
                if not (predicate.flag_name or "").strip():
                    errors.append(f"predicate_story_flag_missing_name:{trigger.trigger_id}:{predicate.predicate_id}")
            if predicate.kind == "system_event_seen":
                if not (
                    predicate.event_codes
                    or predicate.event_code_prefixes
                    or predicate.event_severities
                    or predicate.event_message_contains
                ):
                    errors.append(f"predicate_system_event_missing_filters:{trigger.trigger_id}:{predicate.predicate_id}")
            if predicate.kind == "inventory_item_present":
                if not (
                    predicate.inventory_item_def_ids
                    or predicate.inventory_item_ids
                    or predicate.inventory_item_names
                    or predicate.inventory_item_name_contains
                    or predicate.inventory_categories
                ):
                    errors.append(f"predicate_inventory_missing_filters:{trigger.trigger_id}:{predicate.predicate_id}")
            if predicate.kind == "inventory_delta_seen":
                if predicate.inventory_delta_kind not in {"gained", "consumed"}:
                    errors.append(f"predicate_inventory_delta_kind_invalid:{trigger.trigger_id}:{predicate.predicate_id}")
                if not (
                    predicate.inventory_item_def_ids
                    or predicate.inventory_item_ids
                    or predicate.inventory_item_names
                    or predicate.inventory_item_name_contains
                ):
                    errors.append(f"predicate_inventory_delta_missing_filters:{trigger.trigger_id}:{predicate.predicate_id}")
            if predicate.kind == "relationship_change_seen":
                if not (predicate.relationship_npc_ids or predicate.relationship_npc_names):
                    errors.append(f"predicate_relationship_missing_target:{trigger.trigger_id}:{predicate.predicate_id}")
                if predicate.relationship_delta_sign and predicate.relationship_delta_sign not in {"positive", "negative", "nonzero"}:
                    errors.append(f"predicate_relationship_sign_invalid:{trigger.trigger_id}:{predicate.predicate_id}")
        for effect in trigger.effects:
            for effect_error in _validate_effect_spec(effect):
                errors.append(f"trigger_effect_error:{trigger.trigger_id}:{effect_error}")
            errors.extend(
                _validate_effect_references(
                    effect=effect,
                    source_id=trigger.trigger_id,
                    source_type="trigger",
                    default_quest_id=spec.quest_id,
                    known_quest_ids=known_quest_ids,
                    objective_ids_by_quest=objective_ids_by_quest,
                    allow_unknown_external_quest=True,
                )
            )

    duplicate_trigger_ids = {trigger_id for trigger_id in trigger_ids if trigger_ids.count(trigger_id) > 1 and trigger_id}
    for trigger_id in sorted(duplicate_trigger_ids):
        errors.append(f"duplicate_objective_trigger_id:{trigger_id}")

    transition_ids: list[str] = []
    for transition in spec.transitions:
        if not transition.transition_id.strip():
            errors.append("transition_id_empty")
        transition_ids.append(transition.transition_id)
        if not transition.to_stage.strip():
            errors.append(f"transition_missing_stage:{transition.transition_id}")
        for objective_id in transition.requires_objectives_completed:
            if objective_id not in known_objectives:
                errors.append(f"transition_unknown_objective:{transition.transition_id}:{objective_id}")
        for objective_id, _hint in transition.objective_hint_updates:
            if objective_id not in known_objectives:
                errors.append(f"transition_hint_unknown_objective:{transition.transition_id}:{objective_id}")
        for effect in transition.effects:
            for effect_error in _validate_effect_spec(effect):
                errors.append(f"transition_effect_error:{transition.transition_id}:{effect_error}")
            errors.extend(
                _validate_effect_references(
                    effect=effect,
                    source_id=transition.transition_id,
                    source_type="transition",
                    default_quest_id=spec.quest_id,
                    known_quest_ids=known_quest_ids,
                    objective_ids_by_quest=objective_ids_by_quest,
                    allow_unknown_external_quest=True,
                )
            )

    duplicate_transition_ids = {
        transition_id for transition_id in transition_ids if transition_ids.count(transition_id) > 1 and transition_id
    }
    for transition_id in sorted(duplicate_transition_ids):
        errors.append(f"duplicate_transition_id:{transition_id}")

    return QuestSpecValidationResult(ok=not errors, errors=tuple(errors))


def validate_quest_specs_for_activation(
    specs: list[QuestSpec],
    *,
    existing_quest_ids: set[str] | None = None,
) -> QuestSpecValidationResult:
    """Validation entrypoint for future authored/runtime/LLM-generated quest specs.

    This is the planned docking point for KI-Questvorschlaege: proposals can be
    validated/compiled before activation without letting the narrator mutate world
    state directly.
    """

    errors: list[str] = []
    existing_ids = set(existing_quest_ids or set())
    seen_new_ids: set[str] = set()
    objective_ids_by_quest = {
        spec.quest_id: {objective.objective_id for objective in spec.objectives}
        for spec in specs
    }
    known_quest_ids = set(existing_ids) | set(objective_ids_by_quest.keys())
    for spec in specs:
        result = validate_quest_spec(spec)
        errors.extend(result.errors)
        if spec.quest_id in existing_ids:
            errors.append(f"quest_id_already_exists:{spec.quest_id}")
        if spec.quest_id in seen_new_ids:
            errors.append(f"duplicate_quest_id_in_batch:{spec.quest_id}")
        seen_new_ids.add(spec.quest_id)
        for trigger in spec.objective_triggers:
            for effect in trigger.effects:
                target_quest_id = str((effect.params or {}).get("quest_id") or "").strip()
                if not target_quest_id:
                    continue
                errors.extend(
                    _validate_effect_references(
                        effect=effect,
                        source_id=trigger.trigger_id,
                        source_type="trigger",
                        default_quest_id=spec.quest_id,
                        known_quest_ids=known_quest_ids,
                        objective_ids_by_quest=objective_ids_by_quest,
                    )
                )
        for transition in spec.transitions:
            for effect in transition.effects:
                target_quest_id = str((effect.params or {}).get("quest_id") or "").strip()
                if not target_quest_id:
                    continue
                errors.extend(
                    _validate_effect_references(
                        effect=effect,
                        source_id=transition.transition_id,
                        source_type="transition",
                        default_quest_id=spec.quest_id,
                        known_quest_ids=known_quest_ids,
                        objective_ids_by_quest=objective_ids_by_quest,
                    )
                )
    return QuestSpecValidationResult(ok=not errors, errors=tuple(errors))


def apply_transition_specs_to_quest_state(
    *,
    quest: WorldQuestState,
    spec: QuestSpec,
    story_flags: dict[str, str | int | bool] | None = None,
    mutable_story_flags: dict[str, str | int | bool] | None = None,
    emitted_events: list[TurnSystemEvent] | None = None,
    now: datetime | None = None,
) -> None:
    """Apply the highest-priority matching transition to a quest state (in place)."""

    if not spec.transitions:
        return
    flags = dict(story_flags or {})
    objective_state_map = {objective.objective_id: objective.status for objective in quest.objectives}
    all_completed = all(status == "completed" for status in objective_state_map.values())

    sorted_transitions = sorted(spec.transitions, key=lambda transition: transition.priority)
    for transition in sorted_transitions:
        if transition.requires_all_objectives_completed and not all_completed:
            continue
        if transition.requires_objectives_completed:
            if any(objective_state_map.get(objective_id) != "completed" for objective_id in transition.requires_objectives_completed):
                continue
        if transition.requires_story_flags_true:
            if any(not bool(flags.get(flag_name, False)) for flag_name in transition.requires_story_flags_true):
                continue

        for objective_id, hint in transition.objective_hint_updates:
            for objective in quest.objectives:
                if objective.objective_id == objective_id:
                    objective.hint = hint
                    break

        quest.status = transition.to_status
        quest.current_stage = transition.to_stage
        timestamp = now or datetime.now(UTC)
        quest.updated_at = timestamp
        if transition.to_status == "completed":
            quest.completed_at = quest.completed_at or timestamp
        if transition.effects:
            effect_events = apply_effect_specs(
                effects=transition.effects,
                current_quest=quest,
                all_quests={quest.quest_id: quest},
                story_flags=mutable_story_flags,
                now=timestamp,
            )
            if emitted_events is not None and effect_events:
                emitted_events.extend(effect_events)
        return


def _matches_action_predicate(predicate: PredicateSpec, *, resolution: TurnResolution) -> bool:
    action_types = {value.strip().upper() for value in predicate.action_types if value.strip()}
    target_ids = {value.strip() for value in predicate.target_ids if value.strip()}
    target_id_contains = {value.strip().lower() for value in predicate.target_id_contains if value.strip()}
    target_names = {value.strip().lower() for value in predicate.target_names if value.strip()}
    target_name_contains = {value.strip().lower() for value in predicate.target_name_contains if value.strip()}
    target_kinds = {value.strip().lower() for value in predicate.target_kinds if value.strip()}
    target_roles = {value.strip().lower() for value in predicate.target_roles if value.strip()}

    for action in resolution.applied_actions:
        action_type = str(getattr(action.action_type, "value", action.action_type)).strip().upper()
        if action_types and action_type not in action_types:
            continue

        target_id = str(action.parameters.get("target_id") or action.target_ref or "").strip()
        if target_ids or target_id_contains:
            id_match = False
            if target_id and target_ids and target_id in target_ids:
                id_match = True
            if target_id and target_id_contains and any(fragment in target_id.lower() for fragment in target_id_contains):
                id_match = True
            if not id_match:
                continue

        target_name = str(action.parameters.get("target_name") or "").strip().lower()
        if target_names or target_name_contains:
            name_match = False
            if target_name and target_names and target_name in target_names:
                name_match = True
            if target_name and target_name_contains and any(fragment in target_name for fragment in target_name_contains):
                name_match = True
            if not name_match:
                continue

        target_kind = str(action.parameters.get("target_kind") or action.target_kind or "").strip().lower()
        if target_kinds and target_kind not in target_kinds:
            continue

        target_role = str(action.parameters.get("target_role") or "").strip().lower()
        if target_roles and target_role not in target_roles:
            continue

        return True
    return False


def _matches_system_event_predicate(predicate: PredicateSpec, *, resolution: TurnResolution) -> bool:
    event_codes = {value.strip() for value in predicate.event_codes if value.strip()}
    event_code_prefixes = {value.strip() for value in predicate.event_code_prefixes if value.strip()}
    event_severities = {value.strip().lower() for value in predicate.event_severities if value.strip()}
    event_message_contains = {value.strip().lower() for value in predicate.event_message_contains if value.strip()}

    for event in resolution.system_events:
        code = str(event.code or "").strip()
        severity = str(event.severity or "").strip().lower()
        message = str(event.message or "").strip().lower()

        if event_codes and code not in event_codes:
            continue
        if event_code_prefixes and not any(code.startswith(prefix) for prefix in event_code_prefixes):
            continue
        if event_severities and severity not in event_severities:
            continue
        if event_message_contains and not any(fragment in message for fragment in event_message_contains):
            continue
        return True
    return False


def _matches_inventory_item_filters(
    *,
    predicate: PredicateSpec,
    item_id: str,
    item_def_id: str,
    item_name: str,
    category: str,
    quantity: int,
) -> bool:
    item_ids = {value.strip() for value in predicate.inventory_item_ids if value.strip()}
    item_def_ids = {value.strip() for value in predicate.inventory_item_def_ids if value.strip()}
    item_names = {value.strip().lower() for value in predicate.inventory_item_names if value.strip()}
    item_name_contains = {value.strip().lower() for value in predicate.inventory_item_name_contains if value.strip()}
    categories = {value.strip().lower() for value in predicate.inventory_categories if value.strip()}

    if item_ids and item_id not in item_ids:
        return False
    if item_def_ids and item_def_id not in item_def_ids:
        return False
    if item_names and item_name.lower() not in item_names:
        return False
    if item_name_contains and not any(fragment in item_name.lower() for fragment in item_name_contains):
        return False
    if categories and category.lower() not in categories:
        return False
    if predicate.inventory_min_quantity is not None and quantity < int(predicate.inventory_min_quantity):
        return False
    return True


def _matches_inventory_item_present_predicate(predicate: PredicateSpec, *, resolution: TurnResolution) -> bool:
    for item in resolution.resulting_inventory:
        if _matches_inventory_item_filters(
            predicate=predicate,
            item_id=str(item.inventory_item_id),
            item_def_id=str(item.item_def_id),
            item_name=str(item.name),
            category=str(item.category),
            quantity=int(item.quantity),
        ):
            return True
    return False


def _matches_inventory_delta_seen_predicate(predicate: PredicateSpec, *, resolution: TurnResolution) -> bool:
    delta_kind = str(predicate.inventory_delta_kind or "").strip().lower()
    if delta_kind == "gained":
        delta_items = resolution.state_delta.inventory_gained
    elif delta_kind == "consumed":
        delta_items = resolution.state_delta.inventory_consumed
    else:
        return False

    for entry in delta_items:
        item_id = str(entry.get("inventory_item_id") or entry.get("item_id") or entry.get("id") or "")
        item_def_id = str(entry.get("item_def_id") or entry.get("item_def") or "")
        item_name = str(entry.get("name") or "")
        quantity_value = entry.get("quantity")
        try:
            quantity = int(quantity_value if quantity_value is not None else 1)
        except (TypeError, ValueError):
            quantity = 1
        if _matches_inventory_item_filters(
            predicate=predicate,
            item_id=item_id,
            item_def_id=item_def_id,
            item_name=item_name,
            category="",
            quantity=quantity,
        ):
            return True
    return False


def _matches_relationship_change_seen_predicate(predicate: PredicateSpec, *, resolution: TurnResolution) -> bool:
    npc_ids = {value.strip() for value in predicate.relationship_npc_ids if value.strip()}
    npc_names = {value.strip().lower() for value in predicate.relationship_npc_names if value.strip()}
    sign = str(predicate.relationship_delta_sign or "").strip().lower()

    for change in resolution.state_delta.relationship_changes:
        npc_id = str(change.get("npc_id") or "").strip()
        npc_name = str(change.get("npc") or change.get("npc_name") or "").strip().lower()
        if npc_ids and npc_id not in npc_ids:
            continue
        if npc_names and npc_name not in npc_names:
            continue
        try:
            delta_value = int(change.get("standing_delta", 0))
        except (TypeError, ValueError):
            continue
        if sign == "positive" and delta_value <= 0:
            continue
        if sign == "negative" and delta_value >= 0:
            continue
        if sign == "nonzero" and delta_value == 0:
            continue
        if predicate.relationship_min_delta is not None and delta_value < int(predicate.relationship_min_delta):
            continue
        if predicate.relationship_max_delta is not None and delta_value > int(predicate.relationship_max_delta):
            continue
        return True
    return False


def _matches_predicate_spec(
    predicate: PredicateSpec,
    *,
    resolution: TurnResolution,
    story_flags: dict[str, str | int | bool],
) -> bool:
    if predicate.kind == "action_seen":
        return _matches_action_predicate(predicate, resolution=resolution)
    if predicate.kind == "story_flag_true":
        flag_name = str(predicate.flag_name or "").strip()
        if not flag_name:
            return False
        return bool(story_flags.get(flag_name, False)) is bool(predicate.expected_bool)
    if predicate.kind == "system_event_seen":
        return _matches_system_event_predicate(predicate, resolution=resolution)
    if predicate.kind == "inventory_item_present":
        return _matches_inventory_item_present_predicate(predicate, resolution=resolution)
    if predicate.kind == "inventory_delta_seen":
        return _matches_inventory_delta_seen_predicate(predicate, resolution=resolution)
    if predicate.kind == "relationship_change_seen":
        return _matches_relationship_change_seen_predicate(predicate, resolution=resolution)
    return False


def apply_objective_trigger_specs_to_quest_state(
    *,
    quest: WorldQuestState,
    spec: QuestSpec,
    resolution: TurnResolution,
    story_flags: dict[str, str | int | bool] | None = None,
    mutable_story_flags: dict[str, str | int | bool] | None = None,
    emitted_events: list[TurnSystemEvent] | None = None,
    now: datetime | None = None,
) -> tuple[str, ...]:
    """Apply objective completion triggers to quest state (in place)."""

    if not spec.objective_triggers:
        return ()

    timestamp = now or datetime.now(UTC)
    flags = dict(story_flags or {})
    objective_map = {objective.objective_id: objective for objective in quest.objectives}
    fired_trigger_ids: list[str] = []
    triggered_objectives: set[str] = set()

    for trigger in sorted(spec.objective_triggers, key=lambda item: item.priority):
        objective = objective_map.get(trigger.objective_id)
        if objective is None:
            continue
        if objective.objective_id in triggered_objectives:
            continue
        if trigger.only_if_objective_status_in and objective.status not in set(trigger.only_if_objective_status_in):
            continue
        if trigger.requires_objectives_completed:
            if any(
                objective_map.get(objective_id) is None or objective_map[objective_id].status != "completed"
                for objective_id in trigger.requires_objectives_completed
            ):
                continue
        if trigger.requires_story_flags_true:
            if any(not bool(flags.get(flag_name, False)) for flag_name in trigger.requires_story_flags_true):
                continue

        predicate_matches = [
            _matches_predicate_spec(predicate, resolution=resolution, story_flags=flags) for predicate in trigger.predicates
        ]
        if trigger.require_all_predicates:
            if not all(predicate_matches):
                continue
        else:
            if not any(predicate_matches):
                continue

        objective.status = trigger.set_status
        if trigger.set_hint:
            objective.hint = trigger.set_hint
        quest.updated_at = timestamp
        if trigger.effects:
            effect_events = apply_effect_specs(
                effects=trigger.effects,
                current_quest=quest,
                all_quests={quest.quest_id: quest},
                story_flags=mutable_story_flags,
                now=timestamp,
            )
            if emitted_events is not None and effect_events:
                emitted_events.extend(effect_events)
        fired_trigger_ids.append(trigger.trigger_id)
        triggered_objectives.add(objective.objective_id)

    return tuple(fired_trigger_ids)


def apply_effect_specs(
    *,
    effects: tuple[EffectSpec, ...],
    current_quest: WorldQuestState,
    all_quests: dict[str, WorldQuestState] | None = None,
    story_flags: dict[str, str | int | bool] | None = None,
    now: datetime | None = None,
) -> list[TurnSystemEvent]:
    if not effects:
        return []
    timestamp = now or datetime.now(UTC)
    events: list[TurnSystemEvent] = []
    quest_lookup = dict(all_quests or {})
    quest_lookup.setdefault(current_quest.quest_id, current_quest)
    flags = story_flags if story_flags is not None else {}

    for effect in sorted(effects, key=lambda item: item.priority):
        params = dict(effect.params or {})
        quest_id = str(params.get("quest_id") or "").strip() or current_quest.quest_id
        quest = quest_lookup.get(quest_id)
        if quest is None:
            continue

        if effect.kind == "set_story_flag":
            flag_name = str(params.get("flag_name") or "").strip()
            if not flag_name:
                continue
            value = params.get("value", True)
            if not _is_primitive_value(value):
                continue
            flags[flag_name] = bool(value) if isinstance(value, bool) else value
            continue

        if effect.kind == "increment_story_flag":
            flag_name = str(params.get("flag_name") or "").strip()
            step = params.get("step")
            if not flag_name or type(step) is not int:
                continue
            current_value = flags.get(flag_name, 0)
            try:
                base = int(current_value)
            except (TypeError, ValueError):
                base = 0
            flags[flag_name] = base + step
            continue

        if effect.kind == "set_objective_hint":
            objective_id = str(params.get("objective_id") or "").strip()
            hint = str(params.get("hint") or "").strip()
            if not objective_id or not hint:
                continue
            for objective in quest.objectives:
                if objective.objective_id == objective_id:
                    objective.hint = hint
                    quest.updated_at = timestamp
                    break
            continue

        if effect.kind == "set_objective_status":
            objective_id = str(params.get("objective_id") or "").strip()
            status = str(params.get("status") or "").strip()
            if not objective_id or status not in {"pending", "active", "completed", "failed"}:
                continue
            for objective in quest.objectives:
                if objective.objective_id == objective_id:
                    objective.status = status
                    quest.updated_at = timestamp
                    if status == "completed":
                        if all(obj.status == "completed" for obj in quest.objectives):
                            quest.status = "completed"
                            quest.current_stage = "completed"
                            quest.completed_at = quest.completed_at or timestamp
                    break
            continue

        if effect.kind == "set_quest_state":
            stage = str(params.get("stage") or "").strip()
            status = str(params.get("status") or "").strip()
            if stage:
                quest.current_stage = stage
            if status:
                quest.status = status
                if status == "completed":
                    quest.completed_at = quest.completed_at or timestamp
            quest.updated_at = timestamp
            continue

        if effect.kind == "emit_system_event":
            code = str(params.get("code") or "").strip()
            message = str(params.get("message") or "").strip()
            if not code or not message:
                continue
            severity = str(params.get("severity") or "info").strip().lower()
            if severity not in {"info", "warning", "error"}:
                severity = "info"
            metadata_raw = params.get("metadata")
            metadata: dict[str, str | int | float | bool | None] = {}
            if isinstance(metadata_raw, dict):
                for key, value in metadata_raw.items():
                    if isinstance(key, str) and _is_primitive_value(value):
                        metadata[str(key)] = value
            events.append(
                TurnSystemEvent(
                    code=code,
                    message=message,
                    severity=severity,
                    metadata=metadata,
                )
            )
            continue

    return events

