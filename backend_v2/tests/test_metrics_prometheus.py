import unittest

from backend_v2.app.services.metrics_prometheus import snapshot_to_prometheus


class TestMetricsPrometheusExport(unittest.TestCase):
    def test_snapshot_to_prometheus_includes_core_metric_families(self):
        snapshot = {
            "totals": {"requests": 2, "fallback_requests": 1},
            "strategy_counts": {"hybrid": 2},
            "histograms": {
                "latency_ms": {"le_50": 1, "le_100": 1, "inf": 1},
                "returned_items": {"le_0": 1, "le_1": 1, "inf": 0},
            },
            "http_status": {
                "total": 4,
                "by_class": {"2xx": 2, "4xx": 1, "5xx": 1},
                "by_status": {"200": 2, "429": 1, "500": 1},
            },
            "audit_events": {"auth_failed": 1},
            "error_categories": {"provider": 1},
            "model_routing": {
                "routes": [
                    {
                        "stage": "analysis",
                        "requested_model": "model-a",
                        "used_model": "model-b",
                        "fallback": True,
                        "count": 1,
                    }
                ],
                "attempt_errors": [{"stage": "analysis", "model": "model-a", "count": 1}],
            },
            "windowed_rates": {
                "60s": {
                    "requests_per_minute": 4.0,
                    "errors_5xx_per_minute": 1.0,
                    "errors_5xx_percent": 25.0,
                    "rate_limit_429_per_minute": 1.0,
                    "rate_limit_429_percent": 25.0,
                    "auth_failed_per_minute": 1.0,
                }
            },
        }

        payload = snapshot_to_prometheus(snapshot)
        self.assertIn("ls_backend_v2_retrieval_requests_total 2", payload)
        self.assertIn('ls_backend_v2_retrieval_strategy_total{strategy="hybrid"} 2', payload)
        self.assertIn('ls_backend_v2_http_status_total{status="429"} 1', payload)
        self.assertIn('ls_backend_v2_error_category_total{category="provider"} 1', payload)
        self.assertIn(
            'ls_backend_v2_model_route_total{stage="analysis",requested_model="model-a",used_model="model-b",fallback="true"} 1',
            payload,
        )
        self.assertIn('ls_backend_v2_model_attempt_error_total{stage="analysis",model="model-a"} 1', payload)
        self.assertIn('ls_backend_v2_requests_per_minute{window="60s"} 4.0', payload)
        self.assertIn('ls_backend_v2_errors_5xx_percent{window="60s"} 25.0', payload)
        self.assertIn('ls_backend_v2_rate_limit_429_percent{window="60s"} 25.0', payload)

    def test_histogram_conversion_uses_cumulative_buckets(self):
        snapshot = {
            "totals": {},
            "strategy_counts": {},
            "histograms": {"latency_ms": {"le_50": 1, "le_100": 2, "inf": 3}},
            "http_status": {},
            "audit_events": {},
            "error_categories": {},
            "model_routing": {},
            "windowed_rates": {},
        }

        payload = snapshot_to_prometheus(snapshot)
        self.assertIn('ls_backend_v2_retrieval_latency_ms_bucket{le="50"} 1', payload)
        self.assertIn('ls_backend_v2_retrieval_latency_ms_bucket{le="100"} 3', payload)
        self.assertIn('ls_backend_v2_retrieval_latency_ms_bucket{le="+Inf"} 6', payload)
        self.assertIn("ls_backend_v2_retrieval_latency_ms_count 6", payload)

    def test_label_values_are_escaped(self):
        snapshot = {
            "totals": {},
            "strategy_counts": {},
            "histograms": {},
            "http_status": {},
            "audit_events": {'a"b\\c': 1},
            "error_categories": {},
            "model_routing": {},
            "windowed_rates": {},
        }

        payload = snapshot_to_prometheus(snapshot)
        self.assertIn('event="a\\"b\\\\c"', payload)
        self.assertTrue(payload.endswith("\n"))

    def test_snapshot_to_prometheus_skips_invalid_shapes_and_values(self):
        snapshot = {
            "totals": {"requests": "invalid", "fallback_requests": 2},
            "strategy_counts": {"hybrid": "invalid", "lexical": 1},
            "histograms": {
                "latency_ms": {"le_not_a_number": 9, "le_100": 1, "inf": 0},
                "broken_hist": "invalid",
            },
            "http_status": {"total": 1},
            "audit_events": {},
            "error_categories": {},
            "model_routing": {
                "routes": [
                    "invalid",
                    {"stage": "analysis", "requested_model": "model-a", "used_model": "model-b", "count": "invalid"},
                ],
                "attempt_errors": [
                    "invalid",
                    {"stage": "analysis", "count": "invalid"},
                ],
            },
            "windowed_rates": {"60s": {"requests_per_minute": "invalid"}, "broken": "invalid"},
        }

        payload = snapshot_to_prometheus(snapshot)
        self.assertIn("ls_backend_v2_retrieval_fallback_requests_total 2", payload)
        self.assertIn('ls_backend_v2_retrieval_strategy_total{strategy="lexical"} 1', payload)
        self.assertIn('ls_backend_v2_retrieval_latency_ms_bucket{le="100"} 1', payload)
        self.assertNotIn('ls_backend_v2_model_route_total{stage=', payload)
        self.assertNotIn('ls_backend_v2_model_attempt_error_total{stage=', payload)
        self.assertNotIn("invalid", payload)


if __name__ == "__main__":
    unittest.main()
