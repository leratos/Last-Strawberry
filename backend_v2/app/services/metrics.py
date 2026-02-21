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
            self.model_route_counts: dict[tuple[str, str, str, bool], int] = {}
            self.model_attempt_errors: dict[tuple[str, str], int] = {}
            self.model_attempt_stats: dict[tuple[str, str], dict[str, object]] = {}
            self._http_events: deque[tuple[float, int]] = deque()
            self._cost_events: deque[tuple[float, float, float]] = deque()
            self._audit_event_times: dict[str, deque[float]] = {}

    def _prune_old_rate_events(self, now: float) -> None:
        cutoff = now - self._max_rate_window_seconds
        while self._http_events and self._http_events[0][0] < cutoff:
            self._http_events.popleft()
        while self._cost_events and self._cost_events[0][0] < cutoff:
            self._cost_events.popleft()

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

    def record_model_route(self, *, stage: str, requested_model: str, used_model: str) -> None:
        with self._lock:
            stage_clean = stage.strip() or "unknown"
            requested_clean = requested_model.strip() or "unknown"
            used_clean = used_model.strip() or "unknown"
            fallback_used = requested_clean != used_clean
            key = (stage_clean, requested_clean, used_clean, fallback_used)
            self.model_route_counts[key] = self.model_route_counts.get(key, 0) + 1

    def record_model_attempt_error(self, *, stage: str, model: str) -> None:
        with self._lock:
            stage_clean = stage.strip() or "unknown"
            model_clean = model.strip() or "unknown"
            key = (stage_clean, model_clean)
            self.model_attempt_errors[key] = self.model_attempt_errors.get(key, 0) + 1

    @staticmethod
    def _rate_per_minute(count: int, window_seconds: int) -> float:
        if window_seconds <= 0:
            return 0.0
        return round((count * 60.0) / float(window_seconds), 2)

    @staticmethod
    def _percent(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((float(numerator) * 100.0) / float(denominator), 2)

    @staticmethod
    def _quantile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        if q <= 0:
            return round(min(values), 2)
        if q >= 1:
            return round(max(values), 2)

        ordered = sorted(values)
        index = int((len(ordered) - 1) * q)
        return round(float(ordered[index]), 2)

    def record_model_attempt(
        self,
        *,
        stage: str,
        model: str,
        latency_ms: float,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        estimated_input_cost_usd: float = 0.0,
        estimated_output_cost_usd: float = 0.0,
        estimated_total_cost_usd: float = 0.0,
        provider_reported_cost_usd: float | None = None,
    ) -> None:
        with self._lock:
            stage_clean = stage.strip() or "unknown"
            model_clean = model.strip() or "unknown"
            key = (stage_clean, model_clean)
            now = self._clock()
            self._prune_old_rate_events(now)

            stats = self.model_attempt_stats.get(key)
            if stats is None:
                stats = {
                    "count": 0,
                    "latency_sum_ms": 0.0,
                    "latency_max_ms": 0.0,
                    "latencies_ms": deque(maxlen=2048),
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_input_cost_usd": 0.0,
                    "estimated_output_cost_usd": 0.0,
                    "estimated_total_cost_usd": 0.0,
                    "provider_reported_cost_usd": 0.0,
                }
                self.model_attempt_stats[key] = stats

            latency_clean = max(0.0, float(latency_ms))
            prompt_clean = max(0, int(prompt_tokens))
            completion_clean = max(0, int(completion_tokens))
            total_clean = max(0, int(total_tokens or (prompt_clean + completion_clean)))
            estimated_input_clean = max(0.0, float(estimated_input_cost_usd))
            estimated_output_clean = max(0.0, float(estimated_output_cost_usd))
            estimated_total_clean = max(0.0, float(estimated_total_cost_usd))
            provider_total_clean = max(0.0, float(provider_reported_cost_usd or 0.0))

            stats["count"] = int(stats["count"]) + 1
            stats["latency_sum_ms"] = float(stats["latency_sum_ms"]) + latency_clean
            stats["latency_max_ms"] = max(float(stats["latency_max_ms"]), latency_clean)
            stats["prompt_tokens"] = int(stats["prompt_tokens"]) + prompt_clean
            stats["completion_tokens"] = int(stats["completion_tokens"]) + completion_clean
            stats["total_tokens"] = int(stats["total_tokens"]) + total_clean
            stats["estimated_input_cost_usd"] = float(stats["estimated_input_cost_usd"]) + estimated_input_clean
            stats["estimated_output_cost_usd"] = float(stats["estimated_output_cost_usd"]) + estimated_output_clean
            stats["estimated_total_cost_usd"] = float(stats["estimated_total_cost_usd"]) + estimated_total_clean
            stats["provider_reported_cost_usd"] = float(stats["provider_reported_cost_usd"]) + provider_total_clean

            latencies_ms = stats["latencies_ms"]
            if isinstance(latencies_ms, deque):
                latencies_ms.append(latency_clean)

            self._cost_events.append((now, estimated_total_clean, provider_total_clean))

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

                estimated_cost_total = 0.0
                provider_cost_total = 0.0
                for timestamp, estimated_cost, provider_cost in self._cost_events:
                    if timestamp < cutoff:
                        continue
                    estimated_cost_total += estimated_cost
                    provider_cost_total += provider_cost

                windowed_rates[window_key] = {
                    "requests_per_minute": self._rate_per_minute(request_count, window_seconds),
                    "errors_5xx_per_minute": self._rate_per_minute(status_5xx_count, window_seconds),
                    "errors_5xx_percent": self._percent(status_5xx_count, request_count),
                    "rate_limit_429_per_minute": self._rate_per_minute(status_429_count, window_seconds),
                    "rate_limit_429_percent": self._percent(status_429_count, request_count),
                    "auth_failed_per_minute": self._rate_per_minute(auth_failed_count, window_seconds),
                    "estimated_cost_usd_per_minute": self._rate_per_minute(
                        int(round(estimated_cost_total * 1_000_000)),
                        window_seconds,
                    )
                    / 1_000_000.0,
                    "provider_reported_cost_usd_per_minute": self._rate_per_minute(
                        int(round(provider_cost_total * 1_000_000)),
                        window_seconds,
                    )
                    / 1_000_000.0,
                }

            model_performance_attempts: list[dict[str, object]] = []
            model_performance_totals = {
                "attempts": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "estimated_input_cost_usd": 0.0,
                "estimated_output_cost_usd": 0.0,
                "estimated_total_cost_usd": 0.0,
                "provider_reported_cost_usd": 0.0,
            }
            for (stage, model), stats in sorted(self.model_attempt_stats.items()):
                count = int(stats.get("count", 0))
                latency_sum_ms = float(stats.get("latency_sum_ms", 0.0))
                latency_max_ms = float(stats.get("latency_max_ms", 0.0))
                prompt_tokens = int(stats.get("prompt_tokens", 0))
                completion_tokens = int(stats.get("completion_tokens", 0))
                total_tokens = int(stats.get("total_tokens", 0))
                estimated_input_cost_usd = float(stats.get("estimated_input_cost_usd", 0.0))
                estimated_output_cost_usd = float(stats.get("estimated_output_cost_usd", 0.0))
                estimated_total_cost_usd = float(stats.get("estimated_total_cost_usd", 0.0))
                provider_reported_cost_usd = float(stats.get("provider_reported_cost_usd", 0.0))
                latencies_ms = stats.get("latencies_ms", deque())
                latency_values = list(latencies_ms) if isinstance(latencies_ms, deque) else []

                model_performance_attempts.append(
                    {
                        "stage": stage,
                        "model": model,
                        "count": count,
                        "latency_ms_avg": round((latency_sum_ms / count), 2) if count > 0 else 0.0,
                        "latency_ms_p95": self._quantile(latency_values, 0.95),
                        "latency_ms_p99": self._quantile(latency_values, 0.99),
                        "latency_ms_max": round(latency_max_ms, 2),
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "estimated_input_cost_usd": round(estimated_input_cost_usd, 8),
                        "estimated_output_cost_usd": round(estimated_output_cost_usd, 8),
                        "estimated_total_cost_usd": round(estimated_total_cost_usd, 8),
                        "provider_reported_cost_usd": round(provider_reported_cost_usd, 8),
                    }
                )

                model_performance_totals["attempts"] += count
                model_performance_totals["prompt_tokens"] += prompt_tokens
                model_performance_totals["completion_tokens"] += completion_tokens
                model_performance_totals["total_tokens"] += total_tokens
                model_performance_totals["estimated_input_cost_usd"] += estimated_input_cost_usd
                model_performance_totals["estimated_output_cost_usd"] += estimated_output_cost_usd
                model_performance_totals["estimated_total_cost_usd"] += estimated_total_cost_usd
                model_performance_totals["provider_reported_cost_usd"] += provider_reported_cost_usd

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
                "model_routing": {
                    "routes": [
                        {
                            "stage": stage,
                            "requested_model": requested,
                            "used_model": used,
                            "fallback": fallback,
                            "count": count,
                        }
                        for (stage, requested, used, fallback), count in sorted(self.model_route_counts.items())
                    ],
                    "attempt_errors": [
                        {
                            "stage": stage,
                            "model": model,
                            "count": count,
                        }
                        for (stage, model), count in sorted(self.model_attempt_errors.items())
                    ],
                },
                "model_performance": {
                    "attempts": model_performance_attempts,
                    "totals": {
                        "attempts": model_performance_totals["attempts"],
                        "prompt_tokens": model_performance_totals["prompt_tokens"],
                        "completion_tokens": model_performance_totals["completion_tokens"],
                        "total_tokens": model_performance_totals["total_tokens"],
                        "estimated_input_cost_usd": round(model_performance_totals["estimated_input_cost_usd"], 8),
                        "estimated_output_cost_usd": round(model_performance_totals["estimated_output_cost_usd"], 8),
                        "estimated_total_cost_usd": round(model_performance_totals["estimated_total_cost_usd"], 8),
                        "provider_reported_cost_usd": round(model_performance_totals["provider_reported_cost_usd"], 8),
                    },
                },
                "windowed_rates": windowed_rates,
            }
