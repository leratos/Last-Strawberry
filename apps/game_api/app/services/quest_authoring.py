from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC

from ls_shared_schemas.quests import QuestObjectiveState, WorldQuestState
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnResolution, TurnSystemEvent
from ls_shared_schemas.world import WorldSeed


URBAN_OCCULT_QUEST_ID = "quest-urban-occult-market-ritual-leads"
URBAN_OCCULT_FOLLOWUP_QUEST_ID = "quest-urban-occult-resonance-followup"


@dataclass(frozen=True)
class QuestAdvanceResult:
    quests: list[WorldQuestState]
    system_events: list[TurnSystemEvent]


def derive_story_flags_from_quests(
    *,
    quests: list[WorldQuestState],
    existing_flags: dict[str, str | int | bool] | None = None,
) -> dict[str, str | int | bool]:
    """Derive stable story flags from quest/objective progression (MVP).

    This keeps `world_story_flags` in sync with quest state without requiring
    a full story-transition engine yet.
    """
    next_flags: dict[str, str | int | bool] = dict(existing_flags or {})

    def _objective_completed(quest: WorldQuestState, objective_id: str) -> bool:
        for objective in quest.objectives:
            if objective.objective_id == objective_id:
                return objective.status == "completed"
        return False

    starter_quest = next((q for q in quests if q.quest_id == URBAN_OCCULT_QUEST_ID), None)
    followup_quest = next((q for q in quests if q.quest_id == URBAN_OCCULT_FOLLOWUP_QUEST_ID), None)

    if starter_quest is not None:
        kael_interviewed = _objective_completed(starter_quest, "speak_with_kael")
        supply_crate_inspected = _objective_completed(starter_quest, "inspect_supply_crate")
        mira_report_completed = _objective_completed(starter_quest, "report_to_mira")
        ritual_leads_quest_completed = starter_quest.status == "completed"

        next_flags["kael_interviewed"] = kael_interviewed
        next_flags["supply_crate_inspected"] = supply_crate_inspected
        next_flags["mira_report_completed"] = mira_report_completed
        next_flags["ritual_leads_quest_completed"] = ritual_leads_quest_completed

        # "Scene known" should stay false at initial seed, but become true once
        # the player meaningfully engages with the starter investigation loop.
        if any((kael_interviewed, supply_crate_inspected, mira_report_completed, ritual_leads_quest_completed)):
            next_flags["ritual_scene_known"] = True

    if followup_quest is not None:
        rune_traces_inspected = _objective_completed(followup_quest, "inspect_rune_traces")
        sealed_case_opened = _objective_completed(followup_quest, "open_sealed_case")
        kael_followup_crosschecked = _objective_completed(followup_quest, "crosscheck_with_kael")
        followup_completed = followup_quest.status == "completed"

        next_flags["ritual_resonance_followup_unlocked"] = True
        next_flags["rune_traces_inspected"] = rune_traces_inspected
        next_flags["sealed_case_opened"] = sealed_case_opened
        next_flags["kael_followup_crosschecked"] = kael_followup_crosschecked
        next_flags["ritual_resonance_followup_completed"] = followup_completed

        if any((rune_traces_inspected, sealed_case_opened, kael_followup_crosschecked, followup_completed)):
            next_flags["ritual_scene_known"] = True

    return next_flags


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


