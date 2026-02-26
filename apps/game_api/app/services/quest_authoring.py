from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
import hashlib

from ls_shared_schemas.quests import WorldQuestState
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnResolution, TurnSystemEvent
from ls_shared_schemas.world import WorldSeed
from apps.game_api.app.services.quest_specs import (
    ObjectiveSpec,
    ObjectiveTriggerSpec,
    PredicateSpec,
    QuestSpec,
    TransitionSpec,
    apply_objective_trigger_specs_to_quest_state,
    apply_transition_specs_to_quest_state,
    compile_quest_spec_to_world_state,
    validate_quest_specs_for_activation,
)


URBAN_OCCULT_QUEST_ID = "quest-urban-occult-market-ritual-leads"
URBAN_OCCULT_FOLLOWUP_QUEST_ID = "quest-urban-occult-resonance-followup"


URBAN_OCCULT_STARTER_QUEST_SPEC = QuestSpec(
    quest_id=URBAN_OCCULT_QUEST_ID,
    title="Spuren des fehlgeschlagenen Rituals",
    description=(
        "Finde heraus, was am Marktplatz schiefgelaufen ist: sprich mit Kael, "
        "untersuche die Vorratskiste und gleiche deine Erkenntnisse mit Mira ab."
    ),
    initial_stage="investigate_scene",
    tags=("urban_occult", "starter", "investigation"),
    objectives=(
        ObjectiveSpec(
            objective_id="speak_with_kael",
            title="Mit Kael sprechen",
            hint="Kael wirkt angespannt am Brunnenplatz und weiss vermutlich mehr ueber das Ritual.",
        ),
        ObjectiveSpec(
            objective_id="inspect_supply_crate",
            title="Vorratskiste untersuchen",
            hint="Am Marktplatz gibt es eine Vorratskiste mit moeglichen Hinweisen oder Materialspuren.",
        ),
        ObjectiveSpec(
            objective_id="report_to_mira",
            title="Mit Mira die Funde abgleichen",
            hint="Mira beobachtet die Lage ruhig und kann Hinweise einordnen.",
        ),
    ),
    objective_triggers=(
        ObjectiveTriggerSpec(
            trigger_id="starter_objective_speak_with_kael_by_name",
            objective_id="speak_with_kael",
            predicates=(
                PredicateSpec(
                    predicate_id="talk_kael",
                    kind="action_seen",
                    action_types=("TALK",),
                    target_names=("kael",),
                ),
            ),
            set_hint="Kael hat ein Gespraech gefuehrt; seine Aussagen koennen mit Funden abgeglichen werden.",
            priority=10,
        ),
        ObjectiveTriggerSpec(
            trigger_id="starter_objective_inspect_supply_crate_by_ref",
            objective_id="inspect_supply_crate",
            predicates=(
                PredicateSpec(
                    predicate_id="inspect_supply_crate_ref",
                    kind="action_seen",
                    action_types=("INSPECT", "OPEN", "SEARCH"),
                    target_id_contains=("supply-crate",),
                ),
            ),
            set_hint="Die Vorratskiste wurde untersucht; die Funde sollten mit Mira oder Kael abgeglichen werden.",
            priority=20,
        ),
        ObjectiveTriggerSpec(
            trigger_id="starter_objective_inspect_supply_crate_by_name",
            objective_id="inspect_supply_crate",
            predicates=(
                PredicateSpec(
                    predicate_id="inspect_supply_crate_name",
                    kind="action_seen",
                    action_types=("INSPECT", "OPEN", "SEARCH"),
                    target_names=("vorratskiste",),
                ),
            ),
            set_hint="Die Vorratskiste wurde untersucht; die Funde sollten mit Mira oder Kael abgeglichen werden.",
            priority=21,
        ),
        ObjectiveTriggerSpec(
            trigger_id="starter_objective_report_to_mira",
            objective_id="report_to_mira",
            predicates=(
                PredicateSpec(
                    predicate_id="talk_mira",
                    kind="action_seen",
                    action_types=("TALK",),
                    target_names=("mira",),
                ),
            ),
            requires_objectives_completed=("speak_with_kael", "inspect_supply_crate"),
            set_hint="Mira hat die Funde eingeordnet und neue Ermittlungsansaetze angedeutet.",
            priority=30,
        ),
    ),
    transitions=(
        TransitionSpec(
            transition_id="starter_complete",
            to_stage="completed",
            to_status="completed",
            requires_all_objectives_completed=True,
            priority=10,
        ),
        TransitionSpec(
            transition_id="starter_report_to_mira_stage",
            to_stage="report_to_mira",
            to_status="active",
            requires_objectives_completed=("speak_with_kael", "inspect_supply_crate"),
            objective_hint_updates=(
                ("report_to_mira", "Sprich mit Mira ueber Kaels Aussagen und die Funde aus der Vorratskiste."),
            ),
            priority=20,
        ),
        TransitionSpec(
            transition_id="starter_default_investigate_scene",
            to_stage="investigate_scene",
            to_status="active",
            priority=999,
        ),
    ),
)

