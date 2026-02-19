import re
from dataclasses import dataclass
from typing import Any, Protocol

from backend_v2.app.persistence import SQLiteRepository


@dataclass(frozen=True)
class RetrievalStats:
    strategy: str
    candidates_scanned: int
    lexical_hits: int
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
            returned=len(items),
            fallback_used=False,
        )
        return RetrievalResult(items=items, stats=stats)


class HybridMemoryRetriever:
    strategy = "hybrid"

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
                returned=len(items),
                fallback_used=True,
            )
            return RetrievalResult(items=items, stats=stats)

        scored: list[tuple[float, dict[str, Any]]] = []
        lexical_hits = 0
        pool_size = len(candidates)
        for rank, item in enumerate(candidates):
            content_terms = {term for term in re.split(r"\W+", str(item["content"]).lower()) if term}
            overlap = len(query_terms.intersection(content_terms))
            if overlap <= 0:
                continue
            lexical_hits += 1

            recency_bonus = (pool_size - rank) / pool_size * 0.25
            score = overlap * 3.0 + float(item["importance"]) + recency_bonus
            scored.append((score, item))

        if not scored:
            items = candidates[:safe_limit]
            stats = RetrievalStats(
                strategy=self.strategy,
                candidates_scanned=len(candidates),
                lexical_hits=0,
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
            returned=len(items),
            fallback_used=False,
        )
        return RetrievalResult(items=items, stats=stats)
