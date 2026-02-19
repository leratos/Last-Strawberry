import math
import re
from typing import Protocol


class EmbeddingsProvider(Protocol):
    provider_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


class EmbeddingsProviderError(RuntimeError):
    pass


class NoopEmbeddingsProvider:
    provider_name = "none"

    def __init__(self, dimensions: int = 64):
        self.dimensions = max(8, dimensions)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0 for _ in range(self.dimensions)] for _ in texts]


class HashEmbeddingsProvider:
    provider_name = "hash"

    def __init__(self, dimensions: int = 64):
        self.dimensions = max(16, dimensions)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    def _embed_single(self, text: str) -> list[float]:
        tokens = [token for token in re.split(r"\W+", text.lower()) if token]
        vector = [0.0 for _ in range(self.dimensions)]
        if not tokens:
            return vector

        for token in tokens:
            token_hash = hash(token)
            idx1 = abs(token_hash) % self.dimensions
            idx2 = abs(token_hash // 97) % self.dimensions
            sign = -1.0 if (token_hash & 1) else 1.0
            vector[idx1] += sign
            vector[idx2] += sign * 0.5

        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return vector
        return [value / norm for value in vector]
