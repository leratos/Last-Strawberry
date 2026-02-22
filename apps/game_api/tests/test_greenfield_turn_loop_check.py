from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from apps.game_api.scripts.check_greenfield_turn_loop import (  # noqa: E402
    _build_structured_talk_action,
    _extract_event_codes,
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


if __name__ == "__main__":
    unittest.main()