URBAN_OCCULT_FOLLOWUP_QUEST_SPEC = QuestSpec(
    quest_id=URBAN_OCCULT_FOLLOWUP_QUEST_ID,
    title="Resonanzspur am Rand der Gasse",
    description=(
        "Verfolge die zweite Spur des fehlgeschlagenen Rituals: untersuche die verkohlten Runenspuren, "
        "oeffne den versiegelten Instrumentenkoffer und gleiche die Hinweise mit Kael ab."
    ),
    initial_stage="trace_residue",
    tags=("urban_occult", "followup", "investigation"),
    objectives=(
        ObjectiveSpec(
            objective_id="inspect_rune_traces",
            title="Runenspuren untersuchen",
            hint="Am Brunnenplatz liegen verkohlte Runenspuren, die zur Stoerung des Rituals passen koennten.",
        ),
        ObjectiveSpec(
            objective_id="open_sealed_case",
            title="Versiegelten Instrumentenkoffer oeffnen",
            hint="In der Randgasse liegt ein versiegelter Koffer, moeglicherweise mit Ritualwerkzeug.",
        ),
        ObjectiveSpec(
            objective_id="crosscheck_with_kael",
            title="Mit Kael die zweite Spur abgleichen",
            hint="Kael kann Runenspuren und Fundstuecke aus dem Koffer einordnen.",
        ),
    ),
    objective_triggers=(
        ObjectiveTriggerSpec(
            trigger_id="followup_objective_inspect_rune_traces_by_ref",
            objective_id="inspect_rune_traces",
            predicates=(
                PredicateSpec(
                    predicate_id="inspect_rune_ref",
                    kind="action_seen",
                    action_types=("INSPECT",),
                    target_ids=("poi-marktplatz-runenspuren",),
                ),
            ),
            set_hint="Die Runenspuren wurden gesichert; ihr Verlauf laesst sich nun mit Werkzeug- oder Kofferspuren vergleichen.",
            priority=10,
        ),
        ObjectiveTriggerSpec(
            trigger_id="followup_objective_inspect_rune_traces_by_name",
            objective_id="inspect_rune_traces",
            predicates=(
                PredicateSpec(
                    predicate_id="inspect_rune_name",
                    kind="action_seen",
                    action_types=("INSPECT",),
                    target_name_contains=("runenspuren",),
                ),
            ),
            set_hint="Die Runenspuren wurden gesichert; ihr Verlauf laesst sich nun mit Werkzeug- oder Kofferspuren vergleichen.",
            priority=11,
        ),
        ObjectiveTriggerSpec(
            trigger_id="followup_objective_open_sealed_case_by_ref",
            objective_id="open_sealed_case",
            predicates=(
                PredicateSpec(
                    predicate_id="open_case_ref",
                    kind="action_seen",
                    action_types=("OPEN", "SEARCH"),
                    target_ids=("obj-marktplatz-siegelkoffer",),
                ),
            ),
            set_hint="Der Koffer wurde geoeffnet/gesichtet; der Inhalt kann Kael mit der Ritualspur abgleichen.",
            priority=20,
        ),
        ObjectiveTriggerSpec(
            trigger_id="followup_objective_open_sealed_case_by_name",
            objective_id="open_sealed_case",
            predicates=(
                PredicateSpec(
                    predicate_id="open_case_name",
                    kind="action_seen",
                    action_types=("OPEN", "SEARCH"),
                    target_name_contains=("koffer",),
                ),
            ),
            set_hint="Der Koffer wurde geoeffnet/gesichtet; der Inhalt kann Kael mit der Ritualspur abgleichen.",
            priority=21,
        ),
    ),
    transitions=(
        TransitionSpec(
            transition_id="followup_complete",
            to_stage="completed",
            to_status="completed",
            requires_all_objectives_completed=True,
            priority=10,
        ),
        TransitionSpec(
            transition_id="followup_crosscheck_stage",
            to_stage="crosscheck_with_kael",
            to_status="active",
            requires_objectives_completed=("inspect_rune_traces", "open_sealed_case"),
            objective_hint_updates=(
                ("crosscheck_with_kael", "Sprich erneut mit Kael und gleiche Runenspuren sowie Kofferinhalt ab."),
            ),
            priority=20,
        ),
        TransitionSpec(
            transition_id="followup_default_trace_residue",
            to_stage="trace_residue",
            to_status="active",
            priority=999,
        ),
    ),
)

