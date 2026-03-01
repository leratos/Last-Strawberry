from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))

from apps.game_api.app.services.story_beats import build_story_beats_from_resolution  # noqa: E402
from ls_shared_schemas.character import CharacterAttributes, CharacterResources, CharacterState  # noqa: E402
from ls_shared_schemas.turns import TurnResolution, TurnSystemEvent  # noqa: E402


class TestStoryBeats(unittest.TestCase):
    def test_prefers_discovery_consequence_event_for_inspect_turn(self):
        resolution = TurnResolution(
            world_id="w1",
            world_character_id="wc1",
            resulting_character_state=CharacterState(
                world_character_id="wc1",
                name="Ari",
                location_name="Marktplatz",
                scene_zone_name="Brunnenplatz",
                attributes=CharacterAttributes(strength=10, dexterity=10, intelligence=12, charisma=11),
                resources=CharacterResources(hp=10, max_hp=10, stamina=10, max_stamina=10, focus=3, max_focus=3),
            ),
            resulting_inventory=[],
            system_events=[
                TurnSystemEvent(code="inspect_broad_success", message="Umgebung aufmerksam untersucht."),
                TurnSystemEvent(code="discovery_revealed_npcs", message="Du erkennst 2 neue Praesenz(en)."),
                TurnSystemEvent(
                    code="discovery_revealed_scene_points",
                    message="Du entdeckst 3 neue Interaktionspunkt(e): Streitende Schattenfiguren.",
                ),
            ],
        )

        beats = build_story_beats_from_resolution(resolution)
        consequence = next((beat for beat in beats if beat.startswith("consequence:")), "")
        self.assertIn("discovery_revealed_scene_points", consequence)
        self.assertIn("Schattenfiguren", consequence)


if __name__ == "__main__":
    unittest.main()

