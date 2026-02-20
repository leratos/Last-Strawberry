import unittest
from unittest.mock import patch

from backend_v2.app import main as main_module
from backend_v2.app.config import Settings
from backend_v2.app.providers.embeddings_openrouter import OpenRouterEmbeddingsProvider
from backend_v2.app.services.embeddings import HashEmbeddingsProvider, NoopEmbeddingsProvider
from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.rate_limit import SlidingWindowRateLimiter
from backend_v2.app.services.retrieval import LexicalMemoryRetriever


class TestMainFactories(unittest.TestCase):
    def tearDown(self):
        main_module.get_orchestrator.cache_clear()
        main_module.get_embeddings_provider.cache_clear()
        main_module.get_memory_retriever.cache_clear()
        main_module.get_retrieval_metrics_collector.cache_clear()
        main_module.get_login_rate_limiter.cache_clear()
        main_module.get_turn_ip_rate_limiter.cache_clear()
        main_module.get_turn_rate_limiter.cache_clear()

    def test_factory_wires_metrics_collector_into_orchestrator(self):
        settings = Settings(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.ai/api/v1",
        )
        collector = RetrievalMetricsCollector()

        with patch("backend_v2.app.main.get_settings", return_value=settings), patch(
            "backend_v2.app.main.get_retrieval_metrics_collector",
            return_value=collector,
        ):
            main_module.get_orchestrator.cache_clear()
            orchestrator = main_module.get_orchestrator()

        self.assertIs(orchestrator.metrics_collector, collector)

    def test_factories_support_none_embeddings_and_lexical_retriever(self):
        settings = Settings(
            embeddings_provider="none",
            embeddings_dimensions=96,
            memory_retrieval_strategy="lexical",
        )
        with patch("backend_v2.app.main.get_settings", return_value=settings):
            main_module.get_embeddings_provider.cache_clear()
            main_module.get_memory_retriever.cache_clear()

            embeddings_provider = main_module.get_embeddings_provider()
            retriever = main_module.get_memory_retriever()

        self.assertIsInstance(embeddings_provider, NoopEmbeddingsProvider)
        self.assertIsInstance(retriever, LexicalMemoryRetriever)

    def test_factory_supports_openrouter_embeddings_provider(self):
        settings = Settings(
            openrouter_api_key="test-key",
            embeddings_provider="openrouter",
            embeddings_model="openai/text-embedding-3-small",
            embeddings_timeout_seconds=15,
        )
        with patch("backend_v2.app.main.get_settings", return_value=settings):
            main_module.get_embeddings_provider.cache_clear()
            embeddings_provider = main_module.get_embeddings_provider()

        self.assertIsInstance(embeddings_provider, OpenRouterEmbeddingsProvider)

    def test_factory_falls_back_to_hash_when_openrouter_key_missing(self):
        settings = Settings(
            openrouter_api_key=None,
            embeddings_provider="openrouter",
            embeddings_dimensions=32,
        )
        with patch("backend_v2.app.main.get_settings", return_value=settings):
            main_module.get_embeddings_provider.cache_clear()
            embeddings_provider = main_module.get_embeddings_provider()

        self.assertIsInstance(embeddings_provider, HashEmbeddingsProvider)

    def test_factory_returns_cached_retrieval_metrics_collector(self):
        main_module.get_retrieval_metrics_collector.cache_clear()

        first = main_module.get_retrieval_metrics_collector()
        second = main_module.get_retrieval_metrics_collector()

        self.assertIsInstance(first, RetrievalMetricsCollector)
        self.assertIs(first, second)

    def test_factory_returns_cached_turn_rate_limiter(self):
        settings = Settings(
            turn_rate_limit_enabled=True,
            turn_rate_limit_requests=9,
            turn_rate_limit_window_seconds=45,
        )
        with patch("backend_v2.app.main.get_settings", return_value=settings):
            main_module.get_turn_rate_limiter.cache_clear()
            first = main_module.get_turn_rate_limiter()
            second = main_module.get_turn_rate_limiter()

        self.assertIsInstance(first, SlidingWindowRateLimiter)
        self.assertIs(first, second)

    def test_factory_returns_cached_turn_ip_rate_limiter(self):
        settings = Settings(
            turn_ip_rate_limit_enabled=True,
            turn_ip_rate_limit_requests=15,
            turn_ip_rate_limit_window_seconds=70,
        )
        with patch("backend_v2.app.main.get_settings", return_value=settings):
            main_module.get_turn_ip_rate_limiter.cache_clear()
            first = main_module.get_turn_ip_rate_limiter()
            second = main_module.get_turn_ip_rate_limiter()

        self.assertIsInstance(first, SlidingWindowRateLimiter)
        self.assertIs(first, second)

    def test_factory_returns_cached_login_rate_limiter(self):
        settings = Settings(
            login_rate_limit_enabled=True,
            login_rate_limit_requests=11,
            login_rate_limit_window_seconds=50,
        )
        with patch("backend_v2.app.main.get_settings", return_value=settings):
            main_module.get_login_rate_limiter.cache_clear()
            first = main_module.get_login_rate_limiter()
            second = main_module.get_login_rate_limiter()

        self.assertIsInstance(first, SlidingWindowRateLimiter)
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
