#!/usr/bin/env python
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx


REPO_ROOT = Path(__file__).resolve().parents[2]


def _tail(text: str, max_lines: int = 40) -> str:
    lines = (text or "").splitlines()
    if len(lines) <= max_lines:
        return "\n".join(lines)
    return "\n".join(lines[-max_lines:])


def _run_step(name: str, command: list[str]) -> dict:
    started_at = time.perf_counter()
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    return {
        "name": name,
        "ok": result.returncode == 0,
        "exit_code": result.returncode,
        "duration_ms": duration_ms,
        "stdout_tail": _tail(result.stdout),
        "stderr_tail": _tail(result.stderr),
        "command": command,
    }


def _check_json_health(name: str, url: str, timeout_seconds: float) -> dict:
    started_at = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url)
        payload = response.json() if response.text else {}
    except Exception as exc:
        return {
            "name": name,
            "ok": False,
            "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
            "error": str(exc),
            "url": url,
        }

    return {
        "name": name,
        "ok": response.status_code == 200,
        "duration_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
        "status_code": response.status_code,
        "payload": payload,
        "url": url,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 4 closeout smoke: backend_v2 + backend_server bridge + quickcheck + SLO."
    )
    parser.add_argument("--backend-base-url", default="http://127.0.0.1:8001", help="backend_server base URL")
    parser.add_argument("--v2-base-url", default="http://127.0.0.1:8002", help="backend_v2 base URL")
    parser.add_argument("--username", required=True, help="Legacy backend username")
    parser.add_argument("--password", required=True, help="Legacy backend password")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    parser.add_argument(
        "--skip-playtest",
        action="store_true",
        help="Skip playtest_bridge_quickcheck step.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backend_base = args.backend_base_url.rstrip("/")
    v2_base = args.v2_base_url.rstrip("/")

    report: dict[str, object] = {
        "timestamp_unix": int(time.time()),
        "inputs": {
            "backend_base_url": backend_base,
            "v2_base_url": v2_base,
            "skip_playtest": args.skip_playtest,
        },
        "checks": [],
    }
    checks = report["checks"]

    v2_health = _check_json_health("backend_v2_health", f"{v2_base}/v2/health", args.timeout)
    checks.append(v2_health)

    backend_health = _check_json_health("backend_server_health", f"{backend_base}/health", args.timeout)
    bridge_payload = backend_health.get("payload", {}) if isinstance(backend_health.get("payload"), dict) else {}
    bridge_status = bridge_payload.get("v2_bridge_status") if isinstance(bridge_payload, dict) else {}
    if backend_health.get("ok") and isinstance(bridge_status, dict):
        backend_health["bridge_enabled"] = bool(bridge_status.get("enabled"))
        backend_health["bridge_status"] = str(bridge_status.get("status") or "")
        backend_health["ok"] = backend_health["ok"] and backend_health["bridge_enabled"] and (
            backend_health["bridge_status"] == "ok"
        )
    checks.append(backend_health)

    checks.append(
        _run_step(
            "smoke_v2_bridge",
            [
                sys.executable,
                str(REPO_ROOT / "backend_server" / "scripts" / "smoke_v2_bridge.py"),
                "--base-url",
                backend_base,
                "--username",
                args.username,
                "--password",
                args.password,
                "--world-name",
                "Phase4 Release Smoke World",
                "--command",
                "Ich pruefe den Release-Flow.",
            ],
        )
    )

    if not args.skip_playtest:
        checks.append(
            _run_step(
                "playtest_bridge_quickcheck",
                [
                    sys.executable,
                    str(REPO_ROOT / "backend_server" / "scripts" / "playtest_bridge_quickcheck.py"),
                    "--base-url",
                    backend_base,
                    "--username",
                    args.username,
                    "--password",
                    args.password,
                    "--world-name",
                    "Phase4 Release Playtest World",
                    "--commands",
                    "Ich schaue mich um.|Ich spreche mit einem Haendler.|Ich gehe zum Rathaus.",
                ],
            )
        )

    checks.append(
        _run_step(
            "smoke_slo",
            [
                sys.executable,
                str(REPO_ROOT / "backend_v2" / "scripts" / "smoke_slo.py"),
                "--base-url",
                v2_base,
                "--require-ok",
                "--timeout",
                str(args.timeout),
            ],
        )
    )

    all_ok = all(bool(check.get("ok")) for check in checks if isinstance(check, dict))
    report["ok"] = all_ok
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
