from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))

from apps.game_api.app.services.intent_analysis_preview import analyze_player_input_preview  # noqa: E402
from ls_shared_schemas.inventory import InventoryItemInstance, ItemUseMode  # noqa: E402


class TestIntentAnalysisPreview(unittest.TestCase):
    def test_detects_move_and_use_item(self):
        inventory = [
            InventoryItemInstance(
                inventory_item_id="inv-1",
                item_def_id="starter_healing_draught",
                name="Starter-Heiltrank",
                use_modes=[ItemUseMode.inspect, ItemUseMode.consume, ItemUseMode.use],
                quantity=1,
            )
        ]
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich gehe zur Taverne und benutze den Starter-Heiltrank.",
            inventory=inventory,
        )

        action_types = [action.action_type.value for action in intent.actions]
        self.assertIn("MOVE", action_types)
        self.assertIn("USE_ITEM", action_types)
        self.assertIn("Bewegungsziel erkannt", " ".join(intent.analysis_notes))

    def test_prefers_ids_for_known_targets(self):
        inventory = [
            InventoryItemInstance(
                inventory_item_id="inv-abc123",
                item_def_id="starter_healing_draught",
                name="Starter-Heiltrank",
                use_modes=[ItemUseMode.inspect, ItemUseMode.consume, ItemUseMode.use],
                quantity=1,
            )
        ]
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich gehe zur Taverne, spreche mit Zorak und benutze den Starter-Heiltrank.",
            inventory=inventory,
            known_npc_names=["Zorak"],
            known_locations=["Taverne"],
            known_npc_refs=[{"ref_id": "npc-zorak", "name": "Zorak"}],
            known_location_refs=[{"ref_id": "loc-taverne", "name": "Taverne"}],
        )
        move_action = next(action for action in intent.actions if action.action_type.value == "MOVE")
        talk_action = next(action for action in intent.actions if action.action_type.value == "TALK")
        use_action = next(action for action in intent.actions if action.action_type.value == "USE_ITEM")

        self.assertEqual(move_action.destination, "Taverne")
        self.assertEqual(move_action.target_ref, "loc-taverne")
        self.assertEqual(move_action.parameters.get("destination_id"), "loc-taverne")
        self.assertEqual(talk_action.target_ref, "npc-zorak")
        self.assertEqual(talk_action.parameters.get("target_name"), "Zorak")
        self.assertEqual(talk_action.parameters.get("target_id"), "npc-zorak")
        self.assertEqual(use_action.item_ref, "inv-abc123")
        self.assertEqual(use_action.parameters.get("item_id"), "inv-abc123")

    def test_falls_back_to_clarify(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Hmm...",
            inventory=[],
        )
        self.assertEqual(len(intent.actions), 1)
        self.assertEqual(intent.actions[0].action_type.value, "CLARIFY")

    def test_schaue_does_not_false_positive_attack(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich schaue mich vorsichtig um und suche nach Hinweisen.",
            inventory=[],
        )
        action_types = [action.action_type.value for action in intent.actions]
        self.assertNotIn("ATTACK", action_types)
        self.assertIn("INSPECT", action_types)

    def test_detects_move_phrase_bewege_mich_zu(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich bewege mich zu Sera und frage sie was sie macht.",
            inventory=[],
        )
        action_types = [action.action_type.value for action in intent.actions]
        self.assertIn("MOVE", action_types)
        self.assertIn("TALK", action_types)

    def test_skips_location_move_when_phrase_targets_known_npc_for_talk(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich bewege mich zu Mira und frage sie was sie macht.",
            inventory=[],
            known_npc_names=["Mira"],
            known_npc_refs=[
                {
                    "ref_id": "npc-mira",
                    "name": "Mira",
                    "location_name": "Marktplatz",
                    "scene_zone_id": "zone-market-stalls",
                    "scene_zone_name": "Marktstaende",
                    "distance_band_to_player": "near",
                }
            ],
            known_locations=["Marktplatz", "Taverne"],
            known_location_refs=[{"ref_id": "loc-marktplatz", "name": "Marktplatz"}],
        )
        action_types = [action.action_type.value for action in intent.actions]
        self.assertNotIn("MOVE", action_types)
        self.assertIn("TALK", action_types)
        talk_action = next(action for action in intent.actions if action.action_type.value == "TALK")
        self.assertEqual(talk_action.target_ref, "npc-mira")
        self.assertEqual(talk_action.parameters.get("target_distance_band"), "near")
        self.assertIn("Auto-Approach", " ".join(intent.analysis_notes))

    def test_detects_ranged_attack_mode_from_shoot_verb(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich schiesse auf Zorak.",
            inventory=[],
            known_npc_names=["Zorak"],
            known_npc_refs=[
                {
                    "ref_id": "npc-zorak",
                    "name": "Zorak",
                    "location_name": "Marktplatz",
                    "scene_zone_id": "zone-market-stalls",
                    "scene_zone_name": "Marktstaende",
                    "distance_band_to_player": "near",
                }
            ],
        )
        attack_action = next(action for action in intent.actions if action.action_type.value == "ATTACK")
        self.assertEqual(attack_action.target_ref, "npc-zorak")
        self.assertEqual(attack_action.parameters.get("attack_mode"), "ranged")
        self.assertIn("Fernkampf erkannt", " ".join(intent.analysis_notes))

    def test_detects_retreat_away_from_known_npc(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich entferne mich von Mira.",
            inventory=[],
            known_npc_names=["Mira"],
            known_npc_refs=[
                {
                    "ref_id": "npc-mira",
                    "name": "Mira",
                    "location_name": "Marktplatz",
                    "scene_zone_id": "zone-market-stalls",
                    "scene_zone_name": "Marktstaende",
                    "distance_band_to_player": "adjacent",
                }
            ],
        )
        retreat_action = next(action for action in intent.actions if action.action_type.value == "RETREAT")
        self.assertEqual(retreat_action.target_ref, "npc-mira")
        self.assertEqual(retreat_action.parameters.get("target_name"), "Mira")
        self.assertEqual(retreat_action.parameters.get("target_distance_band"), "adjacent")

    def test_detects_approach_to_known_npc(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich gehe auf Mira zu.",
            inventory=[],
            known_npc_names=["Mira"],
            known_npc_refs=[
                {
                    "ref_id": "npc-mira",
                    "name": "Mira",
                    "location_name": "Marktplatz",
                    "scene_zone_id": "zone-market-stalls",
                    "scene_zone_name": "Marktstaende",
                    "distance_band_to_player": "far",
                }
            ],
        )
        approach_action = next(action for action in intent.actions if action.action_type.value == "APPROACH")
        self.assertEqual(approach_action.target_ref, "npc-mira")
        self.assertEqual(approach_action.parameters.get("target_distance_band"), "far")
        self.assertIn("Annaehern erkannt", " ".join(intent.analysis_notes))

    def test_detects_approach_to_known_npc_with_ascii_ae_phrase(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Ich naeher mich Mira.",
            inventory=[],
            known_npc_names=["Mira"],
            known_npc_refs=[
                {
                    "ref_id": "npc-mira",
                    "name": "Mira",
                    "location_name": "Marktplatz",
                    "scene_zone_id": "zone-market-stalls",
                    "scene_zone_name": "Marktstaende",
                    "distance_band_to_player": "far",
                }
            ],
        )
        approach_action = next(action for action in intent.actions if action.action_type.value == "APPROACH")
        self.assertEqual(approach_action.target_ref, "npc-mira")
        self.assertEqual(approach_action.parameters.get("target_name"), "Mira")

    def test_detects_approach_with_combining_umlaut_input(self):
        player_input = "Ich na\u0308her mich Mira."
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input=player_input,
            inventory=[],
            known_npc_names=["Mira"],
            known_npc_refs=[{"ref_id": "npc-mira", "name": "Mira"}],
        )
        approach_action = next(action for action in intent.actions if action.action_type.value == "APPROACH")
        self.assertEqual(approach_action.target_ref, "npc-mira")


if __name__ == "__main__":
    unittest.main()
