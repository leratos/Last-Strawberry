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

    async def test_run_turn_accepts_embedded_json_from_analysis(self):
        class EmbeddedJsonProvider:
            name = "fake"

            def __init__(self):
                self.calls = 0

            async def generate(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return 'prefix text [{"command":"PLAYER_MOVE","location_name":"Tempel"}] suffix'
                return "Du stehst nun vor dem Tempel. Was tust du als naechstes?"

        settings = Settings(openrouter_api_key="test-key", analysis_model="a", narrative_model="b")
        orchestrator = GameOrchestrator(provider=EmbeddedJsonProvider(), settings=settings)
        request = TurnRequest(world_id=1, player_id=1, player_command="Ich gehe zum Tempel.")

        result = await orchestrator.run_turn(request)
        self.assertEqual(result.extracted_commands[0]["command"], "PLAYER_MOVE")
        self.assertEqual(result.extracted_commands[0]["location_name"], "Tempel")


class TestOrchestratorHelpers(unittest.TestCase):
    def setUp(self):
        self.settings = Settings(openrouter_api_key="test-key", analysis_model="model-a", narrative_model="model-b")
        self.orchestrator = GameOrchestrator(provider=FakeProvider(), settings=self.settings)

    def test_extract_commands_empty_returns_empty(self):
        self.assertEqual(self.orchestrator._extract_commands(""), [])
        self.assertEqual(self.orchestrator._extract_commands(None), [])

    def test_extract_commands_valid_json_array(self):
        raw = '[{"command":"NPC_CREATE","name":"Elara"}]'
        parsed = self.orchestrator._extract_commands(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["command"], "NPC_CREATE")

    def test_extract_commands_non_array_json_returns_empty(self):
        self.assertEqual(self.orchestrator._extract_commands('{"command":"NPC_CREATE"}'), [])

    def test_extract_commands_embedded_json_array(self):
        raw = "analysis result: [{\"command\":\"ROLL_CHECK\",\"attribut\":\"Stärke\"}] done"
        parsed = self.orchestrator._extract_commands(raw)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["command"], "ROLL_CHECK")

    def test_extract_commands_invalid_json_returns_empty(self):
        self.assertEqual(self.orchestrator._extract_commands("[{broken json]"), [])
        self.assertEqual(self.orchestrator._extract_commands("no json here"), [])

    def test_build_analysis_prompts_contains_expected_fields(self):
        request = TurnRequest(
            world_id=2,
            player_id=5,
            player_command="Ich klopfe an die Tuer.",
            player_name="Leratos",
            npc_context="Wache steht vor der Tuer.",
        )
        system_prompt, user_prompt = self.orchestrator._build_analysis_prompts(request)

        self.assertIn("strict game command extractor", system_prompt)
        self.assertIn("Player: Leratos", user_prompt)
        self.assertIn("NPC context: Wache steht vor der Tuer.", user_prompt)
        self.assertIn("Player command: Ich klopfe an die Tuer.", user_prompt)

    def test_build_narrative_prompts_uses_last_three_events(self):
        request = TurnRequest(
            world_id=2,
            player_id=5,
            player_command="Ich betrete die Halle.",
            world_name="Arkanum",
            player_name="Leratos",
            recent_events=["E1", "E2", "E3", "E4"],
        )
        _, user_prompt = self.orchestrator._build_narrative_prompts(
            request,
            extracted_commands=[{"command": "PLAYER_MOVE", "location_name": "Halle"}],
        )

        self.assertIn("World: Arkanum", user_prompt)
        self.assertIn("Player: Leratos", user_prompt)
        self.assertNotIn("E1", user_prompt)
        self.assertIn("E2", user_prompt)
        self.assertIn("E3", user_prompt)
        self.assertIn("E4", user_prompt)
        self.assertIn('"command": "PLAYER_MOVE"', user_prompt)

    def test_build_narrative_prompts_without_history_uses_fallback(self):
        request = TurnRequest(world_id=3, player_id=1, player_command="Ich warte.")
        _, user_prompt = self.orchestrator._build_narrative_prompts(request, extracted_commands=[])
        self.assertIn("No recent events.", user_prompt)


if __name__ == "__main__":
    unittest.main()
