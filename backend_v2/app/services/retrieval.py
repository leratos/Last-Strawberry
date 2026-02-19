import math
import re
from dataclasses import dataclass
from typing import Any, Protocol

from backend_v2.app.persistence import SQLiteRepository
from backend_v2.app.services.embeddings import EmbeddingsProvider


@dataclass(frozen=True)
class RetrievalStats:
    strategy: str
    candidates_scanned: int
    lexical_hits: int
    semantic_hits: int
    returned: int
    fallback_used: bool


@dataclass(frozen=True)
class RetrievalResult:
    items: list[dict[str, Any]]
    stats: RetrievalStats


class MemoryRetriever(Protocol):
    strategy: str

    def retrieve(
        self,
        *,
        repository: SQLiteRepository,
        world_id: int,
        query: str,
        limit: int,
        min_importance: float,
    ) -> RetrievalResult:
        ...


class LexicalMemoryRetriever:
    strategy = "lexical"

    def retrieve(
        self,
        *,
        repository: SQLiteRepository,
        world_id: int,
        query: str,
        limit: int,
        min_importance: float,
    ) -> RetrievalResult:
        safe_limit = max(1, min(limit, 20))
        items = repository.search_memory_items(
            world_id=world_id,
            query=query,
            limit=safe_limit,
            min_importance=min_importance,
        )
        stats = RetrievalStats(
            strategy=self.strategy,
            candidates_scanned=len(items),
            lexical_hits=len(items),
            semantic_hits=0,
            returned=len(items),
            fallback_used=False,
        )
        return RetrievalResult(items=items, stats=stats)


class HybridMemoryRetriever:
    strategy = "hybrid"

    def __init__(
        self,
        embeddings_provider: EmbeddingsProvider | None = None,
        vector_weight: float = 1.2,
        semantic_min_similarity: float = 0.2,
    ):
        self.embeddings_provider = embeddings_provider
        self.vector_weight = max(0.0, vector_weight)
        self.semantic_min_similarity = max(0.0, min(1.0, semantic_min_similarity))

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        if len(a) != len(b) or not a:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def retrieve(
        self,
        *,
        repository: SQLiteRepository,
        world_id: int,
        query: str,
        limit: int,
        min_importance: float,
    ) -> RetrievalResult:
        safe_limit = max(1, min(limit, 20))
        candidate_limit = max(20, safe_limit * 8)
        candidates = repository.list_memory_items(
            world_id=world_id,
            limit=candidate_limit,
            min_importance=min_importance,
        )
        if not candidates:
            stats = RetrievalStats(
                strategy=self.strategy,
                candidates_scanned=0,
                lexical_hits=0,
                semantic_hits=0,
                returned=0,
                fallback_used=True,
            )
            return RetrievalResult(items=[], stats=stats)

        query_terms = {term for term in re.split(r"\W+", query.lower()) if term}
        if not query_terms:
            items = candidates[:safe_limit]
            stats = RetrievalStats(
                strategy=self.strategy,
                candidates_scanned=len(candidates),
                lexical_hits=0,
                semantic_hits=0,
                returned=len(items),
                fallback_used=True,
            )
            return RetrievalResult(items=items, stats=stats)

        semantic_scores: list[float] = [0.0 for _ in candidates]
        if self.embeddings_provider is not None:
            try:
                contents = [str(item.get("content", "")) for item in candidates]
                vectors = self.embeddings_provider.embed_texts([query] + contents)
                if len(vectors) == len(candidates) + 1:
                    query_vector = vectors[0]
                    semantic_scores = [
                        self._cosine_similarity(query_vector, vectors[idx + 1]) for idx in range(len(candidates))
                    ]
            except Exception:
                semantic_scores = [0.0 for _ in candidates]

        scored: list[tuple[float, dict[str, Any]]] = []
        lexical_hits = 0
        semantic_hits = 0
        pool_size = len(candidates)
        for rank, item in enumerate(candidates):
            content_terms = {term for term in re.split(r"\W+", str(item["content"]).lower()) if term}
            overlap = len(query_terms.intersection(content_terms))
            semantic_score = semantic_scores[rank] if rank < len(semantic_scores) else 0.0

            include = overlap > 0 or semantic_score >= self.semantic_min_similarity
            if not include:
                continue
            if overlap > 0:
                lexical_hits += 1
            elif semantic_score >= self.semantic_min_similarity:
                semantic_hits += 1

            recency_bonus = (pool_size - rank) / pool_size * 0.25
            score = overlap * 3.0 + float(item["importance"]) + recency_bonus + semantic_score * self.vector_weight
            scored.append((score, item))

        if not scored:
            items = candidates[:safe_limit]
            stats = RetrievalStats(
                strategy=self.strategy,
                candidates_scanned=len(candidates),
                lexical_hits=0,
                semantic_hits=0,
                returned=len(items),
                fallback_used=True,
            )
            return RetrievalResult(items=items, stats=stats)

        scored.sort(key=lambda pair: pair[0], reverse=True)
        items = [item for _, item in scored[:safe_limit]]
        stats = RetrievalStats(
            strategy=self.strategy,
            candidates_scanned=len(candidates),
            lexical_hits=lexical_hits,
            semantic_hits=semantic_hits,
            returned=len(items),
            fallback_used=False,
        )
        return RetrievalResult(items=items, stats=stats)
