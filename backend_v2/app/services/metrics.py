from collections import deque
from threading import Lock
from time import monotonic
from typing import Callable

from backend_v2.app.services.retrieval import RetrievalStats


class RetrievalMetricsCollector:
    def __init__(
        self,
        latency_buckets_ms: tuple[float, ...] = (50, 100, 250, 500, 1000, 2000, 5000),
        returned_buckets: tuple[int, ...] = (0, 1, 2, 3, 5, 10),
        rate_windows_seconds: tuple[int, ...] = (60, 300),
        clock: Callable[[], float] = monotonic,
    ):
        self.latency_buckets_ms = tuple(sorted(latency_buckets_ms))
        self.returned_buckets = tuple(sorted(returned_buckets))
        self.rate_windows_seconds = tuple(sorted(rate_windows_seconds))
        self._max_rate_window_seconds = self.rate_windows_seconds[-1] if self.rate_windows_seconds else 60
        self._clock = clock
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
            self.http_total = 0
            self.http_by_class = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "other": 0}
            self.http_by_status: dict[str, int] = {}
            self.audit_events: dict[str, int] = {}
            self.error_categories: dict[str, int] = {}
            self._http_events: deque[tuple[float, int]] = deque()
            self._audit_event_times: dict[str, deque[float]] = {}

    def _prune_old_rate_events(self, now: float) -> None:
        cutoff = now - self._max_rate_window_seconds
        while self._http_events and self._http_events[0][0] < cutoff:
            self._http_events.popleft()

        for event_name in list(self._audit_event_times.keys()):
            timestamps = self._audit_event_times[event_name]
            while timestamps and timestamps[0] < cutoff:
                timestamps.popleft()
            if not timestamps:
                del self._audit_event_times[event_name]

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

    def record_http_status(self, status_code: int) -> None:
        with self._lock:
            now = self._clock()
            self._prune_old_rate_events(now)
            self._http_events.append((now, status_code))

            self.http_total += 1
            if 200 <= status_code <= 299:
                self.http_by_class["2xx"] += 1
            elif 300 <= status_code <= 399:
                self.http_by_class["3xx"] += 1
            elif 400 <= status_code <= 499:
                self.http_by_class["4xx"] += 1
            elif 500 <= status_code <= 599:
                self.http_by_class["5xx"] += 1
            else:
                self.http_by_class["other"] += 1
            key = str(status_code)
            self.http_by_status[key] = self.http_by_status.get(key, 0) + 1

    def record_audit_event(self, event_name: str) -> None:
        with self._lock:
            now = self._clock()
            self._prune_old_rate_events(now)
            timestamps = self._audit_event_times.get(event_name)
            if timestamps is None:
                timestamps = deque()
                self._audit_event_times[event_name] = timestamps
            timestamps.append(now)
            self.audit_events[event_name] = self.audit_events.get(event_name, 0) + 1

    def record_error_category(self, category: str) -> None:
        with self._lock:
            self.error_categories[category] = self.error_categories.get(category, 0) + 1

    @staticmethod
    def _rate_per_minute(count: int, window_seconds: int) -> float:
        if window_seconds <= 0:
            return 0.0
        return round((count * 60.0) / float(window_seconds), 2)

    def snapshot(self) -> dict:
        with self._lock:
            now = self._clock()
            self._prune_old_rate_events(now)

            windowed_rates: dict[str, dict[str, float]] = {}
            for window_seconds in self.rate_windows_seconds:
                cutoff = now - float(window_seconds)
                window_key = f"{window_seconds}s"

                request_count = 0
                status_429_count = 0
                status_5xx_count = 0
                for timestamp, status_code in self._http_events:
                    if timestamp < cutoff:
                        continue
                    request_count += 1
                    if status_code == 429:
                        status_429_count += 1
                    if 500 <= status_code <= 599:
                        status_5xx_count += 1

                auth_failed_count = 0
                auth_failed_timestamps = self._audit_event_times.get("auth_failed")
                if auth_failed_timestamps:
                    auth_failed_count = sum(1 for timestamp in auth_failed_timestamps if timestamp >= cutoff)

                windowed_rates[window_key] = {
                    "requests_per_minute": self._rate_per_minute(request_count, window_seconds),
                    "errors_5xx_per_minute": self._rate_per_minute(status_5xx_count, window_seconds),
                    "rate_limit_429_per_minute": self._rate_per_minute(status_429_count, window_seconds),
                    "auth_failed_per_minute": self._rate_per_minute(auth_failed_count, window_seconds),
                }

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
                "http_status": {
                    "total": self.http_total,
                    "by_class": dict(self.http_by_class),
                    "by_status": dict(self.http_by_status),
                },
                "audit_events": dict(self.audit_events),
                "error_categories": dict(self.error_categories),
                "windowed_rates": windowed_rates,
            }
