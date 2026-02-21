#!/usr/bin/env python
import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _post_json(url: str, payload: dict, timeout_seconds: float) -> dict:
    request = Request(
        url=url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _get_json(url: str, token: str, timeout_seconds: float) -> dict:
    request = Request(
        url=url,
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _read_float_env(key: str, default: float) -> float:
    raw = (os.getenv(key) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    default_window = (os.getenv("LS_OPS_SLO_OVERRIDE_WINDOW") or "60s").strip() or "60s"
    default_max_5xx = _read_float_env("LS_OPS_MAX_5XX_PERCENT", _read_float_env("LS_SLO_MAX_5XX_PERCENT", 1.0))
    default_max_429 = _read_float_env("LS_OPS_MAX_429_PERCENT", _read_float_env("LS_SLO_MAX_429_PERCENT", 5.0))

    parser = argparse.ArgumentParser(description="Smoke test for /v2/metrics/slo endpoint.")
    parser.add_argument("--base-url", default="http://localhost:8002", help="Base URL of backend_v2.")
    parser.add_argument("--user-id", type=int, default=1, help="User ID for login token.")
    parser.add_argument("--username", default="slo-smoke", help="Username for login token.")
    parser.add_argument(
        "--window",
        default=default_window,
        help="Window override for second SLO request. Env: LS_OPS_SLO_OVERRIDE_WINDOW.",
    )
    parser.add_argument(
        "--max-5xx",
        type=float,
        default=default_max_5xx,
        help="max_5xx_percent override. Env fallback: LS_OPS_MAX_5XX_PERCENT -> LS_SLO_MAX_5XX_PERCENT.",
    )
    parser.add_argument(
        "--max-429",
        type=float,
        default=default_max_429,
        help="max_429_percent override. Env fallback: LS_OPS_MAX_429_PERCENT -> LS_SLO_MAX_429_PERCENT.",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout seconds.")
    parser.add_argument(
        "--require-ok",
        action="store_true",
        help="Exit with code 2 if one of the SLO results is not status=ok.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()

    base = args.base_url.rstrip("/")
    login_url = f"{base}/v2/auth/login"
    slo_default_url = f"{base}/v2/metrics/slo"
    query = urlencode(
        {
            "window": args.window,
            "max_5xx_percent": args.max_5xx,
            "max_429_percent": args.max_429,
        }
    )
    slo_override_url = f"{base}/v2/metrics/slo?{query}"

    try:
        login_payload = {"user_id": args.user_id, "username": args.username}
        token_response = _post_json(login_url, login_payload, args.timeout)
        token = token_response["access_token"]

        slo_default = _get_json(slo_default_url, token, args.timeout)
        slo_override = _get_json(slo_override_url, token, args.timeout)
    except (HTTPError, URLError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: SLO smoke failed: {exc}", file=sys.stderr)
        return 1

    print("SLO default:")
    print(json.dumps(slo_default, ensure_ascii=True, indent=2))
    print()
    print("SLO override:")
    print(json.dumps(slo_override, ensure_ascii=True, indent=2))

    if args.require_ok and (slo_default.get("status") != "ok" or slo_override.get("status") != "ok"):
        print("ERROR: require-ok active and one SLO status is not 'ok'.", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
