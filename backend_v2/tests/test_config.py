import os
import sys
import types
import unittest
from unittest.mock import Mock, patch

from backend_v2.app import config
from backend_v2.app.config import Settings


class TestConfig(unittest.TestCase):
    def test_prefers_ls_openrouter_api_key(self):
        with patch.dict(
            os.environ,
            {"LS_OPENROUTER_API_KEY": "ls-key-123", "OPENROUTER_API_KEY": "fallback-key"},
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.openrouter_api_key, "ls-key-123")

    def test_falls_back_to_openrouter_api_key(self):
        with patch.dict(
            os.environ,
            {"LS_OPENROUTER_API_KEY": "", "OPENROUTER_API_KEY": "fallback-key-456"},
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.openrouter_api_key, "fallback-key-456")

    def test_ignores_placeholder_ls_key_and_uses_openrouter_api_key(self):
        with patch.dict(
            os.environ,
            {"LS_OPENROUTER_API_KEY": "replace_me", "OPENROUTER_API_KEY": "fallback-key-999"},
            clear=False,
        ):
            settings = Settings.from_env()
        self.assertEqual(settings.openrouter_api_key, "fallback-key-999")

    def test_keyring_fallback(self):
        fake_keyring = types.ModuleType("keyring")

        def fake_get_password(service, username):
            if service == "OPENROUTER_API_KEY" and username == "default":
                return "keyring-secret-789"
            return None

        fake_keyring.get_password = fake_get_password

        with patch.dict(
            os.environ,
            {
                "LS_OPENROUTER_API_KEY": "",
                "OPENROUTER_API_KEY": "",
                "LS_OPENROUTER_KEYRING_SERVICE": "OPENROUTER_API_KEY",
                "LS_OPENROUTER_KEYRING_USERNAME": "default",
            },
            clear=False,
        ), patch.dict(sys.modules, {"keyring": fake_keyring}):
            settings = Settings.from_env()

        self.assertEqual(settings.openrouter_api_key, "keyring-secret-789")

    def test_ignores_placeholder_env_and_uses_keyring_fallback(self):
        fake_keyring = types.ModuleType("keyring")

        def fake_get_password(service, username):
            if service == "OPENROUTER_API_KEY" and username == "default":
                return "keyring-secret-000"
            return None

        fake_keyring.get_password = fake_get_password

        with patch.dict(
            os.environ,
            {
                "LS_OPENROUTER_API_KEY": "replace_me",
                "OPENROUTER_API_KEY": "",
                "LS_OPENROUTER_KEYRING_SERVICE": "OPENROUTER_API_KEY",
                "LS_OPENROUTER_KEYRING_USERNAME": "default",
            },
            clear=False,
        ), patch.dict(sys.modules, {"keyring": fake_keyring}):
            settings = Settings.from_env()

        self.assertEqual(settings.openrouter_api_key, "keyring-secret-000")

    def test_windows_credential_discovery_parser(self):
        fake_output = (
            "    Ziel: LegacyGeneric:target=HomeGym_AI_Coach\n"
            "    Typ: Allgemeine\n"
            "    Benutzer: OPENROUTER_API_KEY\n"
        )
        run_mock = Mock(return_value=Mock(returncode=0, stdout=fake_output))
        with patch.object(config, "os") as os_mod, patch.object(config.subprocess, "run", run_mock):
            os_mod.name = "nt"
            services = config._discover_windows_keyring_services("OPENROUTER_API_KEY")

        self.assertEqual(services, ["HomeGym_AI_Coach"])
        run_mock.assert_called_once_with(
            ["cmdkey", "/list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def test_database_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_DATABASE_URL": "sqlite:///tmp/test.db",
                "LS_DATABASE_AUTO_INIT": "false",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.database_url, "sqlite:///tmp/test.db")
        self.assertFalse(settings.database_auto_init)

    def test_jwt_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_JWT_SECRET": "secret-123",
                "LS_JWT_ALGORITHM": "HS256",
                "LS_JWT_EXPIRE_MINUTES": "15",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.jwt_secret, "secret-123")
        self.assertEqual(settings.jwt_algorithm, "HS256")
        self.assertEqual(settings.jwt_expire_minutes, 15)

    def test_turn_timeout_seconds_from_env(self):
        with patch.dict(
            os.environ,
            {"LS_TURN_TIMEOUT_SECONDS": "75"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.turn_timeout_seconds, 75)

    def test_turn_timeout_seconds_has_minimum_floor(self):
        with patch.dict(
            os.environ,
            {"LS_TURN_TIMEOUT_SECONDS": "0"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.turn_timeout_seconds, 1)

    def test_memory_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_MEMORY_CONTEXT_LIMIT": "7",
                "LS_MEMORY_MIN_IMPORTANCE": "0.75",
                "LS_MEMORY_RETRIEVAL_STRATEGY": "lexical",
                "LS_EMBEDDINGS_PROVIDER": "openrouter",
                "LS_EMBEDDINGS_DIMENSIONS": "96",
                "LS_EMBEDDINGS_MODEL": "openai/text-embedding-3-large",
                "LS_EMBEDDINGS_TIMEOUT_SECONDS": "33",
                "LS_RETRIEVAL_VECTOR_WEIGHT": "1.8",
                "LS_RETRIEVAL_SEMANTIC_MIN_SIMILARITY": "0.35",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.memory_context_limit, 7)
        self.assertEqual(settings.memory_min_importance, 0.75)
        self.assertEqual(settings.memory_retrieval_strategy, "lexical")
        self.assertEqual(settings.embeddings_provider, "openrouter")
        self.assertEqual(settings.embeddings_dimensions, 96)
        self.assertEqual(settings.embeddings_model, "openai/text-embedding-3-large")
        self.assertEqual(settings.embeddings_timeout_seconds, 33)
        self.assertEqual(settings.retrieval_vector_weight, 1.8)
        self.assertEqual(settings.retrieval_semantic_min_similarity, 0.35)

    def test_invalid_memory_retrieval_strategy_falls_back_to_default(self):
        with patch.dict(
            os.environ,
            {"LS_MEMORY_RETRIEVAL_STRATEGY": "unknown"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.memory_retrieval_strategy, "hybrid")

    def test_invalid_embeddings_provider_falls_back_to_hash(self):
        with patch.dict(
            os.environ,
            {"LS_EMBEDDINGS_PROVIDER": "invalid"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.embeddings_provider, "hash")

    def test_turn_rate_limit_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_TURN_RATE_LIMIT_ENABLED": "true",
                "LS_TURN_RATE_LIMIT_REQUESTS": "9",
                "LS_TURN_RATE_LIMIT_WINDOW_SECONDS": "45",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertTrue(settings.turn_rate_limit_enabled)
        self.assertEqual(settings.turn_rate_limit_requests, 9)
        self.assertEqual(settings.turn_rate_limit_window_seconds, 45)

    def test_turn_ip_rate_limit_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_TURN_IP_RATE_LIMIT_ENABLED": "false",
                "LS_TURN_IP_RATE_LIMIT_REQUESTS": "99",
                "LS_TURN_IP_RATE_LIMIT_WINDOW_SECONDS": "90",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertFalse(settings.turn_ip_rate_limit_enabled)
        self.assertEqual(settings.turn_ip_rate_limit_requests, 99)
        self.assertEqual(settings.turn_ip_rate_limit_window_seconds, 90)

    def test_login_rate_limit_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_LOGIN_RATE_LIMIT_ENABLED": "false",
                "LS_LOGIN_RATE_LIMIT_REQUESTS": "33",
                "LS_LOGIN_RATE_LIMIT_WINDOW_SECONDS": "120",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertFalse(settings.login_rate_limit_enabled)
        self.assertEqual(settings.login_rate_limit_requests, 33)
        self.assertEqual(settings.login_rate_limit_window_seconds, 120)

    def test_metrics_api_key_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_METRICS_API_KEY": "metrics-secret",
                "LS_METRICS_API_KEY_HEADER": "X-Obs-Key",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.metrics_api_key, "metrics-secret")
        self.assertEqual(settings.metrics_api_key_header, "X-Obs-Key")

    def test_max_request_body_bytes_from_env(self):
        with patch.dict(
            os.environ,
            {"LS_MAX_REQUEST_BODY_BYTES": "65536"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.max_request_body_bytes, 65536)

    def test_max_request_body_bytes_has_minimum_floor(self):
        with patch.dict(
            os.environ,
            {"LS_MAX_REQUEST_BODY_BYTES": "64"},
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.max_request_body_bytes, 1024)

    def test_slo_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_SLO_WINDOW": "60s",
                "LS_SLO_MAX_5XX_PERCENT": "0.8",
                "LS_SLO_MAX_429_PERCENT": "4.2",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.slo_window, "60s")
        self.assertEqual(settings.slo_max_5xx_percent, 0.8)
        self.assertEqual(settings.slo_max_429_percent, 4.2)

    def test_slo_percent_settings_have_zero_floor(self):
        with patch.dict(
            os.environ,
            {
                "LS_SLO_MAX_5XX_PERCENT": "-1",
                "LS_SLO_MAX_429_PERCENT": "-2",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.slo_max_5xx_percent, 0.0)
        self.assertEqual(settings.slo_max_429_percent, 0.0)

    def test_fallback_models_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_ANALYSIS_FALLBACK_MODELS": "model-a, model-b, model-a,  ,model-c",
                "LS_NARRATIVE_FALLBACK_MODELS": "narrative-fast",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.analysis_fallback_models, ("model-a", "model-b", "model-c"))
        self.assertEqual(settings.narrative_fallback_models, ("narrative-fast",))

    def test_model_latency_budget_and_cost_settings_from_env(self):
        with patch.dict(
            os.environ,
            {
                "LS_ANALYSIS_LATENCY_BUDGET_MS": "2500",
                "LS_NARRATIVE_LATENCY_BUDGET_MS": "9000",
                "LS_ANALYSIS_INPUT_COST_PER_1K_USD": "0.002",
                "LS_ANALYSIS_OUTPUT_COST_PER_1K_USD": "0.006",
                "LS_NARRATIVE_INPUT_COST_PER_1K_USD": "0.003",
                "LS_NARRATIVE_OUTPUT_COST_PER_1K_USD": "0.009",
            },
            clear=False,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.analysis_latency_budget_ms, 2500)
        self.assertEqual(settings.narrative_latency_budget_ms, 9000)
        self.assertEqual(settings.analysis_input_cost_per_1k_usd, 0.002)
        self.assertEqual(settings.analysis_output_cost_per_1k_usd, 0.006)
        self.assertEqual(settings.narrative_input_cost_per_1k_usd, 0.003)
        self.assertEqual(settings.narrative_output_cost_per_1k_usd, 0.009)


if __name__ == "__main__":
    unittest.main()
