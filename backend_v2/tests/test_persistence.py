from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend_v2.app.models import TurnRequest, TurnResponse
from backend_v2.app.persistence import PersistenceError, SQLiteRepository


class TestSQLiteRepository(unittest.TestCase):
    def test_rejects_non_sqlite_url(self):
        with self.assertRaises(PersistenceError):
            SQLiteRepository("postgresql://localhost/db")

    def test_resolve_sqlite_path_edge_cases(self):
        with self.assertRaises(PersistenceError):
            SQLiteRepository._resolve_sqlite_path("sqlite:///")

        memory_path = SQLiteRepository._resolve_sqlite_path("sqlite:///:memory:")
        self.assertEqual(memory_path, Path(":memory:"))

        relative_path = SQLiteRepository._resolve_sqlite_path("sqlite:///backend_v2/data/unit.db")
        self.assertTrue(relative_path.is_absolute())

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
            self.assertIsNone(repo.get_world(9999))

    def test_memory_database_connect_branch(self):
        repo = SQLiteRepository("sqlite:///:memory:")
        self.assertEqual(repo.database_path, Path(":memory:"))
        repo.initialize()

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

    def test_list_turns_handles_invalid_json_and_recent_events_format(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")
            request = TurnRequest(world_id=9, player_id=2, player_command="Ich pruefe die Spuren.")
            response = TurnResponse(
                narrative="Du findest Schleifspuren am Boden.",
                extracted_commands=[{"command": "ROLL_CHECK"}],
                provider="openrouter",
                models={"analysis": "model-a", "narrative": "model-b"},
                created_at=datetime.now(UTC),
            )
            repo.save_turn(request, response)

            with repo._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO turns(
                        world_id,
                        player_id,
                        player_command,
                        narrative,
                        extracted_commands,
                        provider,
                        analysis_model,
                        narrative_model,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        9,
                        3,
                        "Ich markiere den Fundort.",
                        "Der Fundort ist markiert.",
                        "[broken json",
                        "openrouter",
                        "model-a",
                        "model-b",
                        datetime.now(UTC).isoformat(),
                    ),
                )
                conn.commit()

            turns = repo.list_turns(world_id=9, limit=1000)
            self.assertEqual(len(turns), 2)
            self.assertEqual(turns[0]["extracted_commands"], [])

            events = repo.list_recent_turn_events(world_id=9, limit=99)
            self.assertEqual(len(events), 2)
            self.assertTrue(events[0].startswith("Player action:"))
            self.assertIn("Outcome:", events[0])

    def test_memory_write_list_and_search(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")
            written = repo.save_memory_items(
                world_id=5,
                source_turn_id=12,
                items=[
                    {"memory_type": "npc_profile", "content": "NPC introduced: Elara", "importance": 0.9},
                    {"memory_type": "story_beat", "content": "Storm starts at the old gate", "importance": 0.7},
                ],
            )
            listed = repo.list_memory_items(world_id=5, limit=10, min_importance=0.6)
            searched = repo.search_memory_items(world_id=5, query="Elara gate", limit=2, min_importance=0.6)

            self.assertEqual(written, 2)
            self.assertEqual(len(listed), 2)
            self.assertEqual(listed[0]["world_id"], 5)
            self.assertEqual(listed[0]["source_turn_id"], 12)
            self.assertEqual(len(searched), 2)
            self.assertIn("Elara", searched[0]["content"] + searched[1]["content"])

    def test_memory_write_and_search_branch_fallbacks(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")

            self.assertEqual(repo.save_memory_items(world_id=1, items=[]), 0)
            self.assertEqual(
                repo.save_memory_items(
                    world_id=1,
                    items=[
                        {"memory_type": "", "content": "invalid", "importance": 0.9},
                        {"memory_type": "story_beat", "content": "", "importance": 0.9},
                    ],
                ),
                0,
            )

            repo.save_memory_items(
                world_id=1,
                items=[
                    {"memory_type": "story_beat", "content": "Wind rises in the north", "importance": 0.65},
                    {"memory_type": "npc_profile", "content": "NPC introduced: Mira", "importance": 0.85},
                ],
            )

            no_candidates = repo.search_memory_items(world_id=2, query="anything", limit=5, min_importance=0.5)
            self.assertEqual(no_candidates, [])

            empty_query_terms = repo.search_memory_items(world_id=1, query="!!!", limit=1, min_importance=0.5)
            self.assertEqual(len(empty_query_terms), 1)

            no_overlap = repo.search_memory_items(world_id=1, query="zebra quaternion", limit=5, min_importance=0.5)
            self.assertEqual(len(no_overlap), 2)

    def test_embeddings_cache_roundtrip_and_invalid_rows(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")

            written = repo.upsert_cached_embeddings(
                provider="hash",
                model="hash-64",
                embeddings_by_text={
                    "alpha": [0.1, 0.2],
                    "beta": [0.3, 0.4],
                },
            )
            self.assertEqual(written, 2)

            cached = repo.get_cached_embeddings("hash", "hash-64", ["alpha", "beta", "gamma"])
            self.assertIn("alpha", cached)
            self.assertIn("beta", cached)
            self.assertNotIn("gamma", cached)

            with repo._connect() as conn:
                conn.execute(
                    "UPDATE embeddings_cache SET embedding = ? WHERE input_text = ?;",
                    ("{broken-json", "alpha"),
                )
                conn.commit()

            cached_after_corrupt = repo.get_cached_embeddings("hash", "hash-64", ["alpha", "beta"])
            self.assertNotIn("alpha", cached_after_corrupt)
            self.assertIn("beta", cached_after_corrupt)

            with repo._connect() as conn:
                conn.execute(
                    "UPDATE embeddings_cache SET embedding = ? WHERE input_text = ?;",
                    ('{"not":"a-list"}', "beta"),
                )
                conn.commit()
            cached_after_non_list = repo.get_cached_embeddings("hash", "hash-64", ["beta"])
            self.assertEqual(cached_after_non_list, {})

            repo.upsert_cached_embeddings(
                provider="hash",
                model="hash-64",
                embeddings_by_text={"gamma": [0.5, 0.6]},
            )
            with repo._connect() as conn:
                conn.execute(
                    "UPDATE embeddings_cache SET embedding = ? WHERE input_text = ?;",
                    ('["x", "y"]', "gamma"),
                )
                conn.commit()
            cached_after_non_float = repo.get_cached_embeddings("hash", "hash-64", ["gamma"])
            self.assertEqual(cached_after_non_float, {})

    def test_embeddings_cache_empty_inputs(self):
        with TemporaryDirectory() as tmp_dir:
            repo = SQLiteRepository(f"sqlite:///{tmp_dir}/v2.db")
            self.assertEqual(repo.get_cached_embeddings("hash", "hash-64", []), {})
            self.assertEqual(repo.upsert_cached_embeddings("hash", "hash-64", {}), 0)


if __name__ == "__main__":
    unittest.main()
