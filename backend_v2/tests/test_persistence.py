from datetime import UTC, datetime
from tempfile import TemporaryDirectory
import unittest

from backend_v2.app.models import TurnRequest, TurnResponse
from backend_v2.app.persistence import PersistenceError, SQLiteRepository


class TestSQLiteRepository(unittest.TestCase):
    def test_rejects_non_sqlite_url(self):
        with self.assertRaises(PersistenceError):
            SQLiteRepository("postgresql://localhost/db")

    def test_create_and_get_world(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")
            created = repo.create_world(owner_id=10, name="Aschehain", description="Nebel und Ruinen")
            loaded = repo.get_world(created["id"])

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["owner_id"], 10)
            self.assertEqual(loaded["name"], "Aschehain")
            self.assertTrue(repo.is_world_owner(created["id"], 10))
            self.assertFalse(repo.is_world_owner(created["id"], 999))

    def test_save_turn_and_list_turns(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")
            request = TurnRequest(world_id=3, player_id=7, player_command="Ich halte Ausschau.")
            response = TurnResponse(
                narrative="Du entdeckst Spuren im Schlamm.",
                extracted_commands=[{"command": "ROLL_CHECK", "attribut": "Wahrnehmung"}],
                provider="openrouter",
                models={"analysis": "model-a", "narrative": "model-b"},
                created_at=datetime.now(UTC),
            )
            saved = repo.save_turn(request, response)
            turns = repo.list_turns(world_id=3, limit=10)

            self.assertGreater(saved["id"], 0)
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0]["player_id"], 7)
            self.assertEqual(turns[0]["provider"], "openrouter")

    def test_memory_write_list_and_search(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")
            repo.save_memory_items(
                world_id=5,
                source_turn_id=12,
                items=[
                    {"memory_type": "npc_profile", "content": "NPC introduced: Elara", "importance": 0.9},
                    {"memory_type": "story_beat", "content": "Storm starts at the old gate", "importance": 0.7},
                ],
            )
            listed = repo.list_memory_items(world_id=5, limit=10, min_importance=0.6)
            searched = repo.search_memory_items(world_id=5, query="Elara gate", limit=2, min_importance=0.6)

            self.assertEqual(len(listed), 2)
            self.assertEqual(listed[0]["world_id"], 5)
            self.assertEqual(listed[0]["source_turn_id"], 12)
            self.assertEqual(len(searched), 2)
            self.assertIn("Elara", searched[0]["content"] + searched[1]["content"])


if __name__ == "__main__":
    unittest.main()
