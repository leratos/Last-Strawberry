import unittest

from backend_v2.app.services.metrics import RetrievalMetricsCollector
from backend_v2.app.services.retrieval import RetrievalStats


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


if __name__ == "__main__":
    unittest.main()
