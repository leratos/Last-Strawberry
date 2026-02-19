import unittest

from backend_v2.app.services.embeddings import HashEmbeddingsProvider, NoopEmbeddingsProvider


class TestNoopEmbeddingsProvider(unittest.TestCase):
    def test_returns_zero_vectors(self):
        provider = NoopEmbeddingsProvider(dimensions=8)
        vectors = provider.embed_texts(["alpha", "beta"])
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 8)
        self.assertTrue(all(value == 0.0 for value in vectors[0]))


class TestHashEmbeddingsProvider(unittest.TestCase):
    def test_returns_normalized_vectors(self):
        provider = HashEmbeddingsProvider(dimensions=32)
        vectors = provider.embed_texts(["alpha beta gamma"])
        self.assertEqual(len(vectors), 1)
        self.assertEqual(len(vectors[0]), 32)
        self.assertTrue(all(-1.0 <= value <= 1.0 for value in vectors[0]))

    def test_empty_text_returns_zeros(self):
        provider = HashEmbeddingsProvider(dimensions=32)
        vector = provider.embed_texts(["!!!"])[0]
        self.assertTrue(all(value == 0.0 for value in vector))


if __name__ == "__main__":
    unittest.main()
