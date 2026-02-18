import unittest

from backend_v2.app.config import Settings
from backend_v2.app.models import TurnRequest
from backend_v2.app.services.orchestrator import GameOrchestrator


class FakeProvider:
    name = "fake"

    def __init__(self):
        self.calls = 0

    async def generate(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return '[{"command":"ROLL_CHECK","attribut":"Geschicklichkeit","schwierigkeit":12}]'
        return "Du weichst den Truemmern aus und landest sicher. Was tust du als naechstes?"


class TestOrchestrator(unittest.IsolatedAsyncioTestCase):
    async def test_run_turn_returns_commands_and_narrative(self):
        settings = Settings(
            openrouter_api_key="test-key",
            analysis_model="model-a",
            narrative_model="model-b",
        )
        provider = FakeProvider()
        orchestrator = GameOrchestrator(provider=provider, settings=settings)

        request = TurnRequest(
            world_id=1,
            player_id=1,
            player_command="Ich springe ueber die Kiste.",
            world_name="Testwelt",
            player_name="Leratos",
        )
        result = await orchestrator.run_turn(request)

        self.assertEqual(result.provider, "fake")
        self.assertEqual(result.models["analysis"], "model-a")
        self.assertEqual(result.models["narrative"], "model-b")
        self.assertEqual(len(result.extracted_commands), 1)
        self.assertIn("Was tust du", result.narrative)


if __name__ == "__main__":
    unittest.main()
