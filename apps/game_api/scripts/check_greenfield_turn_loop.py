from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _build_structured_talk_action(target_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": "TALK",
        "target_ref": target_ref["ref_id"],
        "target_kind": "npc",
        "parameters": {
            "intent": "talk",
            "target_id": target_ref["ref_id"],
            "target_name": target_ref["name"],
            "target_location_name": target_ref.get("location_name"),
            "target_zone_id": target_ref.get("scene_zone_id"),
            "target_zone_name": target_ref.get("scene_zone_name"),
            "target_distance_band": target_ref.get("distance_band_to_player"),
        },
    }


def _extract_event_codes(turn_run_payload: dict[str, Any]) -> list[str]:
    events = turn_run_payload.get("turn", {}).get("resolution", {}).get("system_events", [])
    return [str(event.get("code")) for event in events if isinstance(event, dict)]


def _request_json(  # pragma: no cover - exercised manually against running local API
    *,
    method: str,
    url: str,
    payload: dict[str, Any] | None,
    timeout: float,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method=method.upper(),
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {raw}") from exc


def run_quickcheck(base_url: str, timeout: float = 15.0) -> dict[str, Any]:  # pragma: no cover - manual smoke tool
    base = base_url.rstrip("/")
    created = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/bootstrap",
        timeout=timeout,
        payload={
            "user_id": "quickcheck-local",
            "world_description": "Ein Marktviertel mit Heilerin, Haendlern und dichter Menschenmenge.",
            "character_description": "Ein aufmerksamer Abenteurer, der zuerst redet und dann handelt.",
        },
    )
    world_id = str(created["world_id"])

    context = _request_json(
        method="GET",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/context",
        timeout=timeout,
        payload=None,
    )
    npc_refs = list(context.get("target_catalog", {}).get("npcs", []))
    if not npc_refs:
        raise RuntimeError("Quickcheck konnte keinen NPC im target_catalog finden.")
    npc_ref = npc_refs[0]

    turn_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Spreche mit {npc_ref.get('name', 'NPC')}",
            "actions_override": [_build_structured_talk_action(npc_ref)],
        },
    )
    codes = _extract_event_codes(turn_run)
    if "talk_success" not in codes:
        raise RuntimeError(f"Quickcheck erwartet talk_success, bekam: {codes}")

    result = {
        "world_id": world_id,
        "npc_id": npc_ref.get("ref_id"),
        "npc_name": npc_ref.get("name"),
        "event_codes": codes,
        "had_auto_approach": "auto_approach_for_talk" in codes,
        "had_auto_move_location": "auto_move_location_for_talk" in codes,
        "context_after_turn_present": bool(turn_run.get("context_after_turn")),
    }
    return result


def main() -> int:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Greenfield turn-loop API quickcheck (local-first).")
    parser.add_argument("--base-url", default="http://127.0.0.1:8010", help="Game API base URL")
    parser.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    try:
        result = run_quickcheck(base_url=args.base_url, timeout=max(1.0, float(args.timeout)))
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL: {exc}")
        return 1

    print("PASS: greenfield turn-loop quickcheck succeeded")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI wrapper
    sys.exit(main())
