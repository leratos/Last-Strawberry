import unittest
from unittest.mock import patch

from backend_v2.app import main as main_module
from backend_v2.app.config import Settings
from backend_v2.app.services.embeddings import NoopEmbeddingsProvider
from backend_v2.app.services.retrieval import LexicalMemoryRetriever


class TestMainFactories(unittest.TestCase):
    def tearDown(self):
        main_module.get_embeddings_provider.cache_clear()
        main_module.get_memory_retriever.cache_clear()

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


if __name__ == "__main__":
    unittest.main()
