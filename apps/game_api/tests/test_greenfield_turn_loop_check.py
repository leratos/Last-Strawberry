from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from apps.game_api.scripts.check_greenfield_turn_loop import (  # noqa: E402
    _build_structured_approach_action,
    _build_structured_attack_action,
    _build_structured_retreat_action,
    _build_structured_scene_action,
    _build_structured_talk_action,
    _extract_event_codes,
    _find_npc_bundle,
)


class TestGreenfieldTurnLoopQuickcheckHelpers(unittest.TestCase):
    def test_build_structured_talk_action_preserves_target_metadata(self):
        target_ref = {
            "ref_id": "npc-mira",
            "name": "Mira",
            "location_name": "Marktplatz",
            "scene_zone_id": "zone-market-stalls",
            "scene_zone_name": "Marktstaende",
            "distance_band_to_player": "near",
        }

        action = _build_structured_talk_action(target_ref)

        self.assertEqual(action["action_type"], "TALK")
        self.assertEqual(action["target_ref"], "npc-mira")
        self.assertEqual(action["parameters"]["target_name"], "Mira")
        self.assertEqual(action["parameters"]["target_zone_id"], "zone-market-stalls")
        self.assertEqual(action["parameters"]["target_distance_band"], "near")

    def test_extract_event_codes_reads_nested_turn_resolution_events(self):
        payload = {
            "turn": {
                "resolution": {
                    "system_events": [
                        {"code": "auto_approach_for_talk"},
                        {"code": "talk_success"},
                    ]
                }
            }
        }

        self.assertEqual(_extract_event_codes(payload), ["auto_approach_for_talk", "talk_success"])

    def test_build_structured_attack_action_includes_attack_mode(self):
        action = _build_structured_attack_action(
            {
                "ref_id": "npc-mira",
                "name": "Mira",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-market-stalls",
                "scene_zone_name": "Marktstaende",
                "distance_band_to_player": "near",
            },
            attack_mode="ranged",
        )
        self.assertEqual(action["action_type"], "ATTACK")
        self.assertEqual(action["parameters"]["attack_mode"], "ranged")
        self.assertEqual(action["parameters"]["target_zone_name"], "Marktstaende")

    def test_build_structured_retreat_action_includes_target_metadata(self):
        action = _build_structured_retreat_action(
            {
                "ref_id": "npc-mira",
                "name": "Mira",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-market-stalls",
                "scene_zone_name": "Marktstaende",
                "distance_band_to_player": "adjacent",
            }
        )
        self.assertEqual(action["action_type"], "RETREAT")
        self.assertEqual(action["parameters"]["target_name"], "Mira")
        self.assertEqual(action["parameters"]["target_distance_band"], "adjacent")

    def test_build_structured_approach_action_includes_target_metadata(self):
        action = _build_structured_approach_action(
            {
                "ref_id": "npc-mira",
                "name": "Mira",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-market-stalls",
                "scene_zone_name": "Marktstaende",
                "distance_band_to_player": "far",
            }
        )
        self.assertEqual(action["action_type"], "APPROACH")
        self.assertEqual(action["parameters"]["target_name"], "Mira")
        self.assertEqual(action["parameters"]["target_distance_band"], "far")

    def test_find_npc_bundle_selects_by_npc_id(self):
        bundles = [
            {"profile": {"npc_id": "npc-zorak"}},
            {"profile": {"npc_id": "npc-mira"}, "relationship": {"standing": 1}},
        ]
        found = _find_npc_bundle(bundles, "npc-mira")
        self.assertIsNotNone(found)
        self.assertEqual(found["relationship"]["standing"], 1)

    def test_build_structured_scene_action_preserves_target_metadata(self):
        action = _build_structured_scene_action(
            {
                "ref_id": "obj-marktplatz-discarded-bag",
                "name": "Liegende Tasche",
                "kind": "scene_object",
                "location_name": "Marktplatz",
                "scene_zone_id": "zone-poi-marktplatz-bag",
                "scene_zone_name": "Randbereich",
            },
            "take",
        )
        self.assertEqual(action["action_type"], "TAKE")
        self.assertEqual(action["target_ref"], "obj-marktplatz-discarded-bag")
        self.assertEqual(action["target_kind"], "scene_object")
        self.assertEqual(action["parameters"]["target_name"], "Liegende Tasche")


if __name__ == "__main__":
    unittest.main()
