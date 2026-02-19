from threading import Lock

from backend_v2.app.services.retrieval import RetrievalStats


class RetrievalMetricsCollector:
    def __init__(
        self,
        latency_buckets_ms: tuple[float, ...] = (50, 100, 250, 500, 1000, 2000, 5000),
        returned_buckets: tuple[int, ...] = (0, 1, 2, 3, 5, 10),
    ):
        self.latency_buckets_ms = tuple(sorted(latency_buckets_ms))
        self.returned_buckets = tuple(sorted(returned_buckets))
        self._lock = Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.total_requests = 0
            self.fallback_requests = 0
            self.lexical_hits_total = 0
            self.semantic_hits_total = 0
            self.cache_hits_total = 0
            self.cache_misses_total = 0
            self.returned_total = 0
            self.candidates_scanned_total = 0
            self.strategy_counts: dict[str, int] = {}
            self.latency_hist = self._init_hist(self.latency_buckets_ms)
            self.returned_hist = self._init_hist(self.returned_buckets)

    @staticmethod
    def _init_hist(buckets: tuple[float | int, ...]) -> dict[str, int]:
        hist: dict[str, int] = {}
        for bucket in buckets:
            hist[f"le_{bucket}"] = 0
        hist["inf"] = 0
        return hist

    @staticmethod
    def _observe(value: float, buckets: tuple[float | int, ...], hist: dict[str, int]) -> None:
        for bucket in buckets:
            if value <= float(bucket):
                hist[f"le_{bucket}"] += 1
                return
        hist["inf"] += 1

    def record(self, stats: RetrievalStats, latency_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            if stats.fallback_used:
                self.fallback_requests += 1
            self.lexical_hits_total += stats.lexical_hits
            self.semantic_hits_total += stats.semantic_hits
            self.cache_hits_total += stats.cache_hits
            self.cache_misses_total += stats.cache_misses
            self.returned_total += stats.returned
            self.candidates_scanned_total += stats.candidates_scanned
            self.strategy_counts[stats.strategy] = self.strategy_counts.get(stats.strategy, 0) + 1

            self._observe(latency_ms, self.latency_buckets_ms, self.latency_hist)
            self._observe(float(stats.returned), self.returned_buckets, self.returned_hist)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "totals": {
                    "requests": self.total_requests,
                    "fallback_requests": self.fallback_requests,
                    "lexical_hits": self.lexical_hits_total,
                    "semantic_hits": self.semantic_hits_total,
                    "cache_hits": self.cache_hits_total,
                    "cache_misses": self.cache_misses_total,
                    "returned_items": self.returned_total,
                    "candidates_scanned": self.candidates_scanned_total,
                },
                "strategy_counts": dict(self.strategy_counts),
                "histograms": {
                    "latency_ms": dict(self.latency_hist),
                    "returned_items": dict(self.returned_hist),
                },
            }