AUTHORED_QUEST_SPECS: dict[str, QuestSpec] = {
    URBAN_OCCULT_QUEST_ID: URBAN_OCCULT_STARTER_QUEST_SPEC,
    URBAN_OCCULT_FOLLOWUP_QUEST_ID: URBAN_OCCULT_FOLLOWUP_QUEST_SPEC,
}


def get_authored_quest_spec_registry() -> dict[str, QuestSpec]:
    return dict(AUTHORED_QUEST_SPECS)


def validate_authored_quest_specs() -> tuple[bool, tuple[str, ...]]:
    result = validate_quest_specs_for_activation(list(AUTHORED_QUEST_SPECS.values()), existing_quest_ids=set())
    return result.ok, result.errors


@dataclass(frozen=True)
class QuestAdvanceResult:
    quests: list[WorldQuestState]
    system_events: list[TurnSystemEvent]


@dataclass(frozen=True)
class DialogTopicApplyResult:
    quests: list[WorldQuestState]
    story_flags: dict[str, str | int | bool]
    system_events: list[TurnSystemEvent]


def _dialog_topic_skillcheck_spec(topic_id: str) -> dict[str, str | int] | None:
    specs: dict[str, dict[str, str | int]] = {
        "kael_ritual_overview": {
            "attribute": "intelligence",
            "label": "Ritualanalyse",
            "dc": 12,
        },
        "kael_witness_pattern": {
            "attribute": "charisma",
            "label": "Nachbohren",
            "dc": 11,
        },
        "mira_next_lead": {
            "attribute": "intelligence",
            "label": "Spurlogik",
            "dc": 10,
        },
        "mira_scene_control": {
            "attribute": "dexterity",
            "label": "Sichern ohne Spuren zu stoeren",
            "dc": 12,
        },
        "kael_sabotage_hypothesis": {
            "attribute": "charisma",
            "label": "Konfrontation",
            "dc": 13,
        },
    }
    return specs.get(topic_id)


def _attribute_modifier(attribute_score: int) -> int:
    return (int(attribute_score) - 10) // 2


def _deterministic_d20_roll(*parts: str) -> int:
    seed = "|".join(parts).encode("utf-8", errors="ignore")
    digest = hashlib.sha256(seed).digest()
    return (digest[0] % 20) + 1


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


