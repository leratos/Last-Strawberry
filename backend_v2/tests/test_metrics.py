import unittest

from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.retrieval import RetrievalStats


class _Clock:
    def __init__(self, start: float = 0.0):
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class TestRetrievalMetricsCollector(unittest.TestCase):
    def test_record_and_snapshot(self):
        collector = RetrievalMetricsCollector(
            latency_buckets_ms=(10, 100),
            returned_buckets=(0, 1, 3),
        )
        collector.record(
            RetrievalStats(
                strategy="hybrid",
                candidates_scanned=12,
                lexical_hits=2,
                semantic_hits=1,
                cache_hits=3,
                cache_misses=2,
                returned=2,
                fallback_used=False,
            ),
            latency_ms=42.0,
        )
        collector.record(
            RetrievalStats(
                strategy="lexical",
                candidates_scanned=6,
                lexical_hits=3,
                semantic_hits=0,
                cache_hits=0,
                cache_misses=0,
                returned=0,
                fallback_used=True,
            ),
            latency_ms=500.0,
        )

        snapshot = collector.snapshot()
        self.assertEqual(snapshot["totals"]["requests"], 2)
        self.assertEqual(snapshot["totals"]["fallback_requests"], 1)
        self.assertEqual(snapshot["totals"]["lexical_hits"], 5)
        self.assertEqual(snapshot["totals"]["semantic_hits"], 1)
        self.assertEqual(snapshot["totals"]["cache_hits"], 3)
        self.assertEqual(snapshot["totals"]["cache_misses"], 2)
        self.assertEqual(snapshot["strategy_counts"]["hybrid"], 1)
        self.assertEqual(snapshot["strategy_counts"]["lexical"], 1)
        self.assertEqual(snapshot["histograms"]["latency_ms"]["le_100"], 1)
        self.assertEqual(snapshot["histograms"]["latency_ms"]["inf"], 1)
        self.assertEqual(snapshot["histograms"]["returned_items"]["le_3"], 1)
        self.assertEqual(snapshot["histograms"]["returned_items"]["le_0"], 1)

        collector.record_http_status(200)
        collector.record_http_status(302)
        collector.record_http_status(429)
        collector.record_http_status(500)
        collector.record_http_status(102)
        collector.record_audit_event("auth_failed")
        collector.record_audit_event("auth_failed")
        collector.record_error_category("provider")
        collector.record_error_category("provider")
        collector.record_error_category("auth")
        collector.record_model_route(
            stage="analysis",
            requested_model="model-primary",
            used_model="model-fallback",
        )
        collector.record_model_route(
            stage="narrative",
            requested_model="model-primary",
            used_model="model-primary",
        )
        collector.record_model_attempt_error(stage="analysis", model="model-primary")
        collector.record_model_attempt(
            stage="analysis",
            model="model-fallback",
            latency_ms=1234.5,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            estimated_input_cost_usd=0.001,
            estimated_output_cost_usd=0.002,
            estimated_total_cost_usd=0.003,
            provider_reported_cost_usd=0.004,
        )
        collector.record_model_attempt(
            stage="analysis",
            model="model-fallback",
            latency_ms=2300.0,
            prompt_tokens=60,
            completion_tokens=20,
            total_tokens=80,
            estimated_input_cost_usd=0.0006,
            estimated_output_cost_usd=0.0004,
            estimated_total_cost_usd=0.001,
            provider_reported_cost_usd=0.0011,
        )

        snapshot = collector.snapshot()
        self.assertEqual(snapshot["http_status"]["total"], 5)
        self.assertEqual(snapshot["http_status"]["by_class"]["2xx"], 1)
        self.assertEqual(snapshot["http_status"]["by_class"]["3xx"], 1)
        self.assertEqual(snapshot["http_status"]["by_class"]["4xx"], 1)
        self.assertEqual(snapshot["http_status"]["by_class"]["5xx"], 1)
        self.assertEqual(snapshot["http_status"]["by_class"]["other"], 1)
        self.assertEqual(snapshot["http_status"]["by_status"]["429"], 1)
        self.assertEqual(snapshot["audit_events"]["auth_failed"], 2)
        self.assertEqual(snapshot["error_categories"]["provider"], 2)
        self.assertEqual(snapshot["error_categories"]["auth"], 1)

        model_routing = snapshot["model_routing"]
        self.assertEqual(len(model_routing["routes"]), 2)

        fallback_route = next(route for route in model_routing["routes"] if route["stage"] == "analysis")
        self.assertTrue(fallback_route["fallback"])
        self.assertEqual(fallback_route["requested_model"], "model-primary")
        self.assertEqual(fallback_route["used_model"], "model-fallback")
        self.assertEqual(fallback_route["count"], 1)

        attempt_error = model_routing["attempt_errors"][0]
        self.assertEqual(attempt_error["stage"], "analysis")
        self.assertEqual(attempt_error["model"], "model-primary")
        self.assertEqual(attempt_error["count"], 1)
        model_perf = snapshot["model_performance"]
        self.assertEqual(model_perf["totals"]["attempts"], 2)
        self.assertGreater(model_perf["totals"]["estimated_total_cost_usd"], 0.0)
        perf_entry = model_perf["attempts"][0]
        self.assertEqual(perf_entry["stage"], "analysis")
        self.assertEqual(perf_entry["model"], "model-fallback")
        self.assertEqual(perf_entry["count"], 2)
        self.assertGreater(perf_entry["latency_ms_p95"], 0.0)
        self.assertEqual(perf_entry["total_tokens"], 230)
        self.assertIn("60s", snapshot["windowed_rates"])
        self.assertIn("requests_per_minute", snapshot["windowed_rates"]["60s"])
        self.assertIn("errors_5xx_percent", snapshot["windowed_rates"]["60s"])
        self.assertIn("rate_limit_429_percent", snapshot["windowed_rates"]["60s"])
        self.assertIn("estimated_cost_usd_per_minute", snapshot["windowed_rates"]["60s"])
        self.assertIn("provider_reported_cost_usd_per_minute", snapshot["windowed_rates"]["60s"])

    def test_reset(self):
        collector = RetrievalMetricsCollector()
        collector.record(
            RetrievalStats(
                strategy="hybrid",
                candidates_scanned=1,
                lexical_hits=1,
                semantic_hits=0,
                cache_hits=0,
                cache_misses=0,
                returned=1,
                fallback_used=False,
            ),
            latency_ms=1.0,
        )
        collector.reset()
        snapshot = collector.snapshot()
        self.assertEqual(snapshot["totals"]["requests"], 0)
        self.assertEqual(snapshot["strategy_counts"], {})
        self.assertEqual(snapshot["http_status"]["total"], 0)
        self.assertEqual(snapshot["audit_events"], {})
        self.assertEqual(snapshot["error_categories"], {})
        self.assertEqual(snapshot["model_routing"]["routes"], [])
        self.assertEqual(snapshot["model_routing"]["attempt_errors"], [])
        self.assertEqual(snapshot["model_performance"]["attempts"], [])
        self.assertEqual(snapshot["model_performance"]["totals"]["attempts"], 0)
        self.assertEqual(snapshot["windowed_rates"]["60s"]["requests_per_minute"], 0.0)

    def test_windowed_rates_use_time_window(self):
        clock = _Clock(start=100.0)
        collector = RetrievalMetricsCollector(rate_windows_seconds=(60,), clock=clock)

        collector.record_http_status(200)
        collector.record_http_status(500)
        collector.record_http_status(429)
        collector.record_audit_event("auth_failed")
        collector.record_model_attempt(
            stage="analysis",
            model="model-a",
            latency_ms=100.0,
            estimated_total_cost_usd=0.006,
            provider_reported_cost_usd=0.007,
        )

        snapshot = collector.snapshot()
        rates = snapshot["windowed_rates"]["60s"]
        self.assertEqual(rates["requests_per_minute"], 3.0)
        self.assertEqual(rates["errors_5xx_per_minute"], 1.0)
        self.assertEqual(rates["errors_5xx_percent"], 33.33)
        self.assertEqual(rates["rate_limit_429_per_minute"], 1.0)
        self.assertEqual(rates["rate_limit_429_percent"], 33.33)
        self.assertEqual(rates["auth_failed_per_minute"], 1.0)
        self.assertEqual(rates["estimated_cost_usd_per_minute"], 0.006)
        self.assertEqual(rates["provider_reported_cost_usd_per_minute"], 0.007)

        clock.advance(61.0)
        snapshot = collector.snapshot()
        rates = snapshot["windowed_rates"]["60s"]
        self.assertEqual(rates["requests_per_minute"], 0.0)
        self.assertEqual(rates["errors_5xx_per_minute"], 0.0)
        self.assertEqual(rates["errors_5xx_percent"], 0.0)
        self.assertEqual(rates["rate_limit_429_per_minute"], 0.0)
        self.assertEqual(rates["rate_limit_429_percent"], 0.0)
        self.assertEqual(rates["auth_failed_per_minute"], 0.0)

    def test_windowed_rates_skip_events_outside_smaller_window(self):
        clock = _Clock(start=0.0)
        collector = RetrievalMetricsCollector(rate_windows_seconds=(60, 300), clock=clock)

        collector.record_http_status(200)
        clock.advance(200.0)

        snapshot = collector.snapshot()
        self.assertEqual(snapshot["windowed_rates"]["60s"]["requests_per_minute"], 0.0)
        self.assertGreater(snapshot["windowed_rates"]["300s"]["requests_per_minute"], 0.0)

    def test_rate_per_minute_guard_on_non_positive_window(self):
        self.assertEqual(RetrievalMetricsCollector._rate_per_minute(5, 0), 0.0)

    def test_percent_guard_on_non_positive_denominator(self):
        self.assertEqual(RetrievalMetricsCollector._percent(5, 0), 0.0)

    def test_quantile_handles_empty_and_bounds(self):
        self.assertEqual(RetrievalMetricsCollector._quantile([], 0.95), 0.0)
        self.assertEqual(RetrievalMetricsCollector._quantile([1.0, 3.0, 2.0], 0.0), 1.0)
        self.assertEqual(RetrievalMetricsCollector._quantile([1.0, 3.0, 2.0], 1.0), 3.0)

    def test_windowed_cost_rates_skip_events_outside_smaller_window(self):
        clock = _Clock(start=0.0)
        collector = RetrievalMetricsCollector(rate_windows_seconds=(60, 300), clock=clock)

        collector.record_model_attempt(
            stage="analysis",
            model="model-a",
            latency_ms=50.0,
            estimated_total_cost_usd=0.005,
            provider_reported_cost_usd=0.006,
        )

        clock.advance(200.0)
        snapshot = collector.snapshot()

        rates_60 = snapshot["windowed_rates"]["60s"]
        rates_300 = snapshot["windowed_rates"]["300s"]
        self.assertEqual(rates_60["estimated_cost_usd_per_minute"], 0.0)
        self.assertEqual(rates_60["provider_reported_cost_usd_per_minute"], 0.0)
        self.assertGreater(rates_300["estimated_cost_usd_per_minute"], 0.0)
        self.assertGreater(rates_300["provider_reported_cost_usd_per_minute"], 0.0)


if __name__ == "__main__":
    unittest.main()
