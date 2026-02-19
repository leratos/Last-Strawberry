from datetime import UTC, datetime
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend_v2.app.config import Settings
from backend_v2.app.main import app
from backend_v2.app.models import TurnResponse
from backend_v2.app.persistence import PersistenceError
from backend_v2.app.providers.base import ProviderError


class _SuccessOrchestrator:
    async def run_turn(self, request):
        return TurnResponse(
            narrative="Die Szene geht weiter. Was tust du als naechstes?",
            extracted_commands=[{"command": "ROLL_CHECK", "attribut": "Geschicklichkeit"}],
            provider="fake",
            models={"analysis": "model-a", "narrative": "model-b"},
            created_at=datetime.now(UTC),
        )


class _ProviderErrorOrchestrator:
    async def run_turn(self, request):
        raise ProviderError("upstream provider unavailable")


class _UnexpectedErrorOrchestrator:
    async def run_turn(self, request):
        raise RuntimeError("boom")


class _MemoryRepo:
    def __init__(self):
        self.worlds = {}
        self.turns = []
        self._world_id = 1
        self._turn_id = 1

    def create_world(self, *, owner_id, name, description=""):
        world = {
            "id": self._world_id,
            "owner_id": owner_id,
            "name": name,
            "description": description,
            "created_at": datetime.now(UTC).isoformat(),
        }
        self.worlds[self._world_id] = world
        self._world_id += 1
        return world

    def get_world(self, world_id):
        return self.worlds.get(world_id)

    def save_turn(self, request, response):
        turn = {
            "id": self._turn_id,
            "world_id": request.world_id,
            "player_id": request.player_id,
            "player_command": request.player_command,
            "narrative": response.narrative,
            "extracted_commands": response.extracted_commands,
            "provider": response.provider,
            "analysis_model": response.models["analysis"],
            "narrative_model": response.models["narrative"],
            "created_at": response.created_at.isoformat(),
        }
        self.turns.append(turn)
        self._turn_id += 1
        return turn

    def list_turns(self, world_id, limit=20):
        result = [turn for turn in self.turns if turn["world_id"] == world_id]
        return list(reversed(result))[:limit]


class _FailingRepo:
    def save_turn(self, request, response):
        raise PersistenceError("db write failed")


class TestMainApi(unittest.TestCase):
    def setUp(self):
        self.repo = _MemoryRepo()
        self.repo_patcher = patch("backend_v2.app.main.get_repository", return_value=self.repo)
        self.repo_patcher.start()
        self.addCleanup(self.repo_patcher.stop)
        self.client = TestClient(app)

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["service"], "last-strawberry-backend-v2")
        self.assertEqual(body["health"], "/v2/health")

    def test_health_degraded_without_api_key(self):
        with patch(
            "backend_v2.app.main.get_settings",
            return_value=Settings(openrouter_api_key=None, analysis_model="a", narrative_model="b"),
        ):
            response = self.client.get("/v2/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "degraded")

    def test_health_ok_with_api_key(self):
        with patch(
            "backend_v2.app.main.get_settings",
            return_value=Settings(openrouter_api_key="secret", analysis_model="a", narrative_model="b"),
        ):
            response = self.client.get("/v2/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_game_turn_success(self):
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich schleiche voran."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            response = self.client.post("/v2/game/turn", json=payload)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "fake")
        self.assertEqual(body["models"]["analysis"], "model-a")
        self.assertEqual(len(body["extracted_commands"]), 1)
        self.assertEqual(len(self.repo.turns), 1)

    def test_game_turn_provider_error_maps_to_502(self):
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich warte."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_ProviderErrorOrchestrator()):
            response = self.client.post("/v2/game/turn", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("upstream provider", response.json()["detail"])

    def test_game_turn_unexpected_error_maps_to_500(self):
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich schaue mich um."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_UnexpectedErrorOrchestrator()):
            response = self.client.post("/v2/game/turn", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"], "Internal v2 error.")

    def test_game_turn_persistence_error_maps_to_500(self):
        payload = {"world_id": 1, "player_id": 7, "player_command": "Ich sichere die Umgebung."}
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()), patch(
            "backend_v2.app.main.get_repository", return_value=_FailingRepo()
        ):
            response = self.client.post("/v2/game/turn", json=payload)
        self.assertEqual(response.status_code, 500)
        self.assertIn("Persistence error", response.json()["detail"])

    def test_create_world(self):
        payload = {"owner_id": 11, "name": "Schattenforst", "description": "Ein dunkler Wald."}
        response = self.client.post("/v2/worlds", json=payload)
        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["owner_id"], 11)
        self.assertEqual(body["name"], "Schattenforst")

    def test_get_world_not_found(self):
        response = self.client.get("/v2/worlds/404")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "World not found.")

    def test_list_world_turns(self):
        self.client.post("/v2/worlds", json={"owner_id": 1, "name": "Testwelt", "description": ""})
        with patch("backend_v2.app.main.get_orchestrator", return_value=_SuccessOrchestrator()):
            self.client.post(
                "/v2/game/turn",
                json={"world_id": 1, "player_id": 7, "player_command": "Ich gehe weiter."},
            )
        response = self.client.get("/v2/worlds/1/turns?limit=10")
        self.assertEqual(response.status_code, 200)
        turns = response.json()
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["world_id"], 1)
        self.assertEqual(turns[0]["player_id"], 7)


if __name__ == "__main__":
    unittest.main()
