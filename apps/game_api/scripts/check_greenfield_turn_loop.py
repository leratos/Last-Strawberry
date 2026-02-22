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


def _find_npc_bundle(npc_memory_payload: list[dict[str, Any]], npc_id: str) -> dict[str, Any] | None:
    for bundle in npc_memory_payload:
        profile = bundle.get("profile", {})
        if isinstance(profile, dict) and str(profile.get("npc_id")) == npc_id:
            return bundle
    return None


def _build_structured_attack_action(target_ref: dict[str, Any], attack_mode: str = "melee") -> dict[str, Any]:
    return {
        "action_type": "ATTACK",
        "target_ref": target_ref["ref_id"],
        "target_kind": "npc",
        "parameters": {
            "intent": "attack",
            "attack_mode": attack_mode,
            "target_id": target_ref["ref_id"],
            "target_name": target_ref["name"],
            "target_location_name": target_ref.get("location_name"),
            "target_zone_id": target_ref.get("scene_zone_id"),
            "target_zone_name": target_ref.get("scene_zone_name"),
            "target_distance_band": target_ref.get("distance_band_to_player"),
        },
    }


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

    talk_turn_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Spreche mit {npc_ref.get('name', 'NPC')}",
            "actions_override": [_build_structured_talk_action(npc_ref)],
        },
    )
    talk_codes = _extract_event_codes(talk_turn_run)
    if "talk_success" not in talk_codes:
        raise RuntimeError(f"Quickcheck erwartet talk_success, bekam: {talk_codes}")

    npc_memory_after_talk = _request_json(
        method="GET",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/npc-memory",
        timeout=timeout,
        payload=None,
    )
    talk_bundle = _find_npc_bundle(npc_memory_after_talk, str(npc_ref["ref_id"]))
    if not talk_bundle:
        raise RuntimeError("Quickcheck konnte NPC-Memory nach TALK nicht finden.")
    talk_standing = int((talk_bundle.get("relationship") or {}).get("standing") or 0)

    queue_turn_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck Queue: Rede mit {npc_ref.get('name', 'NPC')} und greife an",
            "actions_override": [
                _build_structured_talk_action(npc_ref),
                _build_structured_attack_action(npc_ref, attack_mode="melee"),
            ],
        },
    )
    queue_codes = _extract_event_codes(queue_turn_run)
    if "talk_success" not in queue_codes or "attack_resolved" not in queue_codes:
        raise RuntimeError(f"Quickcheck erwartet talk_success + attack_resolved, bekam: {queue_codes}")

    npc_memory_after_queue = _request_json(
        method="GET",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/npc-memory",
        timeout=timeout,
        payload=None,
    )
    queue_bundle = _find_npc_bundle(npc_memory_after_queue, str(npc_ref["ref_id"]))
    if not queue_bundle:
        raise RuntimeError("Quickcheck konnte NPC-Memory nach Queue-Turn nicht finden.")
    queue_standing = int((queue_bundle.get("relationship") or {}).get("standing") or 0)

    context_after_queue = queue_turn_run.get("context_after_turn") or {}
    queue_target_catalog = context_after_queue.get("target_catalog") or {}
    queue_npc_refs = queue_target_catalog.get("npcs") or []
    queue_target_ref = next((entry for entry in queue_npc_refs if entry.get("ref_id") == npc_ref["ref_id"]), None)
    distance_after_queue = (queue_target_ref or {}).get("distance_band_to_player")
    if distance_after_queue != "adjacent":
        raise RuntimeError(f"Quickcheck erwartet Distanz 'adjacent' nach Queue-Turn, bekam: {distance_after_queue!r}")

    result = {
        "world_id": world_id,
        "npc_id": npc_ref.get("ref_id"),
        "npc_name": npc_ref.get("name"),
        "talk_event_codes": talk_codes,
        "queue_event_codes": queue_codes,
        "had_auto_approach_talk": "auto_approach_for_talk" in talk_codes,
        "had_auto_move_location_talk": "auto_move_location_for_talk" in talk_codes,
        "had_auto_approach_attack_queue": "auto_approach_for_attack" in queue_codes,
        "standing_after_talk": talk_standing,
        "standing_after_queue": queue_standing,
        "distance_after_queue": distance_after_queue,
        "context_after_turn_present": bool(queue_turn_run.get("context_after_turn")),
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
