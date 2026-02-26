from __future__ import annotations

from datetime import UTC, datetime
import unittest

from ls_shared_schemas.character import CharacterState
from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.turns import ActionType, StateDelta, TurnIntentAction, TurnResolution, TurnSystemEvent

from apps.game_api.app.services.quest_authoring import (
    URBAN_OCCULT_FOLLOWUP_QUEST_SPEC,
    URBAN_OCCULT_STARTER_QUEST_SPEC,
    validate_authored_quest_specs,
)
from apps.game_api.app.services.quest_specs import (
    EffectSpec,
    ObjectiveSpec,
    ObjectiveTriggerSpec,
    PredicateSpec,
    QuestSpec,
    TransitionSpec,
    apply_effect_specs,
    apply_objective_trigger_specs_to_quest_state,
    apply_transition_specs_to_quest_state,
    compile_quest_spec_to_world_state,
    validate_quest_spec,
    validate_quest_specs_for_activation,
)


class TestQuestSpecs(unittest.TestCase):
    def _resolution_with_actions(self, *actions: TurnIntentAction) -> TurnResolution:
        return TurnResolution(
            world_id="world-test",
            world_character_id="wc-test",
            applied_actions=list(actions),
            rejected_actions=[],
            system_events=[],
            resulting_character_state=CharacterState(
                world_character_id="wc-test",
                name="Tester",
                location_name="Marktplatz",
                scene_zone_id="zone-brunnenplatz",
                scene_zone_name="Brunnenplatz",
            ),
            resulting_inventory=[],
        )

    def _resolution_full(
        self,
        *,
        actions: list[TurnIntentAction] | None = None,
        system_events: list[TurnSystemEvent] | None = None,
        state_delta: StateDelta | None = None,
        inventory: list[InventoryItemInstance] | None = None,
    ) -> TurnResolution:
        return TurnResolution(
            world_id="world-test",
            world_character_id="wc-test",
            applied_actions=list(actions or []),
            rejected_actions=[],
            system_events=list(system_events or []),
            state_delta=state_delta or StateDelta(),
            resulting_character_state=CharacterState(
                world_character_id="wc-test",
                name="Tester",
                location_name="Marktplatz",
                scene_zone_id="zone-brunnenplatz",
                scene_zone_name="Brunnenplatz",
            ),
            resulting_inventory=list(inventory or []),
        )

    def test_compile_quest_spec_to_world_state_preserves_structure(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC, now=now)

        self.assertEqual(quest_state.quest_id, URBAN_OCCULT_STARTER_QUEST_SPEC.quest_id)
        self.assertEqual(quest_state.current_stage, "investigate_scene")
        self.assertEqual(quest_state.status, "active")
        self.assertEqual(len(quest_state.objectives), 3)
        self.assertEqual(quest_state.updated_at, now)
        self.assertTrue(all(obj.status == "pending" for obj in quest_state.objectives))

    def test_validate_authored_quest_specs_is_ok(self):
        ok, errors = validate_authored_quest_specs()
        self.assertTrue(ok)
        self.assertEqual(errors, ())

    def test_validate_quest_spec_detects_duplicate_objective_id(self):
        spec = QuestSpec(
            quest_id="quest-test-dup",
            title="Dup",
            description="Dup",
            initial_stage="start",
            tags=("test",),
            objectives=(
                ObjectiveSpec(objective_id="dup", title="A", hint="a"),
                ObjectiveSpec(objective_id="dup", title="B", hint="b"),
            ),
            transitions=(),
        )
        result = validate_quest_spec(spec)
        self.assertFalse(result.ok)
        self.assertIn("duplicate_objective_id:dup", result.errors)

    def test_validate_quest_spec_detects_unknown_objective_trigger_reference(self):
        spec = QuestSpec(
            quest_id="quest-test-trigger",
            title="Trigger Test",
            description="Trigger Test",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="obj-a", title="A", hint="a"),),
            objective_triggers=(
                # invalid objective_id on purpose
                ObjectiveTriggerSpec(
                    trigger_id="trig-a",
                    objective_id="obj-missing",
                    predicates=(
                        PredicateSpec(
                            predicate_id="pred-a",
                            kind="action_seen",
                            action_types=("TALK",),
                        ),
                    ),
                ),
            ),
            transitions=(),
        )
        result = validate_quest_spec(spec)
        self.assertFalse(result.ok)
        self.assertIn("objective_trigger_unknown_objective:trig-a:obj-missing", result.errors)

    def test_validate_quest_spec_detects_invalid_effect_specs(self):
        spec = QuestSpec(
            quest_id="quest-test-effects",
            title="Effect Validation",
            description="Effect validation.",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="obj-a", title="A", hint="a"),),
            objective_triggers=(
                ObjectiveTriggerSpec(
                    trigger_id="trig-invalid-effect",
                    objective_id="obj-a",
                    predicates=(
                        PredicateSpec(
                            predicate_id="pred-a",
                            kind="story_flag_true",
                            flag_name="flag_a",
                        ),
                    ),
                    effects=(
                        EffectSpec(
                            effect_id="bad-trigger-effect",
                            kind="emit_system_event",
                            params={"code": "missing_message"},
                        ),
                    ),
                ),
            ),
            transitions=(
                TransitionSpec(
                    transition_id="transition-invalid-effect",
                    to_stage="next",
                    effects=(
                        EffectSpec(
                            effect_id="bad-transition-effect",
                            kind="increment_story_flag",
                            params={"flag_name": "heat"},
                        ),
                    ),
                ),
            ),
        )
        result = validate_quest_spec(spec)
        self.assertFalse(result.ok)
        self.assertIn(
            "trigger_effect_error:trig-invalid-effect:effect_missing_event_message:bad-trigger-effect",
            result.errors,
        )
        self.assertIn(
            "transition_effect_error:transition-invalid-effect:effect_increment_step_invalid:bad-transition-effect",
            result.errors,
        )

    def test_validate_quest_specs_for_activation_detects_unknown_effect_target_quest(self):
        spec = QuestSpec(
            quest_id="quest-a",
            title="A",
            description="A",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="obj-a", title="A", hint="a"),),
            transitions=(
                TransitionSpec(
                    transition_id="to-next",
                    to_stage="next",
                    effects=(
                        EffectSpec(
                            effect_id="set-state-external",
                            kind="set_quest_state",
                            params={"quest_id": "quest-missing", "stage": "active_elsewhere"},
                        ),
                    ),
                ),
            ),
        )
        result = validate_quest_specs_for_activation([spec], existing_quest_ids=set())
        self.assertFalse(result.ok)
        self.assertIn(
            "transition_effect_error:to-next:effect_unknown_target_quest:set-state-external:quest-missing",
            result.errors,
        )

    def test_validate_quest_specs_for_activation_allows_cross_quest_objective_effect_when_target_exists(self):
        spec_a = QuestSpec(
            quest_id="quest-a",
            title="A",
            description="A",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="obj-a", title="A", hint="a"),),
            transitions=(
                TransitionSpec(
                    transition_id="sync-b",
                    to_stage="next",
                    effects=(
                        EffectSpec(
                            effect_id="activate-b-objective",
                            kind="set_objective_status",
                            params={
                                "quest_id": "quest-b",
                                "objective_id": "obj-b",
                                "status": "active",
                            },
                        ),
                    ),
                ),
            ),
        )
        spec_b = QuestSpec(
            quest_id="quest-b",
            title="B",
            description="B",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="obj-b", title="B", hint="b"),),
        )
        result = validate_quest_specs_for_activation([spec_a, spec_b], existing_quest_ids=set())
        self.assertTrue(result.ok)
        self.assertEqual(result.errors, ())

    def test_apply_objective_trigger_specs_completes_starter_objectives_from_actions(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC, now=now)
        resolution = self._resolution_with_actions(
            TurnIntentAction(
                action_type=ActionType.talk,
                target_ref="npc-circle-binder",
                parameters={"target_id": "npc-circle-binder", "target_name": "Kael"},
            ),
            TurnIntentAction(
                action_type=ActionType.inspect,
                target_ref="poi-marktplatz-supply-crate",
                target_kind="container",
                parameters={
                    "target_id": "poi-marktplatz-supply-crate",
                    "target_name": "Vorratskiste",
                    "target_kind": "container",
                },
            ),
        )

        fired = apply_objective_trigger_specs_to_quest_state(
            quest=quest_state,
            spec=URBAN_OCCULT_STARTER_QUEST_SPEC,
            resolution=resolution,
            now=now,
        )

        objective_map = {obj.objective_id: obj for obj in quest_state.objectives}
        self.assertEqual(objective_map["speak_with_kael"].status, "completed")
        self.assertEqual(objective_map["inspect_supply_crate"].status, "completed")
        self.assertEqual(objective_map["report_to_mira"].status, "pending")
        self.assertIn("starter_objective_speak_with_kael_by_name", fired)
        self.assertIn("starter_objective_inspect_supply_crate_by_ref", fired)

    def test_apply_objective_trigger_specs_respects_objective_prerequisites(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC, now=now)
        resolution = self._resolution_with_actions(
            TurnIntentAction(
                action_type=ActionType.talk,
                target_ref="npc-mira",
                parameters={"target_id": "npc-mira", "target_name": "Mira"},
            )
        )

        fired = apply_objective_trigger_specs_to_quest_state(
            quest=quest_state,
            spec=URBAN_OCCULT_STARTER_QUEST_SPEC,
            resolution=resolution,
            now=now,
        )

        objective_map = {obj.objective_id: obj for obj in quest_state.objectives}
        self.assertEqual(objective_map["report_to_mira"].status, "pending")
        self.assertNotIn("starter_objective_report_to_mira", fired)

    def test_apply_objective_trigger_specs_supports_system_event_predicate(self):
        spec = QuestSpec(
            quest_id="quest-discovery",
            title="Discovery Test",
            description="Discovery predicate test.",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="discover_scene", title="Discover", hint=""),),
            objective_triggers=(
                ObjectiveTriggerSpec(
                    trigger_id="discover-by-event",
                    objective_id="discover_scene",
                    predicates=(
                        PredicateSpec(
                            predicate_id="event-discovery",
                            kind="system_event_seen",
                            event_codes=("discovery_revealed_scene_points",),
                        ),
                    ),
                ),
            ),
        )
        quest_state = compile_quest_spec_to_world_state(spec)
        resolution = self._resolution_full(
            system_events=[
                TurnSystemEvent(code="discovery_revealed_scene_points", message="Neue Interaktionspunkte entdeckt.", severity="info")
            ]
        )
        fired = apply_objective_trigger_specs_to_quest_state(quest=quest_state, spec=spec, resolution=resolution)
        self.assertEqual(quest_state.objectives[0].status, "completed")
        self.assertIn("discover-by-event", fired)

    def test_apply_objective_trigger_specs_supports_inventory_predicates(self):
        spec = QuestSpec(
            quest_id="quest-inventory",
            title="Inventory Test",
            description="Inventory predicate test.",
            initial_stage="start",
            tags=("test",),
            objectives=(
                ObjectiveSpec(objective_id="has_bandage", title="Bandage", hint=""),
                ObjectiveSpec(objective_id="found_bandage_now", title="Found Now", hint=""),
            ),
            objective_triggers=(
                ObjectiveTriggerSpec(
                    trigger_id="has-item-present",
                    objective_id="has_bandage",
                    predicates=(
                        PredicateSpec(
                            predicate_id="inv-present",
                            kind="inventory_item_present",
                            inventory_item_names=("Verbandspaket",),
                            inventory_min_quantity=1,
                        ),
                    ),
                    priority=10,
                ),
                ObjectiveTriggerSpec(
                    trigger_id="item-gained-delta",
                    objective_id="found_bandage_now",
                    predicates=(
                        PredicateSpec(
                            predicate_id="inv-gain",
                            kind="inventory_delta_seen",
                            inventory_delta_kind="gained",
                            inventory_item_name_contains=("verband",),
                        ),
                    ),
                    priority=20,
                ),
            ),
        )
        quest_state = compile_quest_spec_to_world_state(spec)
        resolution = self._resolution_full(
            state_delta=StateDelta(
                inventory_gained=[{"item_def_id": "item-bandage", "name": "Verbandspaket", "quantity": 1}]
            ),
            inventory=[
                InventoryItemInstance(
                    inventory_item_id="inv-bandage-1",
                    item_def_id="item-bandage",
                    name="Verbandspaket",
                    category="healing",
                    quantity=1,
                )
            ],
        )
        fired = apply_objective_trigger_specs_to_quest_state(quest=quest_state, spec=spec, resolution=resolution)
        objective_map = {obj.objective_id: obj.status for obj in quest_state.objectives}
        self.assertEqual(objective_map["has_bandage"], "completed")
        self.assertEqual(objective_map["found_bandage_now"], "completed")
        self.assertIn("has-item-present", fired)
        self.assertIn("item-gained-delta", fired)

    def test_apply_objective_trigger_specs_supports_relationship_and_action_role_predicates(self):
        spec = QuestSpec(
            quest_id="quest-npc",
            title="NPC Test",
            description="NPC predicate test.",
            initial_stage="start",
            tags=("test",),
            objectives=(
                ObjectiveSpec(objective_id="talk_to_summoner", title="Talk", hint=""),
                ObjectiveSpec(objective_id="gain_trust", title="Trust", hint=""),
            ),
            objective_triggers=(
                ObjectiveTriggerSpec(
                    trigger_id="talk-summoner-role",
                    objective_id="talk_to_summoner",
                    predicates=(
                        PredicateSpec(
                            predicate_id="action-talk-role",
                            kind="action_seen",
                            action_types=("TALK",),
                            target_roles=("beschwoerer",),
                        ),
                    ),
                    priority=10,
                ),
                ObjectiveTriggerSpec(
                    trigger_id="relationship-positive-kael",
                    objective_id="gain_trust",
                    predicates=(
                        PredicateSpec(
                            predicate_id="rel-positive",
                            kind="relationship_change_seen",
                            relationship_npc_ids=("npc-circle-binder",),
                            relationship_delta_sign="positive",
                            relationship_min_delta=1,
                        ),
                    ),
                    priority=20,
                ),
            ),
        )
        quest_state = compile_quest_spec_to_world_state(spec)
        resolution = self._resolution_full(
            actions=[
                TurnIntentAction(
                    action_type=ActionType.talk,
                    target_ref="npc-circle-binder",
                    parameters={
                        "target_id": "npc-circle-binder",
                        "target_name": "Kael",
                        "target_role": "beschwoerer",
                    },
                )
            ],
            state_delta=StateDelta(
                relationship_changes=[{"npc_id": "npc-circle-binder", "npc": "Kael", "standing_delta": 1}]
            ),
        )
        fired = apply_objective_trigger_specs_to_quest_state(quest=quest_state, spec=spec, resolution=resolution)
        objective_map = {obj.objective_id: obj.status for obj in quest_state.objectives}
        self.assertEqual(objective_map["talk_to_summoner"], "completed")
        self.assertEqual(objective_map["gain_trust"], "completed")
        self.assertIn("talk-summoner-role", fired)
        self.assertIn("relationship-positive-kael", fired)

    def test_apply_effect_specs_updates_story_flags_and_emits_event(self):
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC)
        flags: dict[str, str | int | bool] = {}
        events = apply_effect_specs(
            effects=(
                EffectSpec(
                    effect_id="set-flag",
                    kind="set_story_flag",
                    params={"flag_name": "test_flag", "value": True},
                    priority=10,
                ),
                EffectSpec(
                    effect_id="inc-flag",
                    kind="increment_story_flag",
                    params={"flag_name": "heat", "step": 2},
                    priority=20,
                ),
                EffectSpec(
                    effect_id="emit",
                    kind="emit_system_event",
                    params={"code": "test_effect_applied", "message": "Effect ran.", "severity": "info"},
                    priority=30,
                ),
            ),
            current_quest=quest_state,
            all_quests={quest_state.quest_id: quest_state},
            story_flags=flags,
        )
        self.assertTrue(flags["test_flag"])
        self.assertEqual(flags["heat"], 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].code, "test_effect_applied")

    def test_apply_effect_specs_can_update_objective_hint(self):
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC)
        updated_hint = "Neue authored Hint-Zeile."
        apply_effect_specs(
            effects=(
                EffectSpec(
                    effect_id="hint",
                    kind="set_objective_hint",
                    params={
                        "objective_id": "speak_with_kael",
                        "hint": updated_hint,
                    },
                ),
            ),
            current_quest=quest_state,
            all_quests={quest_state.quest_id: quest_state},
            story_flags={},
        )
        objective_map = {obj.objective_id: obj for obj in quest_state.objectives}
        self.assertEqual(objective_map["speak_with_kael"].hint, updated_hint)

    def test_apply_trigger_and_transition_effects_can_emit_events(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        spec = QuestSpec(
            quest_id="quest-effects",
            title="Effects",
            description="Effects.",
            initial_stage="start",
            tags=("test",),
            objectives=(ObjectiveSpec(objective_id="obj-a", title="A", hint="a"),),
            objective_triggers=(
                ObjectiveTriggerSpec(
                    trigger_id="trigger-a",
                    objective_id="obj-a",
                    predicates=(
                        PredicateSpec(
                            predicate_id="pred-a",
                            kind="action_seen",
                            action_types=("TALK",),
                        ),
                    ),
                    effects=(
                        EffectSpec(
                            effect_id="trigger-event",
                            kind="emit_system_event",
                            params={
                                "code": "trigger_effect_event",
                                "message": "Trigger effect emitted.",
                            },
                        ),
                    ),
                ),
            ),
            transitions=(
                TransitionSpec(
                    transition_id="transition-complete",
                    to_stage="completed",
                    to_status="completed",
                    requires_all_objectives_completed=True,
                    effects=(
                        EffectSpec(
                            effect_id="transition-event",
                            kind="emit_system_event",
                            params={
                                "code": "transition_effect_event",
                                "message": "Transition effect emitted.",
                            },
                        ),
                    ),
                ),
            ),
        )
        quest_state = compile_quest_spec_to_world_state(spec, now=now)
        events: list[TurnSystemEvent] = []
        resolution = self._resolution_with_actions(
            TurnIntentAction(action_type=ActionType.talk, target_ref="npc-any"),
        )
        fired = apply_objective_trigger_specs_to_quest_state(
            quest=quest_state,
            spec=spec,
            resolution=resolution,
            emitted_events=events,
            now=now,
        )
        self.assertIn("trigger-a", fired)
        self.assertEqual(events[0].code, "trigger_effect_event")

        apply_transition_specs_to_quest_state(
            quest=quest_state,
            spec=spec,
            emitted_events=events,
            now=now,
        )
        self.assertEqual(quest_state.status, "completed")
        self.assertEqual(events[1].code, "transition_effect_event")

    def test_apply_transition_specs_moves_followup_to_crosscheck_when_clues_ready(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_FOLLOWUP_QUEST_SPEC, now=now)
        objective_map = {obj.objective_id: obj for obj in quest_state.objectives}
        objective_map["inspect_rune_traces"].status = "completed"
        objective_map["open_sealed_case"].status = "completed"
        objective_map["crosscheck_with_kael"].status = "pending"

        apply_transition_specs_to_quest_state(
            quest=quest_state,
            spec=URBAN_OCCULT_FOLLOWUP_QUEST_SPEC,
            now=now,
        )

        self.assertEqual(quest_state.current_stage, "crosscheck_with_kael")
        self.assertEqual(quest_state.status, "active")
        self.assertIn("Runenspuren", str(objective_map["crosscheck_with_kael"].hint))

    def test_authored_starter_transition_sets_story_flag_and_objective_status(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_STARTER_QUEST_SPEC, now=now)
        objective_map = {obj.objective_id: obj for obj in quest_state.objectives}
        objective_map["speak_with_kael"].status = "completed"
        objective_map["inspect_supply_crate"].status = "completed"
        objective_map["report_to_mira"].status = "pending"
        flags: dict[str, str | int | bool] = {}
        events: list[TurnSystemEvent] = []

        apply_transition_specs_to_quest_state(
            quest=quest_state,
            spec=URBAN_OCCULT_STARTER_QUEST_SPEC,
            story_flags=flags,
            mutable_story_flags=flags,
            emitted_events=events,
            now=now,
        )

        self.assertEqual(quest_state.current_stage, "report_to_mira")
        self.assertEqual(objective_map["report_to_mira"].status, "active")
        self.assertTrue(bool(flags.get("quest_report_to_mira_ready")))
        self.assertTrue(any(event.code == "quest_stage_shifted" for event in events))

    def test_apply_transition_specs_completes_quest_when_all_objectives_complete(self):
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        quest_state = compile_quest_spec_to_world_state(URBAN_OCCULT_FOLLOWUP_QUEST_SPEC, now=now)
        for objective in quest_state.objectives:
            objective.status = "completed"

        apply_transition_specs_to_quest_state(
            quest=quest_state,
            spec=URBAN_OCCULT_FOLLOWUP_QUEST_SPEC,
            now=now,
        )

        self.assertEqual(quest_state.status, "completed")
        self.assertEqual(quest_state.current_stage, "completed")
        self.assertIsNotNone(quest_state.completed_at)


if __name__ == "__main__":
    unittest.main()
