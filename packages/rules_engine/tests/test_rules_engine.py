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


if __name__ == "__main__":
    unittest.main()
