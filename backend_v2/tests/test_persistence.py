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


if __name__ == "__main__":
    unittest.main()
