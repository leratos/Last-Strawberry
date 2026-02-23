from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from ls_rules_engine import RulesEngine  # noqa: E402
from ls_shared_schemas.character import CharacterAttributes, CharacterResources, CharacterState  # noqa: E402
from ls_shared_schemas.inventory import InventoryItemInstance, ItemEffect, ItemUseMode  # noqa: E402
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnIntentAction  # noqa: E402


class TestRulesEngine(unittest.TestCase):
    def test_resolve_move_and_use_item_updates_state_delta(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Camp",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=4, max_hp=10, stamina=5, max_stamina=10),
        )
        inventory = [
            InventoryItemInstance(
                inventory_item_id="inv-potion-1",
                item_def_id="healing_potion_small",
                name="Kleiner Heiltrank",
                quantity=2,
                use_modes=[ItemUseMode.inspect, ItemUseMode.consume, ItemUseMode.use],
                effects=[ItemEffect(effect_type="heal", stat="hp", amount=4)],
            )
        ]
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich gehe zur Taverne und benutze den Heiltrank.",
            actions=[
                TurnIntentAction(action_type=ActionType.move, destination="Taverne"),
                TurnIntentAction(action_type=ActionType.use_item, item_ref="inv-potion-1"),
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=inventory)

        self.assertEqual(result.resulting_character_state.location_name, "Taverne")
        self.assertEqual(result.state_delta.location_changed_to, "Taverne")
        self.assertEqual(result.resulting_character_state.resources.hp, 8)
        self.assertEqual(result.state_delta.hp_delta, 4)
        self.assertEqual(result.resulting_inventory[0].quantity, 1)
        self.assertEqual(len(result.applied_actions), 2)
        self.assertEqual(len(result.rejected_actions), 0)

    def test_attack_applies_negative_relationship_change(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Gasse",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=3, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich greife Zorak an.",
            actions=[TurnIntentAction(action_type=ActionType.attack, target_ref="Zorak")],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertEqual(result.resulting_character_state.resources.stamina, 2)
        self.assertEqual(result.state_delta.stamina_delta, -1)
        self.assertTrue(result.state_delta.relationship_changes)
        self.assertEqual(result.state_delta.relationship_changes[0]["npc"], "Zorak")
        self.assertEqual(result.state_delta.relationship_changes[0]["standing_delta"], -5)

    def test_talk_auto_approaches_when_target_is_far(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-center",
            scene_zone_name="Brunnenplatz",
            attributes=CharacterAttributes(strength=10, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich frage Mira was sie macht.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.talk,
                    target_ref="npc-mira",
                    target_kind="npc",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_location_name": "Marktplatz",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "far",
                    },
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertEqual(result.resulting_character_state.scene_zone_id, "zone-market-stalls")
        self.assertEqual(result.resulting_character_state.scene_zone_name, "Marktstaende")
        self.assertEqual(result.state_delta.scene_zone_changed_to_id, "zone-market-stalls")
        codes = [event.code for event in result.system_events]
        self.assertIn("auto_approach_for_talk", codes)
        self.assertIn("talk_success", codes)

    def test_attack_auto_approaches_when_target_is_near_or_far(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-center",
            scene_zone_name="Brunnenplatz",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich greife Mira an.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.attack,
                    target_ref="npc-mira",
                    target_kind="npc_or_enemy",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_location_name": "Marktplatz",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "near",
                    },
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertEqual(result.resulting_character_state.scene_zone_id, "zone-market-stalls")
        self.assertEqual(result.state_delta.scene_zone_changed_to_id, "zone-market-stalls")
        self.assertEqual(result.resulting_character_state.resources.stamina, 4)
        codes = [event.code for event in result.system_events]
        self.assertIn("auto_approach_for_attack", codes)
        self.assertIn("attack_resolved", codes)

    def test_attack_rejects_out_of_range_without_position_metadata(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich greife den Bogenschuetzen am anderen Ende an.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.attack,
                    target_ref="Bogenschuetze",
                    parameters={"target_name": "Bogenschuetze", "target_distance_band": "far"},
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertEqual(len(result.applied_actions), 0)
        self.assertEqual(len(result.rejected_actions), 1)
        self.assertEqual(result.resulting_character_state.resources.stamina, 5)
        codes = [event.code for event in result.system_events]
        self.assertIn("attack_out_of_range", codes)

    def test_ranged_attack_does_not_auto_approach_for_far_target(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-center",
            scene_zone_name="Brunnenplatz",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich schiesse auf Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.attack,
                    target_ref="npc-mira",
                    target_kind="npc_or_enemy",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_location_name": "Marktplatz",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "near",
                        "attack_mode": "ranged",
                    },
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertEqual(result.resulting_character_state.scene_zone_id, "zone-market-center")
        codes = [event.code for event in result.system_events]
        self.assertNotIn("auto_approach_for_attack", codes)
        self.assertIn("attack_resolved", codes)
        attack_event = next(event for event in result.system_events if event.code == "attack_resolved")
        self.assertIn("Fernkampf", attack_event.message)

    def test_retreat_from_adjacent_target_changes_zone_and_emits_retreat_success(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-stalls",
            scene_zone_name="Marktstaende",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich entferne mich von Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.retreat,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "adjacent",
                    },
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertNotEqual(result.resulting_character_state.scene_zone_id, "zone-market-stalls")
        self.assertEqual(result.state_delta.scene_zone_changed_to_id, result.resulting_character_state.scene_zone_id)
        codes = [event.code for event in result.system_events]
        self.assertIn("retreat_success", codes)

    def test_retreat_from_near_target_advances_distance_to_far(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-distance-near",
            scene_zone_name="Abstand zu Mira",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich gehe weiter auf Abstand.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.retreat,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "near",
                    },
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        self.assertEqual(result.resulting_character_state.scene_zone_id, "zone-distance-far")
        self.assertEqual(result.state_delta.scene_zone_changed_to_id, "zone-distance-far")
        self.assertIn("Weit weg", result.resulting_character_state.scene_zone_name)
        codes = [event.code for event in result.system_events]
        self.assertIn("retreat_success", codes)

    def test_approach_from_far_target_reduces_distance_to_near(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-distance-far",
            scene_zone_name="Weit weg von Mira",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich gehe auf Mira zu.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "far",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        self.assertEqual(result.resulting_character_state.scene_zone_id, "zone-distance-near")
        self.assertEqual(result.state_delta.scene_zone_changed_to_id, "zone-distance-near")
        self.assertIn("approach_success", [event.code for event in result.system_events])

    def test_approach_from_near_target_reduces_distance_to_adjacent(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-distance-near",
            scene_zone_name="Naeher an Mira",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich naeher mich Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "near",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        self.assertEqual(result.resulting_character_state.scene_zone_id, "zone-market-stalls")
        self.assertEqual(result.state_delta.scene_zone_changed_to_id, "zone-market-stalls")
        self.assertIn("approach_success", [event.code for event in result.system_events])

    def test_approach_emits_aggressive_reaction_for_hostile_target(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-distance-far",
            scene_zone_name="Weit weg von Mira",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich naeher mich Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "far",
                        "target_standing": -5,
                        "target_role": "tank",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        codes = [event.code for event in result.system_events]
        self.assertIn("approach_success", codes)
        self.assertIn("npc_reacts_aggressive_to_approach", codes)
        reaction_event = next(event for event in result.system_events if event.code == "npc_reacts_aggressive_to_approach")
        self.assertIn("Tank", reaction_event.message)

    def test_retreat_emits_aggressive_reaction_note_for_hostile_target(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-stalls",
            scene_zone_name="Marktstaende",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich halte Abstand zu Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.retreat,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "adjacent",
                        "target_standing": -4,
                        "target_role": "krieger",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        codes = [event.code for event in result.system_events]
        self.assertIn("retreat_success", codes)
        self.assertIn("npc_reacts_aggressive_to_retreat", codes)

    def test_clarify_event_preserves_metadata_from_action_parameters(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            attributes=CharacterAttributes(strength=10, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=10, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich rede mit dem Beschwoerer.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.clarify,
                    parameters={
                        "reason": "ambiguous_npc_role_title",
                        "message": "Bitte waehle: Kael oder Liora.",
                        "suggested_action": "select_visible_npc",
                        "candidates_json": '[{"action_type":"TALK","target_ref":"npc-kael","label":"Kael"}]',
                    },
                )
            ],
        )

        result = engine.resolve(intent=intent, character_state=state, inventory=[])

        clarify_event = next(event for event in result.system_events if event.code == "clarify_required")
        self.assertEqual(clarify_event.message, "Bitte waehle: Kael oder Liora.")
        self.assertEqual(clarify_event.metadata.get("reason"), "ambiguous_npc_role_title")
        self.assertEqual(clarify_event.metadata.get("suggested_action"), "select_visible_npc")
        self.assertEqual(clarify_event.metadata.get("candidate_count"), 1)

    def test_approach_emits_friendly_reaction_for_positive_standing(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-distance-near",
            scene_zone_name="Naeher an Mira",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich trete naeher an Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "near",
                        "target_standing": 4,
                        "target_role": "healer",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        codes = [event.code for event in result.system_events]
        self.assertIn("approach_success", codes)
        self.assertIn("npc_reacts_friendly_to_approach", codes)
        reaction_event = next(event for event in result.system_events if event.code == "npc_reacts_friendly_to_approach")
        self.assertIn("Heiler", reaction_event.message)

    def test_retreat_emits_cautious_reaction_for_neutral_negative_standing(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-stalls",
            scene_zone_name="Marktstaende",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich halte Abstand zu Mira.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.retreat,
                    target_ref="npc-mira",
                    parameters={
                        "target_id": "npc-mira",
                        "target_name": "Mira",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "adjacent",
                        "target_standing": -1,
                        "target_role": "healer",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        self.assertIn("npc_reacts_cautious_to_retreat", [event.code for event in result.system_events])

    def test_approach_friendly_merchant_message_mentions_haendler(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-distance-near",
            scene_zone_name="Naeher an Harl",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich gehe auf Harl zu.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref="npc-harl",
                    parameters={
                        "target_name": "Harl",
                        "target_zone_id": "zone-market-stalls",
                        "target_zone_name": "Marktstaende",
                        "target_distance_band": "near",
                        "target_standing": 2,
                        "target_role": "haendler",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        reaction_event = next(event for event in result.system_events if event.code == "npc_reacts_friendly_to_approach")
        self.assertIn("Haendler", reaction_event.message)

    def test_approach_cautious_mage_message_mentions_arcane(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Archiv",
            scene_zone_id="zone-distance-far",
            scene_zone_name="Weit weg von Elra",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich naeher mich Elra.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref="npc-elra",
                    parameters={
                        "target_name": "Elra",
                        "target_zone_id": "zone-ritual",
                        "target_zone_name": "Ritualkreis",
                        "target_distance_band": "far",
                        "target_standing": 1,
                        "target_role": "magier",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        reaction_event = next(event for event in result.system_events if event.code == "npc_reacts_cautious_to_approach")
        self.assertIn("arkaner", reaction_event.message)

    def test_retreat_aggressive_summoner_message_mentions_beschwoerung(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Katakomben",
            scene_zone_id="zone-ritual",
            scene_zone_name="Ritualkreis",
            attributes=CharacterAttributes(strength=12, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=5, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich halte Abstand zu Vorun.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.retreat,
                    target_ref="npc-vorun",
                    parameters={
                        "target_name": "Vorun",
                        "target_zone_id": "zone-ritual",
                        "target_zone_name": "Ritualkreis",
                        "target_distance_band": "adjacent",
                        "target_standing": -5,
                        "target_role": "beschwoerer",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        reaction_event = next(event for event in result.system_events if event.code == "npc_reacts_aggressive_to_retreat")
        self.assertIn("Beschwoerungsenergie", reaction_event.message)

    def test_inspect_scene_point_emits_focus_success(self):
        engine = RulesEngine()
        state = CharacterState(
            world_character_id="wc-1",
            name="Ari",
            location_name="Marktplatz",
            scene_zone_id="zone-market-center",
            scene_zone_name="Brunnenplatz",
            attributes=CharacterAttributes(strength=10, dexterity=10, intelligence=10, charisma=10),
            resources=CharacterResources(hp=10, max_hp=10, stamina=10, max_stamina=10),
        )
        intent = TurnIntent(
            world_id="world-1",
            world_character_id="wc-1",
            raw_player_input="Ich untersuche die Runenspuren.",
            actions=[
                TurnIntentAction(
                    action_type=ActionType.inspect,
                    target_ref="poi-marktplatz-runenspuren",
                    target_kind="scene_point",
                    parameters={
                        "target_name": "Verkohlte Runenspuren",
                        "target_kind": "scene_point",
                    },
                )
            ],
        )
        result = engine.resolve(intent=intent, character_state=state, inventory=[])
        self.assertIn("inspect_focus_success", [event.code for event in result.system_events])


if __name__ == "__main__":
    unittest.main()