def build_npc_dialog_topics_for_context(
    *,
    quests: list[WorldQuestState],
    story_flags: dict[str, str | int | bool] | None,
    npc_id: str,
    npc_name: str,
    npc_role: str | None,
) -> list[dict[str, str | int | bool]]:
    if not quests:
        return []
    lowered_name = (npc_name or "").strip().lower()
    lowered_role = (npc_role or "").strip().lower()
    is_kael = npc_id == "npc-circle-binder" or lowered_name == "kael" or lowered_role == "beschwoerer"
    is_mira = lowered_name == "mira"
    flags = dict(story_flags or {})
    followup_clues_ready = bool(flags.get("rune_traces_inspected", False)) and bool(flags.get("sealed_case_opened", False))
    sabotage_topic_used = bool(flags.get("dialog_topic_used_kael_sabotage_hypothesis", False))
    sabotage_skill_used = bool(flags.get("dialog_skillcheck_used_kael_sabotage_hypothesis", False))
    sabotage_skill_passed = bool(flags.get("dialog_skillcheck_passed_kael_sabotage_hypothesis", False))

    topics: list[dict[str, str | int | bool]] = []
    for quest in quests:
        if quest.status == "completed":
            continue
        stage = (quest.current_stage or "").strip().lower()
        if quest.quest_id == URBAN_OCCULT_QUEST_ID:
            if is_kael and stage == "investigate_scene":
                topics.extend(
                    [
                        {
                            "topic_id": "kael_ritual_overview",
                            "label": "Ritualablauf",
                            "summary": "Kael nach dem Ablauf des fehlgeschlagenen Binder-Rituals fragen.",
                            "future_check_attribute": "intelligence",
                            "future_check_label": "Ritualanalyse",
                            "future_check_dc": 12,
                        },
                        {
                            "topic_id": "kael_witness_pattern",
                            "label": "Augenzeugenmuster",
                            "summary": "Kael nach auffaelligen Bewegungen oder Personen fragen.",
                            "future_check_attribute": "charisma",
                            "future_check_label": "Nachbohren",
                            "future_check_dc": 11,
                        },
                    ]
                )
            if is_mira and stage == "report_to_mira":
                topics.extend(
                    [
                        {
                            "topic_id": "mira_crosscheck_findings",
                            "label": "Funde abgleichen",
                            "summary": "Mira um Einordnung von Kistenfund und Kaels Aussage bitten.",
                            "requires_flag": "supply_crate_inspected",
                        },
                        {
                            "topic_id": "mira_next_lead",
                            "label": "Naechste Spur",
                            "summary": "Mira nach einer priorisierten Anschlussspur fragen.",
                            "future_check_attribute": "intelligence",
                            "future_check_label": "Spurlogik",
                            "future_check_dc": 10,
                        },
                    ]
                )
        if quest.quest_id == URBAN_OCCULT_FOLLOWUP_QUEST_ID:
            if is_mira and stage == "trace_residue":
                topics.append(
                    {
                        "topic_id": "mira_scene_control",
                        "label": "Spuren sichern",
                        "summary": "Mit Mira abstimmen, wie Spuren/Koffer abgesichert werden sollten.",
                        "future_check_attribute": "dexterity",
                        "future_check_label": "Sichern ohne Spuren zu stoeren",
                        "future_check_dc": 12,
                    }
                )
            if is_kael and stage in {"trace_residue", "crosscheck_with_kael"}:
                if not sabotage_topic_used:
                    topics.append(
                        {
                            "topic_id": "kael_sabotage_hypothesis",
                            "label": "Sabotageverdacht",
                            "summary": "Kael mit dem Verdacht einer Sabotage konfrontieren.",
                            "future_check_attribute": "charisma",
                            "future_check_label": "Konfrontation",
                            "future_check_dc": 13,
                            "dialog_tree_group": "kael_followup_crosscheck",
                            "dialog_tree_step": 1,
                        }
                    )
                elif stage == "crosscheck_with_kael" and followup_clues_ready and sabotage_skill_used:
                    if sabotage_skill_passed:
                        topics.append(
                            {
                                "topic_id": "kael_crosscheck_press_for_names",
                                "label": "Unter Druck nach Namen fragen",
                                "summary": "Nutze Kaels Unsicherheit aus und verlange konkrete Namen oder Zugangswege.",
                                "followup_of": "kael_sabotage_hypothesis",
                                "followup_condition": "skillcheck_success",
                                "effect_hint": "Kann den Kael-Abgleich abschliessen und eine neue Spur konkretisieren.",
                                "dialog_tree_group": "kael_followup_crosscheck",
                                "dialog_tree_step": 2,
                            }
                        )
                    else:
                        topics.append(
                            {
                                "topic_id": "kael_crosscheck_reframe_with_evidence",
                                "label": "Mit Spuren neu ansetzen",
                                "summary": "Lege Kael die gesicherten Spuren und den Kofferfund vor, um ihn zum Abgleich zu bewegen.",
                                "followup_of": "kael_sabotage_hypothesis",
                                "followup_condition": "skillcheck_failure",
                                "effect_hint": "Fuehrt den Kael-Abgleich trotz Abwehrhaltung weiter.",
                                "dialog_tree_group": "kael_followup_crosscheck",
                                "dialog_tree_step": 2,
                            }
                        )

    # Deduplicate by topic_id while preserving order.
    seen: set[str] = set()
    unique_topics: list[dict[str, str | int | bool]] = []
    for topic in topics:
        topic_id = str(topic.get("topic_id") or "").strip()
        if not topic_id or topic_id in seen:
            continue
        requires_flag = str(topic.get("requires_flag") or "").strip()
        if requires_flag and not bool(flags.get(requires_flag, False)):
            continue
        if bool(flags.get(f"dialog_topic_used_{topic_id}", False)):
            continue
        seen.add(topic_id)
        unique_topics.append(topic)
    return unique_topics


