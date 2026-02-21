import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[2]
OPS_SCRIPT_PATH = REPO_ROOT / "backend_v2" / "scripts" / "ops_phase5_report.py"
SMOKE_SLO_SCRIPT_PATH = REPO_ROOT / "backend_v2" / "scripts" / "smoke_slo.py"


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestOpsScriptsEnvDefaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ops_module = _load_module(OPS_SCRIPT_PATH, "ops_phase5_report_module")
        cls.smoke_module = _load_module(SMOKE_SLO_SCRIPT_PATH, "smoke_slo_module")

    def test_ops_parse_args_uses_ops_env_defaults(self):
        with patch.dict(
            "os.environ",
            {
                "LS_OPS_WINDOW": "600s",
                "LS_OPS_MAX_5XX_PERCENT": "0.7",
                "LS_OPS_MAX_429_PERCENT": "3.5",
                "LS_OPS_MAX_ESTIMATED_COST_PER_MINUTE": "0.08",
                "LS_OPS_MAX_PROVIDER_COST_PER_MINUTE": "0.06",
                "LS_OPS_REQUIRE_PROMETHEUS_FAMILIES": "true",
            },
            clear=False,
        ):
            args = self.ops_module.parse_args([])

        self.assertEqual(args.window, "600s")
        self.assertEqual(args.max_5xx, 0.7)
        self.assertEqual(args.max_429, 3.5)
        self.assertEqual(args.max_estimated_cost_per_minute, 0.08)
        self.assertEqual(args.max_provider_cost_per_minute, 0.06)
        self.assertTrue(args.require_prometheus_families)

    def test_ops_parse_args_falls_back_to_slo_env(self):
        with patch.dict(
            "os.environ",
            {
                "LS_OPS_WINDOW": "",
                "LS_OPS_MAX_5XX_PERCENT": "",
                "LS_OPS_MAX_429_PERCENT": "",
                "LS_SLO_WINDOW": "420s",
                "LS_SLO_MAX_5XX_PERCENT": "0.9",
                "LS_SLO_MAX_429_PERCENT": "4.9",
            },
            clear=False,
        ):
            args = self.ops_module.parse_args([])

        self.assertEqual(args.window, "420s")
        self.assertEqual(args.max_5xx, 0.9)
        self.assertEqual(args.max_429, 4.9)

    def test_ops_parse_args_cli_overrides_env_default(self):
        with patch.dict(
            "os.environ",
            {
                "LS_OPS_MAX_5XX_PERCENT": "0.7",
            },
            clear=False,
        ):
            args = self.ops_module.parse_args(["--max-5xx", "1.4", "--no-require-prometheus-families"])

        self.assertEqual(args.max_5xx, 1.4)
        self.assertFalse(args.require_prometheus_families)

    def test_resolve_metrics_key_prefers_cli_and_env(self):
        with patch.dict("os.environ", {"LS_METRICS_API_KEY": "env-key-123"}, clear=False):
            cli_key, cli_source = self.ops_module._resolve_metrics_key("cli-key-999")
            env_key, env_source = self.ops_module._resolve_metrics_key("")

        self.assertEqual(cli_key, "cli-key-999")
        self.assertEqual(cli_source, "cli")
        self.assertEqual(env_key, "env-key-123")
        self.assertEqual(env_source, "env")

    def test_read_env_value_from_file_supports_export_and_quotes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text(
                "\n".join(
                    [
                        "# comment",
                        "export LS_METRICS_API_KEY='quoted-value'",
                    ]
                ),
                encoding="utf-8",
            )
            value = self.ops_module._read_env_value_from_file("LS_METRICS_API_KEY", env_file)
        self.assertEqual(value, "quoted-value")

    def test_smoke_slo_parse_args_uses_env_threshold_defaults(self):
        with patch.dict(
            "os.environ",
            {
                "LS_OPS_SLO_OVERRIDE_WINDOW": "75s",
                "LS_OPS_MAX_5XX_PERCENT": "0.6",
                "LS_OPS_MAX_429_PERCENT": "2.8",
            },
            clear=False,
        ):
            args = self.smoke_module.parse_args([])

        self.assertEqual(args.window, "75s")
        self.assertEqual(args.max_5xx, 0.6)
        self.assertEqual(args.max_429, 2.8)


if __name__ == "__main__":
    unittest.main()
