from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))

from apps.game_api.app.services.narration_preview import build_narrative_from_resolution  # noqa: E402
from ls_shared_schemas.character import CharacterState  # noqa: E402
from ls_shared_schemas.turns import StateDelta, TurnResolution, TurnSystemEvent  # noqa: E402


class TestNarrationPreview(unittest.TestCase):
    def test_reaction_event_is_explicitly_marked_in_narrative(self):
        resolution = TurnResolution(
            world_id="world-1",
            world_character_id="wc-1",
            resulting_character_state=CharacterState(
                world_character_id="wc-1",
                name="Ari",
                location_name="Marktplatz",
            ),
            state_delta=StateDelta(),
            system_events=[
                TurnSystemEvent(code="approach_success", message="Du naeherst dich Mira an."),
                TurnSystemEvent(
                    code="npc_reacts_friendly_to_approach",
                    message="Mira reagiert freundlich auf deine Annaeherung.",
                ),
            ],
        )

        envelope = build_narrative_from_resolution(resolution)

        self.assertIn("Marktplatz", envelope.narrative)
        self.assertIn("Du naeherst dich Mira an.", envelope.narrative)
        self.assertIn("daraufhin mira reagiert freundlich", envelope.narrative.lower())
        self.assertIn("Was tust du als naechstes?", envelope.narrative)
        self.assertGreaterEqual(len(envelope.story_beats), 3)
        self.assertTrue(any(beat.startswith("scene:") for beat in envelope.story_beats))
        self.assertTrue(any("npc_reaction:" in beat for beat in envelope.story_beats))

    def test_container_loot_and_state_delta_are_integrated_into_scene_flow(self):
        resolution = TurnResolution(
            world_id="world-1",
            world_character_id="wc-1",
            resulting_character_state=CharacterState(
                world_character_id="wc-1",
                name="Ari",
                location_name="Marktplatz",
            ),
            state_delta=StateDelta(
                inventory_gained=[
                    {
                        "inventory_item_id": "inv-verbandsset",
                        "name": "Verbandsset",
                        "quantity": 1,
                    }
                ]
            ),
            system_events=[
                TurnSystemEvent(code="search_focus_success", message="Du durchsuchst die Vorratskiste."),
                TurnSystemEvent(code="container_opened", message="Du oeffnest die Vorratskiste."),
                TurnSystemEvent(code="container_loot_found", message="Du findest in der Vorratskiste: Verbandspaket."),
            ],
        )

        envelope = build_narrative_from_resolution(resolution)

        self.assertIn("Zwischen den Spuren sicherst du Verbandsset x1.", envelope.narrative)
        self.assertTrue(envelope.narrative.startswith("In Marktplatz gehst du den naechsten Spuren aufmerksam nach."))
        self.assertNotIn("HP: 10", envelope.narrative)
        self.assertTrue(any("container_loot_found" in beat for beat in envelope.story_beats))

    def test_partial_parse_hint_and_changed_resources_are_narrated(self):
        resolution = TurnResolution(
            world_id="world-1",
            world_character_id="wc-1",
            resulting_character_state=CharacterState(
                world_character_id="wc-1",
                name="Ari",
                location_name="Marktplatz",
            ),
            state_delta=StateDelta(hp_delta=-2, stamina_delta=-1),
            system_events=[
                TurnSystemEvent(code="attack_resolved", message="Du triffst den Gegner mit einem schnellen Hieb."),
                TurnSystemEvent(
                    code="partial_multiclause_parse",
                    message="Mehrteilige Eingabe wurde nur teilweise verarbeitet.",
                ),
            ],
        )

        envelope = build_narrative_from_resolution(resolution)

        self.assertIn("Nicht jede Teilaktion wurde bereits vollstaendig aufgeloest", envelope.narrative)
        self.assertIn("HP -2", envelope.narrative)
        self.assertIn("Ausdauer -1", envelope.narrative)


if __name__ == "__main__":
    unittest.main()
