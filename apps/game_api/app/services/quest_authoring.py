from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from ls_shared_schemas.quests import QuestObjectiveState, WorldQuestState
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnResolution, TurnSystemEvent
from ls_shared_schemas.world import WorldSeed


URBAN_OCCULT_QUEST_ID = "quest-urban-occult-market-ritual-leads"


@dataclass(frozen=True)
class QuestAdvanceResult:
    quests: list[WorldQuestState]
    system_events: list[TurnSystemEvent]


def initial_quest_states_for_world_seed(world_seed: WorldSeed) -> list[WorldQuestState]:
    if not _looks_urban_occult_world_seed(world_seed):
        return []
    now = datetime.now(UTC)
    return [
        WorldQuestState(
            quest_id=URBAN_OCCULT_QUEST_ID,
            title="Spuren des fehlgeschlagenen Rituals",
            description=(
                "Finde heraus, was am Marktplatz schiefgelaufen ist: sprich mit Kael, "
                "untersuche die Vorratskiste und gleiche deine Erkenntnisse mit Mira ab."
            ),
            status="active",
            current_stage="investigate_scene",
            objectives=[
                QuestObjectiveState(
                    objective_id="speak_with_kael",
                    title="Mit Kael sprechen",
                    status="pending",
                    hint="Kael wirkt angespannt am Brunnenplatz und weiss vermutlich mehr ueber das Ritual.",
                ),
                QuestObjectiveState(
                    objective_id="inspect_supply_crate",
                    title="Vorratskiste untersuchen",
                    status="pending",
                    hint="Am Marktplatz gibt es eine Vorratskiste mit moeglichen Hinweisen oder Materialspuren.",
                ),
                QuestObjectiveState(
                    objective_id="report_to_mira",
                    title="Mit Mira die Funde abgleichen",
                    status="pending",
                    hint="Mira beobachtet die Lage ruhig und kann Hinweise einordnen.",
                ),
            ],
            tags=["urban_occult", "starter", "investigation"],
            updated_at=now,
        )
    ]


def advance_quests_for_turn(
    *,
    quests: list[WorldQuestState],
    intent: TurnIntent,
    resolution: TurnResolution,
) -> QuestAdvanceResult:
    if not quests:
        return QuestAdvanceResult(quests=[], system_events=[])

    updated_quests: list[WorldQuestState] = []
    emitted_events: list[TurnSystemEvent] = []
    now = datetime.now(UTC)

    for quest in quests:
        if quest.quest_id != URBAN_OCCULT_QUEST_ID:
            updated_quests.append(quest)
            continue

        before_status = quest.status
        before_objectives = {obj.objective_id: obj.status for obj in quest.objectives}
        quest_copy = quest.model_copy(deep=True)

        talked_to_kael = False
        talked_to_mira = False
        inspected_supply_crate = False
        for action in resolution.applied_actions:
            target_id = str(action.parameters.get("target_id") or action.target_ref or "").strip()
            target_name = str(action.parameters.get("target_name") or "").strip().lower()
            if action.action_type == ActionType.talk:
                if target_id == "npc-circle-binder" or target_name == "kael":
                    talked_to_kael = True
                if target_name == "mira":
                    talked_to_mira = True
            if action.action_type in {ActionType.inspect, ActionType.open, ActionType.search}:
                if "supply-crate" in target_id or target_name == "vorratskiste":
                    inspected_supply_crate = True

        objective_map = {obj.objective_id: obj for obj in quest_copy.objectives}
        if talked_to_kael and "speak_with_kael" in objective_map:
            objective_map["speak_with_kael"].status = "completed"
            objective_map["speak_with_kael"].hint = "Kael hat ein Gespraech gefuehrt; seine Aussagen koennen mit Funden abgeglichen werden."
        if inspected_supply_crate and "inspect_supply_crate" in objective_map:
            objective_map["inspect_supply_crate"].status = "completed"
            objective_map["inspect_supply_crate"].hint = "Die Vorratskiste wurde untersucht; die Funde sollten mit Mira oder Kael abgeglichen werden."

        can_report_to_mira = (
            objective_map.get("speak_with_kael", QuestObjectiveState(objective_id="x", title="x")).status == "completed"
            and objective_map.get("inspect_supply_crate", QuestObjectiveState(objective_id="x", title="x")).status == "completed"
        )
        if "report_to_mira" in objective_map:
            if can_report_to_mira and objective_map["report_to_mira"].status != "completed":
                objective_map["report_to_mira"].hint = "Sprich mit Mira ueber Kaels Aussagen und die Funde aus der Vorratskiste."
            if talked_to_mira and can_report_to_mira:
                objective_map["report_to_mira"].status = "completed"
                objective_map["report_to_mira"].hint = "Mira hat die Funde eingeordnet und neue Ermittlungsansaetze angedeutet."

        all_completed = all(obj.status == "completed" for obj in quest_copy.objectives)
        if all_completed:
            quest_copy.status = "completed"
            quest_copy.current_stage = "completed"
            quest_copy.completed_at = quest_copy.completed_at or now
        elif can_report_to_mira:
            quest_copy.status = "active"
            quest_copy.current_stage = "report_to_mira"
        else:
            quest_copy.status = "active"
            quest_copy.current_stage = "investigate_scene"
        quest_copy.updated_at = now

        after_objectives = {obj.objective_id: obj.status for obj in quest_copy.objectives}
        for objective_id, after_state in after_objectives.items():
            if before_objectives.get(objective_id) == after_state:
                continue
            objective_title = next((obj.title for obj in quest_copy.objectives if obj.objective_id == objective_id), objective_id)
            emitted_events.append(
                TurnSystemEvent(
                    code="quest_objective_updated",
                    message=f"Quest-Fortschritt: {objective_title} ({after_state}).",
                    severity="info",
                    metadata={
                        "quest_id": quest_copy.quest_id,
                        "objective_id": objective_id,
                        "objective_status": after_state,
                    },
                )
            )
        if before_status != quest_copy.status and quest_copy.status == "completed":
            emitted_events.append(
                TurnSystemEvent(
                    code="quest_completed",
                    message=f"Quest abgeschlossen: {quest_copy.title}.",
                    severity="info",
                    metadata={"quest_id": quest_copy.quest_id},
                )
            )

        updated_quests.append(quest_copy)

    return QuestAdvanceResult(quests=updated_quests, system_events=emitted_events)


