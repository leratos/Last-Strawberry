#!/usr/bin/env python
import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for /v2/metrics/slo endpoint.")
    parser.add_argument("--base-url", default="http://localhost:8002", help="Base URL of backend_v2.")
    parser.add_argument("--user-id", type=int, default=1, help="User ID for login token.")
    parser.add_argument("--username", default="slo-smoke", help="Username for login token.")
    parser.add_argument("--window", default="60s", help="Window override for second SLO request.")
    parser.add_argument("--max-5xx", type=float, default=1.0, help="max_5xx_percent override.")
    parser.add_argument("--max-429", type=float, default=5.0, help="max_429_percent override.")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout seconds.")
    parser.add_argument(
        "--require-ok",
        action="store_true",
        help="Exit with code 2 if one of the SLO results is not status=ok.",
    )
    args = parser.parse_args()

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