def _make_urban_occult_followup_quest(*, now: datetime | None = None) -> WorldQuestState:
    created_at = now or datetime.now(UTC)
    return WorldQuestState(
        quest_id=URBAN_OCCULT_FOLLOWUP_QUEST_ID,
        title="Resonanzspur am Rand der Gasse",
        description=(
            "Verfolge die zweite Spur des fehlgeschlagenen Rituals: untersuche die verkohlten Runenspuren, "
            "oeffne den versiegelten Instrumentenkoffer und gleiche die Hinweise mit Kael ab."
        ),
        status="active",
        current_stage="trace_residue",
        objectives=[
            QuestObjectiveState(
                objective_id="inspect_rune_traces",
                title="Runenspuren untersuchen",
                status="pending",
                hint="Am Brunnenplatz liegen verkohlte Runenspuren, die zur Stoerung des Rituals passen koennten.",
            ),
            QuestObjectiveState(
                objective_id="open_sealed_case",
                title="Versiegelten Instrumentenkoffer oeffnen",
                status="pending",
                hint="In der Randgasse liegt ein versiegelter Koffer, moeglicherweise mit Ritualwerkzeug.",
            ),
            QuestObjectiveState(
                objective_id="crosscheck_with_kael",
                title="Mit Kael die zweite Spur abgleichen",
                status="pending",
                hint="Kael kann Runenspuren und Fundstuecke aus dem Koffer einordnen.",
            ),
        ],
        tags=["urban_occult", "followup", "investigation"],
        updated_at=created_at,
    )


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
            if quest.quest_id != URBAN_OCCULT_FOLLOWUP_QUEST_ID:
                updated_quests.append(quest)
                continue
            updated_quests.append(_advance_urban_occult_followup_quest(quest=quest, resolution=resolution, now=now, emitted_events=emitted_events))
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
            if not any(existing.quest_id == URBAN_OCCULT_FOLLOWUP_QUEST_ID for existing in quests):
                followup = _make_urban_occult_followup_quest(now=now)
                updated_quests.append(followup)
                emitted_events.append(
                    TurnSystemEvent(
                        code="quest_unlocked",
                        message=f"Neue Spur verfuegbar: {followup.title}.",
                        severity="info",
                        metadata={"quest_id": followup.quest_id},
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
        if quest.status == "completed":
            continue
        stage = quest.current_stage
        lowered_name = (npc_name or "").strip().lower()
        lowered_role = (npc_role or "").strip().lower()
        is_kael = npc_id == "npc-circle-binder" or lowered_name == "kael" or lowered_role == "beschwoerer"
        is_mira = lowered_name == "mira"
        if quest.quest_id == URBAN_OCCULT_QUEST_ID:
            if is_kael and stage == "investigate_scene":
                return {
                    "dialog_state": "quest_hook",
                    "dialog_hint": "Kael wirkt angespannt und koennte Hinweise zum gestoerten Ritual geben.",
                    "dialog_topics_hint": "Ritualstoerung | Augenzeugen | Binder-Konklave",
                }
            if is_mira and stage == "investigate_scene":
                return {
                    "dialog_state": "ambient_help",
                    "dialog_hint": "Mira beobachtet die Lage ruhig; sie kann nach ersten Funden helfen, sie einzuordnen.",
                    "dialog_topics_hint": "Verletzte | Marktstimmung | Beobachtungen",
                }
            if is_mira and stage == "report_to_mira":
                return {
                    "dialog_state": "quest_report",
                    "dialog_hint": "Mira erwartet einen Abgleich deiner Funde aus Kiste und Gespraech mit Kael.",
                    "dialog_topics_hint": "Kistenfund | Kaels Aussage | naechste Spur",
                }
        if quest.quest_id == URBAN_OCCULT_FOLLOWUP_QUEST_ID:
            if is_mira and stage == "trace_residue":
                return {
                    "dialog_state": "followup_guidance",
                    "dialog_hint": "Mira draengt darauf, erst die Spuren und den Koffer zu sichern, bevor ihr Kael erneut konfrontiert.",
                    "dialog_topics_hint": "Runenspuren | Koffer | Deckung halten",
                }
            if is_kael and stage == "trace_residue":
                return {
                    "dialog_state": "followup_suspicious",
                    "dialog_hint": "Kael wirkt kontrolliert, aber ausweichend; belastbare Funde koennten seine Haltung veraendern.",
                    "dialog_topics_hint": "Ritualkreis | Energieausfall | Konklave",
                }
            if is_kael and stage == "crosscheck_with_kael":
                return {
                    "dialog_state": "followup_crosscheck",
                    "dialog_hint": "Kael erwartet einen Abgleich zu Runenspuren und Kofferinhalt. Jetzt lohnt sich gezieltes Nachfragen.",
                    "dialog_topics_hint": "Runensignatur | Instrumentenkoffer | Sabotageverdacht",
                }
    return {}


def _advance_urban_occult_followup_quest(
    *,
    quest: WorldQuestState,
    resolution: TurnResolution,
    now: datetime,
    emitted_events: list[TurnSystemEvent],
) -> WorldQuestState:
    before_status = quest.status
    before_objectives = {obj.objective_id: obj.status for obj in quest.objectives}
    quest_copy = quest.model_copy(deep=True)

    inspected_runes = False
    opened_case = False
    talked_to_kael = False
    for action in resolution.applied_actions:
        target_id = str(action.parameters.get("target_id") or action.target_ref or "").strip()
        target_name = str(action.parameters.get("target_name") or "").strip().lower()
        if action.action_type == ActionType.talk and (target_id == "npc-circle-binder" or target_name == "kael"):
            talked_to_kael = True
        if action.action_type == ActionType.inspect and ("runenspuren" in target_name or "poi-marktplatz-runenspuren" == target_id):
            inspected_runes = True
        if action.action_type in {ActionType.open, ActionType.search} and (
            "obj-marktplatz-siegelkoffer" == target_id or "koffer" in target_name
        ):
            opened_case = True

    objective_map = {obj.objective_id: obj for obj in quest_copy.objectives}
    if inspected_runes and "inspect_rune_traces" in objective_map:
        objective_map["inspect_rune_traces"].status = "completed"
        objective_map["inspect_rune_traces"].hint = "Die Runenspuren wurden gesichert; ihr Verlauf laesst sich nun mit Werkzeug- oder Kofferspuren vergleichen."
    if opened_case and "open_sealed_case" in objective_map:
        objective_map["open_sealed_case"].status = "completed"
        objective_map["open_sealed_case"].hint = "Der Koffer wurde geoeffnet/gesichtet; der Inhalt kann Kael mit der Ritualspur abgleichen."

    can_crosscheck = (
        objective_map.get("inspect_rune_traces", QuestObjectiveState(objective_id="x", title="x")).status == "completed"
        and objective_map.get("open_sealed_case", QuestObjectiveState(objective_id="x", title="x")).status == "completed"
    )
    if "crosscheck_with_kael" in objective_map:
        if can_crosscheck and objective_map["crosscheck_with_kael"].status != "completed":
            objective_map["crosscheck_with_kael"].hint = "Sprich erneut mit Kael und gleiche Runenspuren sowie Kofferinhalt ab."
        if talked_to_kael and can_crosscheck:
            objective_map["crosscheck_with_kael"].status = "completed"
            objective_map["crosscheck_with_kael"].hint = "Kael hat den Abgleich vorgenommen und eine neue Sabotagespur angedeutet."

    all_completed = all(obj.status == "completed" for obj in quest_copy.objectives)
    if all_completed:
        quest_copy.status = "completed"
        quest_copy.current_stage = "completed"
        quest_copy.completed_at = quest_copy.completed_at or now
    elif can_crosscheck:
        quest_copy.status = "active"
        quest_copy.current_stage = "crosscheck_with_kael"
    else:
        quest_copy.status = "active"
        quest_copy.current_stage = "trace_residue"
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
                metadata={"quest_id": quest_copy.quest_id, "objective_id": objective_id, "objective_status": after_state},
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
    return quest_copy


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