def build_npc_dialog_hints_for_context(
    *,
    quests: list[WorldQuestState],
    npc_id: str,
    npc_name: str,
    npc_role: str | None,
) -> dict[str, str]:
    if not quests:
        return {}
    for quest in quests:
        if quest.quest_id != URBAN_OCCULT_QUEST_ID or quest.status == "completed":
            continue
        stage = quest.current_stage
        lowered_name = (npc_name or "").strip().lower()
        lowered_role = (npc_role or "").strip().lower()
        if (npc_id == "npc-circle-binder" or lowered_name == "kael" or lowered_role == "beschwoerer") and stage == "investigate_scene":
            return {
                "dialog_state": "quest_hook",
                "dialog_hint": "Kael wirkt angespannt und koennte Hinweise zum gestoerten Ritual geben.",
            }
        if lowered_name == "mira" and stage == "investigate_scene":
            return {
                "dialog_state": "ambient_help",
                "dialog_hint": "Mira beobachtet die Lage ruhig; sie kann nach ersten Funden helfen, sie einzuordnen.",
            }
        if lowered_name == "mira" and stage == "report_to_mira":
            return {
                "dialog_state": "quest_report",
                "dialog_hint": "Mira erwartet einen Abgleich deiner Funde aus Kiste und Gespraech mit Kael.",
            }
    return {}


def derive_story_flags_from_quests(
    *,
    quests: list[WorldQuestState],
    existing_flags: dict[str, str | int | bool] | None = None,
) -> dict[str, str | int | bool]:
    flags: dict[str, str | int | bool] = dict(existing_flags or {})
    if not quests:
        return flags
    for quest in quests:
        if quest.quest_id != URBAN_OCCULT_QUEST_ID:
            continue
        objective_map = {obj.objective_id: obj.status for obj in quest.objectives}
        flags["kael_interviewed"] = objective_map.get("speak_with_kael") == "completed"
        flags["supply_crate_inspected"] = objective_map.get("inspect_supply_crate") == "completed"
        flags["mira_report_completed"] = objective_map.get("report_to_mira") == "completed"
        flags["ritual_scene_known"] = bool(
            flags.get("ritual_scene_known")
            or flags["kael_interviewed"]
            or flags["supply_crate_inspected"]
        )
        flags["ritual_leads_quest_completed"] = quest.status == "completed"
    return flags


def _looks_urban_occult_world_seed(world_seed: WorldSeed) -> bool:
    haystack = " ".join(
        [
            world_seed.name,
            world_seed.summary,
            world_seed.start_hook,
            *world_seed.factions,
            *world_seed.open_threads,
        ]
    ).lower()
    return any(token in haystack for token in ("binder", "ritual", "konklave", "champion", "arkane", "beschwoer"))

