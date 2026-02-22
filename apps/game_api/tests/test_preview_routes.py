from pathlib import Path
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "packages" / "shared_schemas"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "rules_engine"))

from apps.game_api.app.main import app  # noqa: E402
from apps.game_api.app.persistence import WorldRepository  # noqa: E402


class TestGameApiPreviewRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "greenfield_test.db"
        repository = WorldRepository(str(db_path))
        repository.initialize()
        app.state.world_repository = repository

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_world_bootstrap_preview(self):
        response = self.client.post(
            "/v1/worlds/bootstrap/preview",
            json={
                "user_id": "u1",
                "world_description": "Eine Hafenstadt mit Intrigen, Wetterumschlag und rivalisierenden Fraktionen.",
                "character_description": "Eine neugierige Kartografin auf der Suche nach ihrer Schwester.",
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("world_seed", payload)
        self.assertIn("initial_narrative", payload)

    def test_world_bootstrap_create_and_get_session(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-create-1",
                "world_description": "Eine windige Grenzstadt zwischen Wald und Sumpf mit einem zerbrochenen Waffenstillstand.",
                "character_description": "Ein ehemaliger Spaeher mit Heilerfahrung und schlechten Erinnerungen an den Krieg.",
                "tone": "grim_adventure",
                "difficulty": "challenging",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()

        world_id = created["world_id"]
        self.assertTrue(world_id.startswith("world-"))
        self.assertEqual(created["user_id"], "u-create-1")
        self.assertEqual(created["character_state"]["location_name"], created["world_seed"]["start_location_name"])
        self.assertGreaterEqual(len(created["inventory"]), 1)
        self.assertGreaterEqual(len(created["journal"]), 1)

        get_response = self.client.get(f"/v1/worlds/{world_id}")
        self.assertEqual(get_response.status_code, 200)
        fetched = get_response.json()
        self.assertEqual(fetched["world_id"], world_id)
        self.assertEqual(fetched["world_seed"]["world_id"], world_id)
        self.assertEqual(fetched["initial_narrative"], created["initial_narrative"])

    def test_get_world_session_returns_404_for_unknown_world(self):
        response = self.client.get("/v1/worlds/world-does-not-exist")
        self.assertEqual(response.status_code, 404)

    def test_g2_analyze_run_and_list_turns_persists_updates(self):
        create_response = self.client.post(
            "/v1/worlds/bootstrap",
            json={
                "user_id": "u-g2-1",
                "world_description": "Eine Stadt im Dauerregen, deren Unterstadt von Geruechten und Schulden beherrscht wird.",
                "character_description": "Ein abgekaempfter Kundschafter mit Sinn fuer Heilmittel und schlechte Deals.",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        created = create_response.json()
        world_id = created["world_id"]
        before_quantity = created["inventory"][0]["quantity"]

        analyze_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/analyze/preview",
            json={"player_input": "Ich gehe zur Taverne und benutze den Starter-Heiltrank."},
        )
        self.assertEqual(analyze_response.status_code, 200)
        intent = analyze_response.json()
        action_types = [action["action_type"] for action in intent["actions"]]
        self.assertIn("MOVE", action_types)
        self.assertIn("USE_ITEM", action_types)

        run_response = self.client.post(
            f"/v1/worlds/{world_id}/turns/run",
            json={"player_input": "Ich gehe zur Taverne und benutze den Starter-Heiltrank."},
        )
        self.assertEqual(run_response.status_code, 200)
        run_payload = run_response.json()
        self.assertIn("turn", run_payload)
        self.assertTrue(run_payload["turn"]["turn_id"].startswith("turn-"))
        self.assertGreaterEqual(len(run_payload["journal_entry_ids"]), 2)

        session_response = self.client.get(f"/v1/worlds/{world_id}")
        self.assertEqual(session_response.status_code, 200)
        session_payload = session_response.json()
        self.assertEqual(session_payload["character_state"]["location_name"], "Taverne")
        self.assertEqual(session_payload["inventory"][0]["quantity"], max(0, before_quantity - 1))
        self.assertGreaterEqual(len(session_payload["journal"]), 3)

        turns_response = self.client.get(f"/v1/worlds/{world_id}/turns")
        self.assertEqual(turns_response.status_code, 200)
        turns_payload = turns_response.json()
        self.assertEqual(len(turns_payload), 1)
        self.assertEqual(turns_payload[0]["world_id"], world_id)
        self.assertEqual(
            turns_payload[0]["resolution"]["resulting_character_state"]["location_name"],
            "Taverne",
        )


if __name__ == "__main__":
    unittest.main()
