from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from ls_shared_schemas.quests import QuestObjectiveState, WorldQuestState


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
class QuestSpec:
    quest_id: str
    title: str
    description: str
    initial_stage: str
    tags: tuple[str, ...]
    objectives: tuple[ObjectiveSpec, ...]
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

