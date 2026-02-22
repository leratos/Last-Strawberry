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


if __name__ == "__main__":
    unittest.main()