def apply_authored_dialog_topics_for_turn(
    *,
    quests: list[WorldQuestState],
    story_flags: dict[str, str | int | bool] | None,
    resolution: TurnResolution,
) -> DialogTopicApplyResult:
    if not quests:
        return DialogTopicApplyResult(quests=list(quests), story_flags=dict(story_flags or {}), system_events=[])

    updated_quests = [quest.model_copy(deep=True) for quest in quests]
    updated_flags: dict[str, str | int | bool] = dict(story_flags or {})
    events: list[TurnSystemEvent] = []
    now = datetime.now(UTC)
    before_quest_statuses = {quest.quest_id: quest.status for quest in updated_quests}
    before_objective_statuses = {
        (quest.quest_id, objective.objective_id): objective.status
        for quest in updated_quests
        for objective in quest.objectives
    }

    quest_map = {quest.quest_id: quest for quest in updated_quests}
    starter_quest = quest_map.get(URBAN_OCCULT_QUEST_ID)
    followup_quest = quest_map.get(URBAN_OCCULT_FOLLOWUP_QUEST_ID)

    for action in resolution.applied_actions:
        if action.action_type != ActionType.talk:
            continue
        topic_id = str(action.parameters.get("topic_id") or "").strip()
        if not topic_id:
            continue

        flag_key = f"dialog_topic_used_{topic_id}"
        already_used = bool(updated_flags.get(flag_key, False))
        target_name = str(action.parameters.get("target_name") or action.target_ref or "NPC").strip()
        target_ref = str(action.parameters.get("target_id") or action.target_ref or "").strip()
        try:
            target_standing = int(action.parameters.get("target_standing"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            target_standing = 0
        skill_spec = _dialog_topic_skillcheck_spec(topic_id)
        skill_check_result: dict[str, str | int | bool] | None = None
        if skill_spec is not None:
            attr_name = str(skill_spec["attribute"])
            attr_value = int(getattr(resolution.resulting_character_state.attributes, attr_name, 10))
            dc_value = int(skill_spec["dc"])
            roll_value = _deterministic_d20_roll(
                resolution.world_character_id,
                topic_id,
                target_ref or target_name.lower(),
                resolution.resulting_character_state.location_name,
                resolution.resulting_character_state.scene_zone_id,
            )
            modifier_value = _attribute_modifier(attr_value)
            total_value = roll_value + modifier_value
            success_value = total_value >= dc_value
            skill_check_result = {
                "topic_id": topic_id,
                "attribute": attr_name,
                "label": str(skill_spec.get("label") or attr_name),
                "attribute_score": attr_value,
                "modifier": modifier_value,
                "dc": dc_value,
                "roll": roll_value,
                "total": total_value,
                "success": success_value,
            }
            updated_flags[f"dialog_skillcheck_used_{topic_id}"] = True
            updated_flags[f"dialog_skillcheck_passed_{topic_id}"] = success_value
            updated_flags[f"dialog_skillcheck_total_{topic_id}"] = total_value

        response_text = ""
        if topic_id == "kael_ritual_overview":
            updated_flags[flag_key] = True
            updated_flags["kael_ritual_background_heard"] = True
            if starter_quest is not None:
                _update_objective_hint(
                    starter_quest,
                    "speak_with_kael",
                    "Kael schilderte den Ritualablauf; seine Details sollten mit Spuren/Kistenfund abgeglichen werden.",
                )
            response_text = (
                "Kael skizziert den Ablauf des Binder-Rituals und betont, dass der Bruch genau im Umschaltmoment der Energiezufuhr einsetzte."
            )
            if bool(skill_check_result and bool(skill_check_result.get("success"))):
                updated_flags["kael_ritual_analysis_success"] = True
                response_text = (
                    "Waehrend Kael den Ablauf des Binder-Rituals erklaert, erkennst du das stoerende Muster im Umschaltmoment der Energiezufuhr und kannst den Bruch zeitlich enger eingrenzen."
                )
            elif target_standing >= 2:
                updated_flags["kael_shared_circuit_detail"] = True
                response_text = (
                    "Kael schildert den Ablauf des Binder-Rituals ungewoehnlich praezise und nennt sogar den Moment, in dem die Kreise aus dem Takt gerieten."
                )
        elif topic_id == "kael_witness_pattern":
            updated_flags[flag_key] = True
            updated_flags["kael_witness_pattern_heard"] = True
            if target_standing <= 0:
                updated_flags["kael_witness_pattern_partial"] = True
                response_text = (
                    "Kael bleibt vage, bestaetigt aber, dass kurz vor dem Ausfall ungewohnte Bewegungen am Brunnenplatz auffielen."
                )
            else:
                updated_flags["kael_witness_pattern_named"] = True
                response_text = (
                    "Kael erinnert sich an zwei Personen, die kurz vor dem Ausfall auffaellig gegen den Strom am Brunnenplatz vorbeigingen."
                )
        elif topic_id == "mira_crosscheck_findings":
            updated_flags[flag_key] = True
            updated_flags["mira_findings_crosschecked"] = True
            updated_flags["mira_confirms_followup_route"] = True
            if starter_quest is not None:
                _update_objective_hint(
                    starter_quest,
                    "report_to_mira",
                    "Mira hat Kistenfund und Kaels Aussage miteinander abgeglichen und eine zweite Spur priorisiert.",
                )
            response_text = (
                "Mira gleicht deine Funde mit Kaels Aussagen ab und markiert die Runenspuren sowie einen versiegelten Koffer als naechste Prioritaet."
            )
        elif topic_id == "mira_next_lead":
            updated_flags[flag_key] = True
            updated_flags["mira_next_lead_requested"] = True
            updated_flags["followup_route_briefed"] = True
            if bool(skill_check_result and bool(skill_check_result.get("success"))):
                updated_flags["mira_next_lead_analysis_success"] = True
                updated_flags["followup_route_briefed_precise"] = True
                response_text = (
                    "Mira folgt deiner Spurlogik und priorisiert eine klare Reihenfolge: erst Runenspuren sichern, dann den versiegelten Koffer in Deckung oeffnen und zuletzt den Fund mit Kael abgleichen."
                )
            else:
                updated_flags["mira_next_lead_analysis_partial"] = True
                response_text = "Mira empfiehlt, zuerst die sichtbaren Ritualspuren zu sichern und danach den versiegelten Koffer zu untersuchen."
        elif topic_id == "mira_scene_control":
            updated_flags[flag_key] = True
            updated_flags["mira_scene_control_plan"] = True
            updated_flags["scene_control_protocol_active"] = True
            if bool(skill_check_result and bool(skill_check_result.get("success"))):
                updated_flags["scene_control_precision"] = True
                response_text = (
                    "Mira nickt zu deinem vorsichtigen Vorgehen und legt eine praezise Reihenfolge fest: Spuren markieren, Bereich sichern, dann den Koffer kontrolliert in Deckung oeffnen."
                )
            else:
                response_text = "Mira weist dich an, die Spuren zuerst zu sichern und den Koffer erst danach in Deckung zu oeffnen."
            if followup_quest is not None:
                _update_objective_hint(
                    followup_quest,
                    "inspect_rune_traces",
                    "Mira will, dass du die Runenspuren zuerst sicherst, bevor der Koffer geoeffnet wird.",
                )
        elif topic_id == "kael_sabotage_hypothesis":
            updated_flags[flag_key] = True
            updated_flags["kael_sabotage_hypothesis_shared"] = True
            updated_flags["ritual_sabotage_suspected"] = True
            if not already_used:
                try:
                    heat = int(updated_flags.get("occult_heat_level", 1))
                except (TypeError, ValueError):
                    heat = 1
                updated_flags["occult_heat_level"] = min(5, heat + 1)
            if bool(skill_check_result and bool(skill_check_result.get("success"))):
                updated_flags["kael_sabotage_hypothesis_pressure_success"] = True
                if followup_quest is not None:
                    _update_objective_hint(
                        followup_quest,
                        "crosscheck_with_kael",
                        "Kael steht unter Druck. Frage jetzt nach konkreten Namen oder Zugangswegen zum Ritualplatz.",
                    )
                response_text = (
                    "Du setzt Kael gezielt unter Druck und triffst die richtigen Punkte; nach kurzem Zaudern raeumt er ein, dass die Stoerung sehr wahrscheinlich absichtlich gesetzt wurde."
                )
            elif target_standing <= -1:
                updated_flags["kael_defensive_under_pressure"] = True
                if followup_quest is not None:
                    _update_objective_hint(
                        followup_quest,
                        "crosscheck_with_kael",
                        "Kael blockt. Lege ihm Runenspuren und Kofferfund direkt vor, um den Abgleich zu erzwingen.",
                    )
                response_text = (
                    "Kael reagiert gereizt auf den Sabotageverdacht und versucht auszuweichen, bestaetigt aber zwischen den Zeilen eine gezielte Stoerung."
                )
            else:
                if followup_quest is not None:
                    _update_objective_hint(
                        followup_quest,
                        "crosscheck_with_kael",
                        "Kael wirkt angespannt. Ein zweites Nachsetzen mit den gesicherten Hinweisen koennte den Abgleich vervollstaendigen.",
                    )
                response_text = (
                    "Kael reagiert angespannt auf den Sabotageverdacht und raeumt ein, dass die Stoerung eher gesetzt als zufaellig gewesen sein koennte."
                )
        elif topic_id == "kael_crosscheck_press_for_names":
            updated_flags[flag_key] = True
            updated_flags["kael_followup_crosscheck_dialog_resolved"] = True
            updated_flags["kael_named_possible_conclave_access"] = True
            updated_flags["urban_occult_next_hook_ready"] = True
            if followup_quest is not None:
                _update_objective_hint(
                    followup_quest,
                    "crosscheck_with_kael",
                    "Kael nannte moegliche Zugangswege/Namen aus dem Konklave; die zweite Spur ist damit ausgewertet.",
                )
                _mark_objective_completed(followup_quest, "crosscheck_with_kael", now=now)
                _recompute_quest_completion_state(followup_quest, now=now)
            response_text = (
                "Unter dem Druck der Beweise nennt Kael zwei moegliche Zugangswege zum Ritualplatz und deutet an, wer aus dem Konklave davon wusste."
            )
        elif topic_id == "kael_crosscheck_reframe_with_evidence":
            updated_flags[flag_key] = True
            updated_flags["kael_followup_crosscheck_dialog_resolved"] = True
            updated_flags["kael_reluctant_crosscheck_done"] = True
            updated_flags["urban_occult_next_hook_ready"] = True
            if followup_quest is not None:
                _update_objective_hint(
                    followup_quest,
                    "crosscheck_with_kael",
                    "Der Abgleich mit Kael ist abgeschlossen; er bleibt vorsichtig, bestaetigt aber die Relevanz der Spur.",
                )
                _mark_objective_completed(followup_quest, "crosscheck_with_kael", now=now)
                _recompute_quest_completion_state(followup_quest, now=now)
            response_text = (
                "Mit den gesicherten Runenspuren und dem Kofferfund zwingst du Kael zu einem sachlichen Abgleich; widerwillig bestaetigt er, dass die Hinweise zusammenpassen."
            )
        else:
            continue

        events.append(
            TurnSystemEvent(
                code="dialog_topic_applied",
                message=f"Dialog-Thema angewendet: {topic_id}.",
                severity="info",
                metadata={
                    "topic_id": topic_id,
                    "target_name": target_name,
                    "topic_reused": already_used,
                    "target_standing": target_standing,
                },
            )
        )
        if skill_check_result is not None:
            success = bool(skill_check_result["success"])
            label = str(skill_check_result["label"])
            attr_name = str(skill_check_result["attribute"])
            total_value = int(skill_check_result["total"])
            dc_value = int(skill_check_result["dc"])
            roll_value = int(skill_check_result["roll"])
            mod_value = int(skill_check_result["modifier"])
            attr_score = int(skill_check_result["attribute_score"])
            outcome_label = "Erfolg" if success else "Misserfolg"
            events.append(
                TurnSystemEvent(
                    code="dialog_topic_skill_check",
                    message=(
                        f"Probe {label} ({attr_name} {attr_score} / Mod {'+' if mod_value >= 0 else '-'}{abs(mod_value)}) -> {outcome_label}: "
                        f"W20 {roll_value} {'+' if mod_value >= 0 else '-'} {abs(mod_value)} = {total_value} gegen DC {dc_value}."
                    ),
                    severity="info" if success else "warning",
                    metadata={
                        "topic_id": topic_id,
                        "target_name": target_name,
                        "check_label": label,
                        "check_attribute": attr_name,
                        "attribute_score": attr_score,
                        "modifier": mod_value,
                        "roll": roll_value,
                        "total": total_value,
                        "dc": dc_value,
                        "success": success,
                    },
                )
            )
        events.append(
            TurnSystemEvent(
                code="dialog_topic_response",
                message=response_text,
                severity="info",
                metadata={"topic_id": topic_id, "target_name": target_name},
            )
        )

    for quest in updated_quests:
        for objective in quest.objectives:
            before_state = before_objective_statuses.get((quest.quest_id, objective.objective_id))
            if before_state == objective.status:
                continue
            events.append(
                TurnSystemEvent(
                    code="quest_objective_updated",
                    message=f"Quest-Fortschritt: {objective.title} ({objective.status}).",
                    severity="info",
                    metadata={
                        "quest_id": quest.quest_id,
                        "objective_id": objective.objective_id,
                        "objective_status": objective.status,
                        "source": "dialog_topic",
                    },
                )
            )
        if before_quest_statuses.get(quest.quest_id) != quest.status and quest.status == "completed":
            events.append(
                TurnSystemEvent(
                    code="quest_completed",
                    message=f"Quest abgeschlossen: {quest.title}.",
                    severity="info",
                    metadata={"quest_id": quest.quest_id, "source": "dialog_topic"},
                )
            )

    return DialogTopicApplyResult(quests=updated_quests, story_flags=updated_flags, system_events=events)


def _update_objective_hint(quest: WorldQuestState, objective_id: str, hint: str) -> None:
    for objective in quest.objectives:
        if objective.objective_id == objective_id:
            objective.hint = hint
            quest.updated_at = datetime.now(UTC)
            return


def _mark_objective_completed(quest: WorldQuestState, objective_id: str, *, now: datetime) -> None:
    for objective in quest.objectives:
        if objective.objective_id != objective_id:
            continue
        objective.status = "completed"
        quest.updated_at = now
        return


def _recompute_quest_completion_state(quest: WorldQuestState, *, now: datetime) -> None:
    if all(obj.status == "completed" for obj in quest.objectives):
        quest.status = "completed"
        quest.current_stage = "completed"
        quest.completed_at = quest.completed_at or now
        quest.updated_at = now


def initial_quest_states_for_world_seed(world_seed: WorldSeed) -> list[WorldQuestState]:
    if not _looks_urban_occult_world_seed(world_seed):
        return []
    now = datetime.now(UTC)
    return [compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC, now=now)]


def _make_urban_occult_followup_quest(*, now: datetime | None = None) -> WorldQuestState:
    return compile_quest_spec_to_world_state(URBAN_OCCULT_FOLLOWUP_QUEST_SPEC, now=now or datetime.now(UTC))


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
        apply_objective_trigger_specs_to_quest_state(
            quest=quest_copy,
            spec=URBAN_OCCULT_STARTER_QUEST_SPEC,
            resolution=resolution,
            now=now,
        )

        apply_transition_specs_to_quest_state(
            quest=quest_copy,
            spec=URBAN_OCCULT_STARTER_QUEST_SPEC,
            now=now,
        )
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
    apply_objective_trigger_specs_to_quest_state(
        quest=quest_copy,
        spec=URBAN_OCCULT_FOLLOWUP_QUEST_SPEC,
        resolution=resolution,
        now=now,
    )

    apply_transition_specs_to_quest_state(
        quest=quest_copy,
        spec=URBAN_OCCULT_FOLLOWUP_QUEST_SPEC,
        now=now,
    )
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

