from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from ls_shared_schemas.quests import QuestObjectiveState, WorldQuestState
from ls_shared_schemas.turns import TurnResolution


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
    for spec in specs:
        result = validate_quest_spec(spec)
        errors.extend(result.errors)
        if spec.quest_id in existing_ids:
            errors.append(f"quest_id_already_exists:{spec.quest_id}")
        if spec.quest_id in seen_new_ids:
            errors.append(f"duplicate_quest_id_in_batch:{spec.quest_id}")
        seen_new_ids.add(spec.quest_id)
    return QuestSpecValidationResult(ok=not errors, errors=tuple(errors))


def apply_transition_specs_to_quest_state(
    *,
    quest: WorldQuestState,
    spec: QuestSpec,
    story_flags: dict[str, str | int | bool] | None = None,
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
        fired_trigger_ids.append(trigger.trigger_id)
        triggered_objectives.add(objective.objective_id)

    return tuple(fired_trigger_ids)

