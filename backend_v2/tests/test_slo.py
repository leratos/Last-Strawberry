import unittest

from backend_v2.app.services.slo import evaluate_slo


class TestSloEvaluation(unittest.TestCase):
    def test_evaluate_slo_ok_when_within_thresholds(self):
        snapshot = {
            "windowed_rates": {
                "300s": {
                    "errors_5xx_percent": 0.4,
                    "rate_limit_429_percent": 1.2,
                }
            }
        }

        result = evaluate_slo(
            snapshot=snapshot,
            window="300s",
            max_5xx_percent=1.0,
            max_429_percent=5.0,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["breaches"], [])

    def test_evaluate_slo_detects_breaches(self):
        snapshot = {
            "windowed_rates": {
                "60s": {
                    "errors_5xx_percent": 2.0,
                    "rate_limit_429_percent": 9.5,
                }
            }
        }

        result = evaluate_slo(
            snapshot=snapshot,
            window="60s",
            max_5xx_percent=1.0,
            max_429_percent=5.0,
        )

        self.assertEqual(result["status"], "breach")
        self.assertIn("errors_5xx_percent", result["breaches"])
        self.assertIn("rate_limit_429_percent", result["breaches"])

    def test_evaluate_slo_handles_missing_window(self):
        snapshot = {"windowed_rates": {"60s": {"errors_5xx_percent": 2.0}}}

        result = evaluate_slo(
            snapshot=snapshot,
            window="300s",
            max_5xx_percent=1.0,
            max_429_percent=5.0,
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["actual"]["errors_5xx_percent"], 0.0)
        self.assertEqual(result["actual"]["rate_limit_429_percent"], 0.0)

    def test_evaluate_slo_handles_invalid_shapes(self):
        snapshot = {"windowed_rates": "invalid"}
        result = evaluate_slo(
            snapshot=snapshot,
            window="300s",
            max_5xx_percent=1.0,
            max_429_percent=5.0,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["actual"]["errors_5xx_percent"], 0.0)
        self.assertEqual(result["actual"]["rate_limit_429_percent"], 0.0)

        snapshot_with_invalid_window = {"windowed_rates": {"300s": "invalid"}}
        result = evaluate_slo(
            snapshot=snapshot_with_invalid_window,
            window="300s",
            max_5xx_percent=1.0,
            max_429_percent=5.0,
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["actual"]["errors_5xx_percent"], 0.0)


if __name__ == "__main__":
    unittest.main()
