from pathlib import Path
import sys
import unittest

from pydantic import ValidationError


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))

from ls_shared_schemas.inventory import InventoryItemInstance, ItemUseMode  # noqa: E402
from ls_shared_schemas.npc_memory import NPCMemoryBundle, NPCMemoryEntry, NPCProfile, NPCRelationship  # noqa: E402
from ls_shared_schemas.turns import ActionType, TurnIntentAction  # noqa: E402
from ls_shared_schemas.world import WorldBootstrapRequest  # noqa: E402


class TestSchemas(unittest.TestCase):
    def test_world_bootstrap_request_requires_substantial_text(self):
        req = WorldBootstrapRequest(
            user_id="u-1",
            world_description="Eine alte Kuestenstadt mit Schmugglern, Sturm und politischen Intrigen.",
            character_description="Eine ehemalige Kartografin, die ihre verschollene Schwester sucht.",
        )
        self.assertEqual(req.tone, "adventure")

    def test_inventory_item_supports_use_modes(self):
        item = InventoryItemInstance(
            inventory_item_id="i1",
            item_def_id="rope",
            name="Seil",
            use_modes=[ItemUseMode.inspect, ItemUseMode.use],
        )
        self.assertTrue(item.supports(ItemUseMode.use))
        self.assertFalse(item.supports(ItemUseMode.consume))

    def test_npc_memory_bundle_models_relationship_and_memories(self):
        bundle = NPCMemoryBundle(
            profile=NPCProfile(npc_id="npc-1", name="Mira", role="healer"),
            relationship=NPCRelationship(npc_id="npc-1", world_character_id="wc-1", standing=12),
            recent_memories=[
                NPCMemoryEntry(memory_id="m1", npc_id="npc-1", world_id="w1", summary="Half bei einer Verletzung.")
            ],
        )
        self.assertEqual(bundle.profile.name, "Mira")
        self.assertEqual(bundle.relationship.standing, 12)
        self.assertEqual(len(bundle.recent_memories), 1)

    def test_turn_intent_action_move_requires_destination_or_target(self):
        with self.assertRaises(ValidationError):
            TurnIntentAction(action_type=ActionType.move)


if __name__ == "__main__":
    unittest.main()
