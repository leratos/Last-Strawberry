#!/usr/bin/env python
import argparse
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


def _http_request(
    *,
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 10.0,
) -> tuple[int, str]:
    data = None
    req_headers = dict(headers or {})
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    request = Request(url=url, data=data, headers=req_headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            return int(response.status), body
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), body
    except URLError as exc:
        return 0, str(exc)


def _json_or_none(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _check_backend_health(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    status, body = _http_request(url=f"{base_url}/v2/health", timeout_seconds=timeout_seconds)
    payload = _json_or_none(body)
    return {
        "name": "backend_health",
        "ok": status == 200 and isinstance(payload, dict) and payload.get("provider") == "openrouter",
        "status_code": status,
        "details": payload if isinstance(payload, dict) else body[:280],
    }


def _check_metrics_endpoint(
    *,
    base_url: str,
    timeout_seconds: float,
    user_id: int,
    username: str,
    metrics_key: str | None,
    metrics_key_header: str,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    mode = "bearer"

    if metrics_key:
        mode = "api_key"
        headers[metrics_key_header] = metrics_key
    else:
        login_status, login_body = _http_request(
            url=f"{base_url}/v2/auth/login",
            method="POST",
            json_body={"user_id": user_id, "username": username},
            timeout_seconds=timeout_seconds,
        )
        login_payload = _json_or_none(login_body)
        token = None
        if isinstance(login_payload, dict):
            token = login_payload.get("access_token")
        if login_status != 200 or not token:
            return {
                "name": "backend_metrics_export",
                "ok": False,
                "status_code": login_status,
                "mode": mode,
                "details": f"login failed: {login_body[:280]}",
            }
        headers["Authorization"] = f"Bearer {token}"

    status, body = _http_request(
        url=f"{base_url}/v2/metrics/prometheus",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    ok = status == 200 and "ls_backend_v2_http_requests_total" in body
    return {
        "name": "backend_metrics_export",
        "ok": ok,
        "status_code": status,
        "mode": mode,
        "details": body[:280] if not ok else "prometheus payload ok",
    }


def _check_prometheus_ready(prometheus_url: str, timeout_seconds: float) -> dict[str, Any]:
    status, body = _http_request(url=f"{prometheus_url}/-/ready", timeout_seconds=timeout_seconds)
    return {
        "name": "prometheus_ready",
        "ok": status == 200,
        "status_code": status,
        "details": body[:180],
    }


def _check_prometheus_targets(
    *, prometheus_url: str, timeout_seconds: float, expected_job: str
) -> dict[str, Any]:
    status, body = _http_request(
        url=f"{prometheus_url}/api/v1/targets?state=active",
        timeout_seconds=timeout_seconds,
    )
    payload = _json_or_none(body)
    if status != 200 or not isinstance(payload, dict):
        return {
            "name": "prometheus_targets",
            "ok": False,
            "status_code": status,
            "details": body[:280],
        }

    targets = payload.get("data", {}).get("activeTargets", [])
    if not isinstance(targets, list):
        targets = []

    job_targets = []
    for target in targets:
        labels = target.get("labels", {}) if isinstance(target, dict) else {}
        if isinstance(labels, dict) and labels.get("job") == expected_job:
            job_targets.append(target)

    up_count = 0
    for target in job_targets:
        if isinstance(target, dict) and str(target.get("health", "")).lower() == "up":
            up_count += 1

    return {
        "name": "prometheus_targets",
        "ok": up_count >= 1,
        "status_code": status,
        "details": {
            "expected_job": expected_job,
            "job_target_count": len(job_targets),
            "up_count": up_count,
        },
    }


def _check_prometheus_rules(prometheus_url: str, timeout_seconds: float) -> dict[str, Any]:
    required = {"last_strawberry_backend_v2_slo", "last_strawberry_backend_v2_operational"}
    status, body = _http_request(
        url=f"{prometheus_url}/api/v1/rules",
        timeout_seconds=timeout_seconds,
    )
    payload = _json_or_none(body)
    if status != 200 or not isinstance(payload, dict):
        return {
            "name": "prometheus_rules",
            "ok": False,
            "status_code": status,
            "details": body[:280],
        }

    groups = payload.get("data", {}).get("groups", [])
    found = set()
    if isinstance(groups, list):
        for group in groups:
            if isinstance(group, dict):
                name = group.get("name")
                if isinstance(name, str):
                    found.add(name)

    missing = sorted(required - found)
    return {
        "name": "prometheus_rules",
        "ok": not missing,
        "status_code": status,
        "details": {"missing_groups": missing},
    }


def _check_prometheus_query(
    *, prometheus_url: str, timeout_seconds: float, expected_job: str
) -> dict[str, Any]:
    promql = quote_plus(f'ls_backend_v2_http_requests_total{{job="{expected_job}"}}')
    status, body = _http_request(
        url=f"{prometheus_url}/api/v1/query?query={promql}",
        timeout_seconds=timeout_seconds,
    )
    payload = _json_or_none(body)
    if status != 200 or not isinstance(payload, dict):
        return {
            "name": "prometheus_query",
            "ok": False,
            "status_code": status,
            "details": body[:280],
        }

    result = payload.get("data", {}).get("result", [])
    count = len(result) if isinstance(result, list) else 0
    return {
        "name": "prometheus_query",
        "ok": count >= 1,
        "status_code": status,
        "details": {"series_count": count},
    }


def _check_grafana_dashboard(
    *, grafana_url: str, timeout_seconds: float, dashboard_uid: str, api_token: str
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_token}"}
    status, body = _http_request(
        url=f"{grafana_url}/api/dashboards/uid/{dashboard_uid}",
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    payload = _json_or_none(body)
    ok = status == 200 and isinstance(payload, dict) and isinstance(payload.get("dashboard"), dict)
    return {
        "name": "grafana_dashboard",
        "ok": ok,
        "status_code": status,
        "details": payload if isinstance(payload, dict) else body[:280],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="End-to-end monitoring stack smoke check (backend+prometheus+grafana).")
    parser.add_argument("--backend-url", default="http://localhost:8002")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--expected-job", default="last_strawberry_backend_v2")
    parser.add_argument("--metrics-key", default=None)
    parser.add_argument("--metrics-key-header", default="X-Metrics-Key")
    parser.add_argument("--user-id", type=int, default=901)
    parser.add_argument("--username", default="stack-smoke")
    parser.add_argument("--grafana-url", default=None, help="Optional, e.g. http://localhost:3000")
    parser.add_argument("--grafana-api-token", default=None, help="Required for Grafana dashboard API check.")
    parser.add_argument("--grafana-dashboard-uid", default="ls-backend-v2-slo-ops")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backend_url = args.backend_url.rstrip("/")
    prometheus_url = args.prometheus_url.rstrip("/")

    checks: list[dict[str, Any]] = [
        _check_backend_health(backend_url, args.timeout_seconds),
        _check_metrics_endpoint(
            base_url=backend_url,
            timeout_seconds=args.timeout_seconds,
            user_id=args.user_id,
            username=args.username,
            metrics_key=args.metrics_key,
            metrics_key_header=args.metrics_key_header,
        ),
        _check_prometheus_ready(prometheus_url, args.timeout_seconds),
        _check_prometheus_targets(
            prometheus_url=prometheus_url,
            timeout_seconds=args.timeout_seconds,
            expected_job=args.expected_job,
        ),
        _check_prometheus_rules(prometheus_url, args.timeout_seconds),
        _check_prometheus_query(
            prometheus_url=prometheus_url,
            timeout_seconds=args.timeout_seconds,
            expected_job=args.expected_job,
        ),
    ]

    if args.grafana_url and args.grafana_api_token:
        checks.append(
            _check_grafana_dashboard(
                grafana_url=args.grafana_url.rstrip("/"),
                timeout_seconds=args.timeout_seconds,
                dashboard_uid=args.grafana_dashboard_uid,
                api_token=args.grafana_api_token,
            )
        )

    failed = [item for item in checks if not item.get("ok")]
    summary = {
        "ok": not failed,
        "check_count": len(checks),
        "failed_count": len(failed),
        "checks": checks,
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
