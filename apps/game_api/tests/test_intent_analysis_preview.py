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

    def test_falls_back_to_clarify(self):
        intent = analyze_player_input_preview(
            world_id="w1",
            world_character_id="wc1",
            player_input="Hmm...",
            inventory=[],
        )
        self.assertEqual(len(intent.actions), 1)
        self.assertEqual(intent.actions[0].action_type.value, "CLARIFY")


if __name__ == "__main__":
    unittest.main()
