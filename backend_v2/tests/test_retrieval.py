import unittest

from backend_v2.app.services.retrieval import HybridMemoryRetriever, LexicalMemoryRetriever


class _FakeRepo:
    def __init__(self):
        self.search_result = []
        self.list_result = []

    def search_memory_items(self, world_id, query, limit=5, min_importance=0.5):
        return self.search_result[:limit]

    def list_memory_items(self, world_id, limit=20, min_importance=0.0):
        return self.list_result[:limit]


class TestLexicalMemoryRetriever(unittest.TestCase):
    def test_retrieve_returns_lexical_items_and_stats(self):
        repo = _FakeRepo()
        repo.search_result = [
            {"id": 1, "content": "NPC introduced: Elara", "importance": 0.9},
            {"id": 2, "content": "Storm starts at gate", "importance": 0.7},
        ]
        retriever = LexicalMemoryRetriever()
        result = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="Elara gate",
            limit=2,
            min_importance=0.5,
        )
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.stats.strategy, "lexical")
        self.assertEqual(result.stats.lexical_hits, 2)
        self.assertFalse(result.stats.fallback_used)


class TestHybridMemoryRetriever(unittest.TestCase):
    def test_hybrid_returns_ranked_overlap(self):
        repo = _FakeRepo()
        repo.list_result = [
            {"id": 1, "content": "NPC introduced: Elara", "importance": 0.9},
            {"id": 2, "content": "Storm starts at gate", "importance": 0.7},
            {"id": 3, "content": "Unrelated memory", "importance": 0.8},
        ]
        retriever = HybridMemoryRetriever()
        result = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="Elara gate",
            limit=2,
            min_importance=0.5,
        )
        self.assertEqual(len(result.items), 2)
        self.assertEqual(result.stats.strategy, "hybrid")
        self.assertGreater(result.stats.lexical_hits, 0)
        self.assertFalse(result.stats.fallback_used)

    def test_hybrid_fallback_for_empty_query_terms_or_no_hits(self):
        repo = _FakeRepo()
        repo.list_result = [
            {"id": 10, "content": "Wind rises in the north", "importance": 0.8},
            {"id": 11, "content": "Torch flickers", "importance": 0.7},
        ]
        retriever = HybridMemoryRetriever()

        empty_terms = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="!!!",
            limit=1,
            min_importance=0.5,
        )
        self.assertEqual(len(empty_terms.items), 1)
        self.assertTrue(empty_terms.stats.fallback_used)

        no_hits = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="quaternion zebra",
            limit=2,
            min_importance=0.5,
        )
        self.assertEqual(len(no_hits.items), 2)
        self.assertTrue(no_hits.stats.fallback_used)

    def test_hybrid_fallback_when_no_candidates(self):
        repo = _FakeRepo()
        retriever = HybridMemoryRetriever()
        result = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="anything",
            limit=2,
            min_importance=0.5,
        )
        self.assertEqual(result.items, [])
        self.assertEqual(result.stats.candidates_scanned, 0)
        self.assertTrue(result.stats.fallback_used)


if __name__ == "__main__":
    unittest.main()
