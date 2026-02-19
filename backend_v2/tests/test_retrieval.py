import unittest

from backend_v2.app.services.retrieval import HybridMemoryRetriever, LexicalMemoryRetriever


class _FakeRepo:
    def __init__(self):
        self.search_result = []
        self.list_result = []
        self._embedding_cache = {}
        self.cache_get_calls = 0
        self.cache_upsert_calls = 0

    def search_memory_items(self, world_id, query, limit=5, min_importance=0.5):
        return self.search_result[:limit]

    def list_memory_items(self, world_id, limit=20, min_importance=0.0):
        return self.list_result[:limit]

    def get_cached_embeddings(self, provider, model, texts):
        self.cache_get_calls += 1
        result = {}
        for text in texts:
            key = (provider, model, text)
            if key in self._embedding_cache:
                result[text] = self._embedding_cache[key]
        return result

    def upsert_cached_embeddings(self, provider, model, embeddings_by_text):
        self.cache_upsert_calls += 1
        for text, vector in embeddings_by_text.items():
            self._embedding_cache[(provider, model, text)] = vector
        return len(embeddings_by_text)


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
        self.assertEqual(result.stats.semantic_hits, 0)
        self.assertEqual(result.stats.cache_hits, 0)
        self.assertEqual(result.stats.cache_misses, 0)
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
        self.assertEqual(result.stats.semantic_hits, 0)
        self.assertEqual(result.stats.cache_hits, 0)
        self.assertEqual(result.stats.cache_misses, 0)
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
        self.assertEqual(result.stats.cache_hits, 0)
        self.assertEqual(result.stats.cache_misses, 0)
        self.assertTrue(result.stats.fallback_used)

    def test_cosine_similarity_guard_branches(self):
        self.assertEqual(HybridMemoryRetriever._cosine_similarity([], []), 0.0)
        self.assertEqual(HybridMemoryRetriever._cosine_similarity([1.0], [1.0, 2.0]), 0.0)
        self.assertEqual(HybridMemoryRetriever._cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)

    def test_hybrid_handles_embeddings_provider_exception(self):
        class _BrokenProvider:
            provider_name = "broken"

            def embed_texts(self, texts):
                raise RuntimeError("embedding boom")

        repo = _FakeRepo()
        repo.list_result = [
            {"id": 1, "content": "Silent hallway", "importance": 0.6},
            {"id": 2, "content": "Broken mirror", "importance": 0.7},
        ]
        retriever = HybridMemoryRetriever(
            embeddings_provider=_BrokenProvider(),
            semantic_min_similarity=0.2,
        )
        result = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="quaternion zebra",
            limit=1,
            min_importance=0.5,
        )
        self.assertEqual(len(result.items), 1)
        self.assertTrue(result.stats.fallback_used)
        self.assertEqual(result.stats.semantic_hits, 0)
        self.assertEqual(result.stats.cache_hits, 0)
        self.assertEqual(result.stats.cache_misses, 0)

    def test_hybrid_can_return_semantic_only_match(self):
        class _StaticProvider:
            provider_name = "static"

            def embed_texts(self, texts):
                # query + two candidates
                return [
                    [1.0, 0.0, 0.0],
                    [0.0, 1.0, 0.0],
                    [0.9, 0.1, 0.0],
                ]

        repo = _FakeRepo()
        repo.list_result = [
            {"id": 1, "content": "first unrelated memory", "importance": 0.6},
            {"id": 2, "content": "second unrelated memory", "importance": 0.7},
        ]
        retriever = HybridMemoryRetriever(
            embeddings_provider=_StaticProvider(),
            vector_weight=2.0,
            semantic_min_similarity=0.2,
        )
        result = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="mysterious relic",
            limit=1,
            min_importance=0.5,
        )
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0]["id"], 2)
        self.assertEqual(result.stats.lexical_hits, 0)
        self.assertEqual(result.stats.semantic_hits, 1)
        self.assertEqual(result.stats.cache_hits, 0)
        self.assertEqual(result.stats.cache_misses, 3)
        self.assertFalse(result.stats.fallback_used)

    def test_hybrid_uses_embedding_cache_across_calls(self):
        class _CountingProvider:
            provider_name = "counting"
            model_name = "counting-v1"

            def __init__(self):
                self.calls = 0

            def embed_texts(self, texts):
                self.calls += 1
                # return same-sized simple vectors
                return [[1.0, 0.0] for _ in texts]

        repo = _FakeRepo()
        repo.list_result = [
            {"id": 1, "content": "memory one", "importance": 0.7},
            {"id": 2, "content": "memory two", "importance": 0.6},
        ]
        provider = _CountingProvider()
        retriever = HybridMemoryRetriever(embeddings_provider=provider)

        first = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="memory",
            limit=2,
            min_importance=0.5,
        )
        second = retriever.retrieve(
            repository=repo,
            world_id=1,
            query="memory",
            limit=2,
            min_importance=0.5,
        )

        self.assertEqual(provider.calls, 1)
        self.assertGreater(first.stats.cache_misses, 0)
        self.assertEqual(first.stats.cache_hits, 0)
        self.assertGreater(second.stats.cache_hits, 0)
        self.assertEqual(second.stats.cache_misses, 0)

    def test_embed_texts_with_cache_guard_paths(self):
        repo = _FakeRepo()
        retriever_without_provider = HybridMemoryRetriever(embeddings_provider=None)
        vectors, hits, misses = retriever_without_provider._embed_texts_with_cache(repository=repo, texts=["a"])
        self.assertEqual(vectors, [])
        self.assertEqual(hits, 0)
        self.assertEqual(misses, 0)

        class _SimpleProvider:
            provider_name = "simple"
            model_name = "simple-v1"

            def embed_texts(self, texts):
                return [[1.0] for _ in texts]

        retriever_with_provider = HybridMemoryRetriever(embeddings_provider=_SimpleProvider())
        vectors2, hits2, misses2 = retriever_with_provider._embed_texts_with_cache(repository=repo, texts=[])
        self.assertEqual(vectors2, [])
        self.assertEqual(hits2, 0)
        self.assertEqual(misses2, 0)


if __name__ == "__main__":
    unittest.main()
