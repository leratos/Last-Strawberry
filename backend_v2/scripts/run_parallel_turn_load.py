import argparse
import asyncio
import json
import statistics
import time
from collections import Counter

import httpx


async def _login(client: httpx.AsyncClient, *, user_id: int, username: str) -> str:
    response = await client.post(
        "/v2/auth/login",
        json={"user_id": user_id, "username": username},
    )
    response.raise_for_status()
    return response.json()["access_token"]


async def _create_world(client: httpx.AsyncClient, *, token: str, name: str) -> int:
    response = await client.post(
        "/v2/worlds",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": name, "description": "parallel-load-test"},
    )
    response.raise_for_status()
    return int(response.json()["id"])


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    idx = max(0, min(len(values) - 1, int(round((len(values) - 1) * ratio))))
    return sorted(values)[idx]


async def run_load(args: argparse.Namespace) -> int:
    timeout = httpx.Timeout(args.timeout_seconds)
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=timeout) as client:
        token = await _login(client, user_id=args.user_id, username=args.username)
        world_id = await _create_world(client, token=token, name=args.world_name)
        auth_header = {"Authorization": f"Bearer {token}"}

        semaphore = asyncio.Semaphore(args.concurrency)
        status_counts: Counter[int] = Counter()
        latencies_ms: list[float] = []
        failed_bodies: list[str] = []

        async def _send_turn(i: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                response = await client.post(
                    "/v2/game/turn",
                    headers=auth_header,
                    json={
                        "world_id": world_id,
                        "player_id": args.player_id,
                        "player_command": f"{args.command_prefix} #{i}",
                    },
                )
                latency_ms = (time.perf_counter() - started) * 1000
                latencies_ms.append(latency_ms)
                status_counts[response.status_code] += 1
                if response.status_code >= 400 and len(failed_bodies) < 5:
                    failed_bodies.append(response.text[:200])

        await asyncio.gather(*[_send_turn(i) for i in range(args.requests)])

        summary = {
            "base_url": args.base_url,
            "requests": args.requests,
            "concurrency": args.concurrency,
            "status_counts": dict(status_counts),
            "latency_ms": {
                "mean": round(statistics.fmean(latencies_ms), 2) if latencies_ms else 0.0,
                "p50": round(_percentile(latencies_ms, 0.50), 2),
                "p95": round(_percentile(latencies_ms, 0.95), 2),
                "max": round(max(latencies_ms), 2) if latencies_ms else 0.0,
            },
            "sample_failures": failed_bodies,
        }
        print(json.dumps(summary, ensure_ascii=True, indent=2))

        fail_5xx = sum(count for status, count in status_counts.items() if status >= 500)
        if fail_5xx > 0:
            return 2
        if args.fail_on_429 and status_counts.get(429, 0) > 0:
            return 3
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run parallel /v2/game/turn load burst against backend_v2.")
    parser.add_argument("--base-url", default="http://localhost:8002", help="Backend base URL.")
    parser.add_argument("--user-id", type=int, default=991, help="User ID for auth/login.")
    parser.add_argument("--username", default="loadtester", help="Username for auth/login.")
    parser.add_argument("--world-name", default="Load Test World", help="Temporary world name.")
    parser.add_argument("--player-id", type=int, default=77, help="Player ID used in turn payloads.")
    parser.add_argument("--requests", type=int, default=40, help="Total number of turn requests.")
    parser.add_argument("--concurrency", type=int, default=10, help="Parallel request workers.")
    parser.add_argument("--command-prefix", default="Ich pruefe die Last", help="Player command prefix.")
    parser.add_argument("--timeout-seconds", type=float, default=30.0, help="HTTP timeout in seconds.")
    parser.add_argument("--fail-on-429", action="store_true", help="Return non-zero exit code if any 429 occurs.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(run_load(args))


if __name__ == "__main__":
    raise SystemExit(main())
