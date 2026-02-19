from datetime import UTC, datetime
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend_v2.app.config import Settings
from backend_v2.app.main import app
from backend_v2.app.models import TurnResponse
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


class TestMainApi(unittest.TestCase):
    def setUp(self):
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


if __name__ == "__main__":
    unittest.main()
