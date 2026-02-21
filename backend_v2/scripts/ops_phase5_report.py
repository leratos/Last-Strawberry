#!/usr/bin/env python
import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _read_float_env(key: str, default: float) -> float:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _read_bool_env(key: str, default: bool) -> bool:
    raw = (os.getenv(key) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _window_key(value: str) -> str:
    raw = (value or "").strip()
    return raw if raw.endswith("s") else f"{raw}s"


def _read_env_value_from_file(key: str, env_path: Path) -> str:
    if not env_path.exists():
        return ""
    try:
        lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return ""

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        lhs, sep, rhs = line.partition("=")
        if not sep:
            continue
        if lhs.strip() != key:
            continue
        value = rhs.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return value.strip()
    return ""


def _resolve_metrics_key(cli_value: str) -> tuple[str, str]:
    explicit = (cli_value or "").strip()
    if explicit:
        return explicit, "cli"

    env_value = os.getenv("LS_METRICS_API_KEY", "").strip()
    if env_value:
        return env_value, "env"

    local_env_candidates = [Path("backend_v2/.env"), Path(".env")]
    for env_path in local_env_candidates:
        file_value = _read_env_value_from_file("LS_METRICS_API_KEY", env_path)
        if file_value:
            return file_value, str(env_path)

    return "", "none"


def _get_with_auth(
    client: httpx.Client,
    url: str,
    *,
    token: str | None = None,
    metrics_key: str | None = None,
    metrics_key_header: str = "X-Metrics-Key",
) -> httpx.Response:
    headers: dict[str, str] = {}
    if metrics_key:
        headers[metrics_key_header] = metrics_key
    elif token:
        headers["Authorization"] = f"Bearer {token}"
    return client.get(url, headers=headers)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_window = (os.getenv("LS_OPS_WINDOW") or os.getenv("LS_SLO_WINDOW") or "300s").strip() or "300s"
    default_max_5xx = _read_float_env("LS_OPS_MAX_5XX_PERCENT", _read_float_env("LS_SLO_MAX_5XX_PERCENT", 1.0))
    default_max_429 = _read_float_env("LS_OPS_MAX_429_PERCENT", _read_float_env("LS_SLO_MAX_429_PERCENT", 5.0))
    default_max_estimated_cost = _read_float_env("LS_OPS_MAX_ESTIMATED_COST_PER_MINUTE", 0.10)
    default_max_provider_cost = _read_float_env("LS_OPS_MAX_PROVIDER_COST_PER_MINUTE", 0.10)
    default_require_prometheus = _read_bool_env("LS_OPS_REQUIRE_PROMETHEUS_FAMILIES", False)

    parser = argparse.ArgumentParser(
        description="Phase 5 ops report for backend_v2 (health, SLO, cost rate, metrics presence)."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8002", help="backend_v2 base URL")
    parser.add_argument("--user-id", type=int, default=1, help="Login user_id for JWT auth")
    parser.add_argument("--username", default="phase5-ops", help="Login username for JWT auth")
    parser.add_argument(
        "--window",
        default=default_window,
        help="Window key (e.g. 60s, 300s). Env fallback: LS_OPS_WINDOW -> LS_SLO_WINDOW.",
    )
    parser.add_argument(
        "--max-5xx",
        type=float,
        default=default_max_5xx,
        help="SLO max 5xx percent. Env fallback: LS_OPS_MAX_5XX_PERCENT -> LS_SLO_MAX_5XX_PERCENT.",
    )
    parser.add_argument(
        "--max-429",
        type=float,
        default=default_max_429,
        help="SLO max 429 percent. Env fallback: LS_OPS_MAX_429_PERCENT -> LS_SLO_MAX_429_PERCENT.",
    )
    parser.add_argument(
        "--max-estimated-cost-per-minute",
        type=float,
        default=default_max_estimated_cost,
        help="Max estimated cost USD/min for selected window (0 disables check). Env: LS_OPS_MAX_ESTIMATED_COST_PER_MINUTE.",
    )
    parser.add_argument(
        "--max-provider-cost-per-minute",
        type=float,
        default=default_max_provider_cost,
        help="Max provider-reported cost USD/min for selected window (0 disables check). Env: LS_OPS_MAX_PROVIDER_COST_PER_MINUTE.",
    )
    parser.add_argument(
        "--require-prometheus-families",
        action="store_true",
        default=default_require_prometheus,
        help="Require key Prometheus metric families to be present in /v2/metrics/prometheus output",
    )
    parser.add_argument(
        "--no-require-prometheus-families",
        action="store_false",
        dest="require_prometheus_families",
        help="Disable required Prometheus families check even if LS_OPS_REQUIRE_PROMETHEUS_FAMILIES=true.",
    )
    parser.add_argument("--metrics-key", default="", help="Optional LS_METRICS_API_KEY value")
    parser.add_argument("--metrics-key-header", default="X-Metrics-Key", help="Metrics key header name")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    parser.add_argument("--output", default="", help="Optional output JSON path")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    base_url = args.base_url.rstrip("/")
    window = _window_key(args.window)
    timeout_seconds = max(1.0, float(args.timeout))

    report: dict[str, object] = {
        "timestamp_unix": int(time.time()),
        "inputs": {
            "base_url": base_url,
            "window": window,
            "max_5xx_percent": args.max_5xx,
            "max_429_percent": args.max_429,
            "max_estimated_cost_per_minute": args.max_estimated_cost_per_minute,
            "max_provider_cost_per_minute": args.max_provider_cost_per_minute,
            "require_prometheus_families": bool(args.require_prometheus_families),
            "metrics_key_header": args.metrics_key_header,
        },
        "checks": [],
    }
    checks: list[dict[str, object]] = report["checks"]  # type: ignore[assignment]

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            login_response = client.post(
                f"{base_url}/v2/auth/login",
                json={"user_id": args.user_id, "username": args.username},
            )
            login_response.raise_for_status()
            access_token = str(login_response.json().get("access_token") or "")
            if not access_token:
                raise RuntimeError("Missing access_token in /v2/auth/login response.")

            health_response = _get_with_auth(client, f"{base_url}/v2/health", token=access_token)
            health_response.raise_for_status()
            health_payload = health_response.json()
            checks.append(
                {
                    "name": "v2_health",
                    "ok": health_response.status_code == 200 and str(health_payload.get("status")) == "ok",
                    "status_code": health_response.status_code,
                    "payload": health_payload,
                }
            )

            slo_response = _get_with_auth(
                client,
                f"{base_url}/v2/metrics/slo?window={window}&max_5xx_percent={args.max_5xx}&max_429_percent={args.max_429}",
                token=access_token,
            )
            slo_response.raise_for_status()
            slo_payload = slo_response.json()
            checks.append(
                {
                    "name": "slo_status",
                    "ok": str(slo_payload.get("status")) == "ok",
                    "status_code": slo_response.status_code,
                    "payload": slo_payload,
                }
            )

            retrieval_response = _get_with_auth(client, f"{base_url}/v2/metrics/retrieval", token=access_token)
            retrieval_response.raise_for_status()
            retrieval_payload = retrieval_response.json()
            window_rates = retrieval_payload.get("windowed_rates", {}).get(window, {})
            estimated_cost = _to_float(window_rates.get("estimated_cost_usd_per_minute"), 0.0)
            provider_cost = _to_float(window_rates.get("provider_reported_cost_usd_per_minute"), 0.0)

            cost_ok = True
            if args.max_estimated_cost_per_minute > 0:
                cost_ok = cost_ok and estimated_cost <= float(args.max_estimated_cost_per_minute)
            if args.max_provider_cost_per_minute > 0:
                cost_ok = cost_ok and provider_cost <= float(args.max_provider_cost_per_minute)

            checks.append(
                {
                    "name": "cost_window",
                    "ok": cost_ok,
                    "window": window,
                    "estimated_cost_usd_per_minute": estimated_cost,
                    "provider_reported_cost_usd_per_minute": provider_cost,
                }
            )

            if args.require_prometheus_families:
                # Prefer explicit CLI value, then process env, then local .env file.
                metrics_key_value, metrics_key_source = _resolve_metrics_key(args.metrics_key)
                metrics_response = _get_with_auth(
                    client,
                    f"{base_url}/v2/metrics/prometheus",
                    token=access_token,
                    metrics_key=metrics_key_value or None,
                    metrics_key_header=args.metrics_key_header,
                )
                required_families = [
                    "ls_backend_v2_model_latency_ms_p95",
                    "ls_backend_v2_estimated_cost_usd_per_minute",
                    "ls_backend_v2_errors_5xx_percent",
                    "ls_backend_v2_rate_limit_429_percent",
                ]
                if metrics_response.status_code != 200:
                    hint = (
                        "Set --metrics-key <value> or LS_METRICS_API_KEY when metrics endpoint runs in API-key mode."
                        if metrics_response.status_code == 401
                        else "Check /v2/metrics/prometheus availability and auth mode."
                    )
                    checks.append(
                        {
                            "name": "prometheus_families",
                            "ok": False,
                            "status_code": metrics_response.status_code,
                            "required": required_families,
                            "metrics_key_source": metrics_key_source,
                            "hint": hint,
                            "response_excerpt": (metrics_response.text or "")[:300],
                        }
                    )
                else:
                    metrics_text = metrics_response.text
                    missing = [family for family in required_families if family not in metrics_text]
                    checks.append(
                        {
                            "name": "prometheus_families",
                            "ok": len(missing) == 0,
                            "missing": missing,
                            "required": required_families,
                            "auth_mode": "metrics_key" if metrics_key_value else "bearer",
                            "metrics_key_source": metrics_key_source,
                        }
                    )

    except httpx.HTTPStatusError as exc:
        report["ok"] = False
        report["error"] = f"HTTP {exc.response.status_code}: {exc.response.text[:400]}"
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 1
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        print(json.dumps(report, ensure_ascii=True, indent=2))
        return 1

    all_ok = all(bool(check.get("ok")) for check in checks)
    report["ok"] = all_ok
    output_text = json.dumps(report, ensure_ascii=True, indent=2)
    print(output_text)

    output_path = (args.output or "").strip()
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output_text, encoding="utf-8")

    return 0 if all_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
