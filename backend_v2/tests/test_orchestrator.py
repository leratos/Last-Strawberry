import unittest

from backend_v2.app.config import Settings
from backend_v2.app.models import TurnRequest
from backend_v2.app.providers.base import GenerationResult, ProviderError
from backend_v2.app.services.metrics import RetrievalMetricsCollector
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

    async def test_run_turn_accepts_string_command_array_from_analysis(self):
        class StringArrayProvider:
            name = "fake"

            def __init__(self):
                self.calls = 0

            async def generate(self, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    return '["PLAYER_STATE_UPDATE"]'
                return "Du atmest tief durch. Was tust du als naechstes?"

        settings = Settings(openrouter_api_key="test-key", analysis_model="a", narrative_model="b")
        orchestrator = GameOrchestrator(provider=StringArrayProvider(), settings=settings)
        request = TurnRequest(world_id=1, player_id=1, player_command="Ich sammle mich.")

        result = await orchestrator.run_turn(request)
        self.assertEqual(result.extracted_commands, [{"command": "PLAYER_STATE_UPDATE"}])

    async def test_run_turn_uses_fallback_models(self):
        class FallbackProvider:
            name = "fake"

            def __init__(self):
                self.calls: list[str] = []

            async def generate(self, **kwargs):
                model = kwargs["model"]
                self.calls.append(model)
                if model in {"analysis-primary", "narrative-primary"}:
                    raise ProviderError(f"{model} unavailable")
                if model == "analysis-fallback":
                    return '[{"command":"PLAYER_MOVE","location_name":"Bruecke"}]'
                if model == "narrative-fallback":
                    return "Du erreichst die Bruecke. Was tust du als naechstes?"
                raise ProviderError("unexpected model")

        settings = Settings(
            openrouter_api_key="test-key",
            analysis_model="analysis-primary",
            analysis_fallback_models=("analysis-fallback",),
            narrative_model="narrative-primary",
            narrative_fallback_models=("narrative-fallback",),
        )
        provider = FallbackProvider()
        orchestrator = GameOrchestrator(provider=provider, settings=settings)

        request = TurnRequest(world_id=1, player_id=1, player_command="Ich gehe zur Bruecke.")
        result = await orchestrator.run_turn(request)

        self.assertEqual(provider.calls, ["analysis-primary", "analysis-fallback", "narrative-primary", "narrative-fallback"])
        self.assertEqual(result.models["analysis"], "analysis-fallback")
        self.assertEqual(result.models["narrative"], "narrative-fallback")

    async def test_run_turn_records_model_routing_metrics(self):
        class FallbackProvider:
            name = "fake"

            def __init__(self):
                self.calls: list[str] = []

            async def generate(self, **kwargs):
                model = kwargs["model"]
                self.calls.append(model)
                if model == "analysis-primary":
                    raise ProviderError("analysis primary unavailable")
                if model == "analysis-fallback":
                    return '[{"command":"PLAYER_MOVE","location_name":"Bruecke"}]'
                if model == "narrative-primary":
                    return "Du erreichst die Bruecke. Was tust du als naechstes?"
                raise ProviderError("unexpected model")

        collector = RetrievalMetricsCollector()
        settings = Settings(
            openrouter_api_key="test-key",
            analysis_model="analysis-primary",
            analysis_fallback_models=("analysis-fallback",),
            narrative_model="narrative-primary",
            analysis_input_cost_per_1k_usd=0.01,
            analysis_output_cost_per_1k_usd=0.02,
            narrative_input_cost_per_1k_usd=0.03,
            narrative_output_cost_per_1k_usd=0.04,
        )
        provider = FallbackProvider()
        orchestrator = GameOrchestrator(provider=provider, settings=settings, metrics_collector=collector)

        request = TurnRequest(world_id=1, player_id=1, player_command="Ich gehe zur Bruecke.")
        await orchestrator.run_turn(request)

        routing = collector.snapshot()["model_routing"]
        routes = routing["routes"]
        attempt_errors = routing["attempt_errors"]
        model_performance = collector.snapshot()["model_performance"]

        self.assertEqual(len(routes), 2)
        self.assertEqual(len(attempt_errors), 1)
        self.assertEqual(model_performance["totals"]["attempts"], 2)
        self.assertGreaterEqual(model_performance["totals"]["estimated_total_cost_usd"], 0.0)

        analysis_route = next(route for route in routes if route["stage"] == "analysis")
        narrative_route = next(route for route in routes if route["stage"] == "narrative")

        self.assertTrue(analysis_route["fallback"])
        self.assertEqual(analysis_route["requested_model"], "analysis-primary")
        self.assertEqual(analysis_route["used_model"], "analysis-fallback")
        self.assertFalse(narrative_route["fallback"])
        self.assertEqual(narrative_route["used_model"], "narrative-primary")

        self.assertEqual(attempt_errors[0]["stage"], "analysis")
        self.assertEqual(attempt_errors[0]["model"], "analysis-primary")

    async def test_run_turn_records_latency_budget_breach_audit_event(self):
        class SlowProvider:
            name = "fake"

            def __init__(self):
                self.calls = 0

            async def generate_result(self, **kwargs):
                from backend_v2.app.providers.base import GenerationResult

                self.calls += 1
                if self.calls == 1:
                    return GenerationResult(
                        text='[{"command":"PLAYER_STATE_UPDATE"}]',
                        model=kwargs["model"],
                        latency_ms=300.0,
                    )
                return GenerationResult(
                    text="Du blickst nach vorne. Was tust du als naechstes?",
                    model=kwargs["model"],
                    latency_ms=900.0,
                )

        collector = RetrievalMetricsCollector()
        settings = Settings(
            openrouter_api_key="test-key",
            analysis_model="analysis-primary",
            narrative_model="narrative-primary",
            analysis_latency_budget_ms=200,
            narrative_latency_budget_ms=800,
        )
        orchestrator = GameOrchestrator(provider=SlowProvider(), settings=settings, metrics_collector=collector)

        request = TurnRequest(world_id=1, player_id=1, player_command="Ich pruefe die Lage.")
        await orchestrator.run_turn(request)
        audit = collector.snapshot()["audit_events"]
        self.assertEqual(audit["analysis_latency_budget_exceeded"], 1)
        self.assertEqual(audit["narrative_latency_budget_exceeded"], 1)

    async def test_run_turn_raises_if_all_analysis_models_fail(self):
        class AlwaysFailProvider:
            name = "fake"

            async def generate(self, **kwargs):
                raise ProviderError("provider down")

        settings = Settings(
            openrouter_api_key="test-key",
            analysis_model="analysis-primary",
            analysis_fallback_models=("analysis-backup",),
            narrative_model="narrative-primary",
        )
        orchestrator = GameOrchestrator(provider=AlwaysFailProvider(), settings=settings)
        request = TurnRequest(world_id=1, player_id=1, player_command="Test.")

        with self.assertRaises(ProviderError) as ctx:
            await orchestrator.run_turn(request)

        self.assertIn("All analysis models failed", str(ctx.exception))


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

    def test_extract_commands_string_array_is_normalized(self):
        parsed = self.orchestrator._extract_commands('["PLAYER_STATE_UPDATE"]')
        self.assertEqual(parsed, [{"command": "PLAYER_STATE_UPDATE"}])

    def test_extract_commands_mixed_entries_only_keeps_valid_shapes(self):
        raw = '["NPC_CREATE", {"command":"ROLL_CHECK","attribut":"Starke"}, 123, ["PLAYER_MOVE", {"location_name":"Halle"}]]'
        parsed = self.orchestrator._extract_commands(raw)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(parsed[0]["command"], "NPC_CREATE")
        self.assertEqual(parsed[1]["command"], "ROLL_CHECK")
        self.assertEqual(parsed[2]["command"], "PLAYER_MOVE")
        self.assertEqual(parsed[2]["location_name"], "Halle")

    def test_build_analysis_prompts_contains_expected_fields(self):
        request = TurnRequest(
            world_id=2,
            player_id=5,
            player_command="Ich klopfe an die Tuer.",
            player_name="Leratos",
            npc_context="Wache steht vor der Tuer.",
            memory_context=["npc_profile: NPC introduced: Elara"],
        )
        system_prompt, user_prompt = self.orchestrator._build_analysis_prompts(request)

        self.assertIn("strict game command extractor", system_prompt)
        self.assertIn("Player: Leratos", user_prompt)
        self.assertIn("NPC context: Wache steht vor der Tuer.", user_prompt)
        self.assertIn("Memory context:", user_prompt)
        self.assertIn("npc_profile: NPC introduced: Elara", user_prompt)
        self.assertIn("Player command: Ich klopfe an die Tuer.", user_prompt)

    def test_build_narrative_prompts_uses_last_three_events(self):
        request = TurnRequest(
            world_id=2,
            player_id=5,
            player_command="Ich betrete die Halle.",
            world_name="Arkanum",
            player_name="Leratos",
            recent_events=["E1", "E2", "E3", "E4"],
            memory_context=["story_beat: The gate is unstable."],
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
        self.assertIn("Relevant memory:", user_prompt)
        self.assertIn("story_beat: The gate is unstable.", user_prompt)
        self.assertIn('"command": "PLAYER_MOVE"', user_prompt)

    def test_build_narrative_prompts_without_history_uses_fallback(self):
        request = TurnRequest(world_id=3, player_id=1, player_command="Ich warte.")
        _, user_prompt = self.orchestrator._build_narrative_prompts(request, extracted_commands=[])
        self.assertIn("No recent events.", user_prompt)
        self.assertIn("No memory context.", user_prompt)

    def test_iter_candidate_models_deduplicates_and_trims(self):
        candidates = self.orchestrator._iter_candidate_models(
            " model-a ",
            ("model-a", "model-b", "", " model-b ", "model-c"),
        )
        self.assertEqual(candidates, ("model-a", "model-b", "model-c"))

    def test_stage_helpers_return_safe_defaults_for_unknown_stage(self):
        budget = self.orchestrator._get_stage_latency_budget_ms(stage_name="unknown")
        costs = self.orchestrator._estimate_stage_cost(
            stage_name="unknown",
            prompt_tokens=100,
            completion_tokens=50,
        )
        self.assertEqual(budget, 0)
        self.assertEqual(costs, (0.0, 0.0, 0.0))

    def test_record_model_attempt_metrics_is_noop_without_collector(self):
        orchestrator = GameOrchestrator(
            provider=FakeProvider(),
            settings=self.settings,
            metrics_collector=None,
        )
        generation = GenerationResult(text="ok", model="model-a", latency_ms=10.0)
        orchestrator._record_model_attempt_metrics(stage_name="analysis", model="model-a", generation=generation)


if __name__ == "__main__":
    unittest.main()
