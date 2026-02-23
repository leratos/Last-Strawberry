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


def _build_structured_retreat_action(target_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": "RETREAT",
        "target_ref": target_ref["ref_id"],
        "target_kind": "npc",
        "parameters": {
            "intent": "retreat",
            "target_id": target_ref["ref_id"],
            "target_name": target_ref["name"],
            "target_location_name": target_ref.get("location_name"),
            "target_zone_id": target_ref.get("scene_zone_id"),
            "target_zone_name": target_ref.get("scene_zone_name"),
            "target_distance_band": target_ref.get("distance_band_to_player"),
        },
    }


def _build_structured_approach_action(target_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "action_type": "APPROACH",
        "target_ref": target_ref["ref_id"],
        "target_kind": "npc",
        "parameters": {
            "intent": "approach",
            "target_id": target_ref["ref_id"],
            "target_name": target_ref["name"],
            "target_location_name": target_ref.get("location_name"),
            "target_zone_id": target_ref.get("scene_zone_id"),
            "target_zone_name": target_ref.get("scene_zone_name"),
            "target_distance_band": target_ref.get("distance_band_to_player"),
        },
    }


def _build_structured_scene_action(target_ref: dict[str, Any], action_type: str) -> dict[str, Any]:
    action_type_upper = action_type.upper()
    intent = action_type_upper.lower()
    return {
        "action_type": action_type_upper,
        "target_ref": target_ref["ref_id"],
        "target_kind": target_ref.get("kind") or "scene_point",
        "parameters": {
            "intent": intent,
            "target_id": target_ref["ref_id"],
            "target_name": target_ref["name"],
            "target_kind": target_ref.get("kind") or "scene_point",
            "target_location_name": target_ref.get("location_name"),
            "target_zone_id": target_ref.get("scene_zone_id"),
            "target_zone_name": target_ref.get("scene_zone_name"),
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
    hidden_npc_count_before = int(context.get("hidden_npc_count") or 0)
    hidden_scene_points_before = int(context.get("hidden_scene_point_count") or 0)
    npc_refs = list(context.get("target_catalog", {}).get("npcs", []))
    if not npc_refs:
        raise RuntimeError("Quickcheck konnte keinen NPC im target_catalog finden.")
    npc_ref = npc_refs[0]

    discover_turn_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={"player_input": "Ich schau mich um."},
    )
    discover_codes = _extract_event_codes(discover_turn_run)
    if "discovery_revealed_scene_points" not in discover_codes:
        raise RuntimeError(f"Quickcheck erwartet discovery_revealed_scene_points, bekam: {discover_codes}")
    discovered_context = discover_turn_run.get("context_after_turn") or {}
    discovered_scene_points = (discovered_context.get("target_catalog") or {}).get("scene_points") or []
    if not discovered_scene_points:
        raise RuntimeError("Quickcheck erwartete sichtbare Interaktionspunkte nach INSPECT.")
    container_ref = next((entry for entry in discovered_scene_points if entry.get("kind") == "container"), None)
    scene_object_ref = next((entry for entry in discovered_scene_points if entry.get("kind") == "scene_object"), None)
    if container_ref is None or scene_object_ref is None:
        raise RuntimeError("Quickcheck erwartet mindestens einen container und ein scene_object nach INSPECT.")
    if int(discovered_context.get("hidden_scene_point_count") or 0) != 0:
        raise RuntimeError("Quickcheck erwartet hidden_scene_point_count=0 nach erstem broad INSPECT.")

    discover_turn_run_repeat = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={"player_input": "Ich schau mich um."},
    )
    discover_repeat_codes = _extract_event_codes(discover_turn_run_repeat)
    if "inspect_broad_success" not in discover_repeat_codes:
        raise RuntimeError(f"Quickcheck erwartet inspect_broad_success beim Wiederholen, bekam: {discover_repeat_codes}")
    if "discovery_nothing_new" not in discover_repeat_codes:
        raise RuntimeError(f"Quickcheck erwartet discovery_nothing_new beim Wiederholen, bekam: {discover_repeat_codes}")

    open_container_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Oeffne {container_ref.get('name', 'Container')}",
            "actions_override": [_build_structured_scene_action(container_ref, "OPEN")],
        },
    )
    open_container_codes = _extract_event_codes(open_container_run)
    if "container_opened" not in open_container_codes:
        raise RuntimeError(f"Quickcheck erwartet container_opened, bekam: {open_container_codes}")

    search_container_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Durchsuche {container_ref.get('name', 'Container')}",
            "actions_override": [_build_structured_scene_action(container_ref, "SEARCH")],
        },
    )
    search_container_codes = _extract_event_codes(search_container_run)
    if "search_focus_success" not in search_container_codes:
        raise RuntimeError(f"Quickcheck erwartet search_focus_success, bekam: {search_container_codes}")
    if not any(code in search_container_codes for code in ("container_loot_found", "container_empty", "container_already_searched")):
        raise RuntimeError(f"Quickcheck erwartet Container-Search-Ergebnis, bekam: {search_container_codes}")

    take_scene_object_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Nimm {scene_object_ref.get('name', 'Objekt')}",
            "actions_override": [_build_structured_scene_action(scene_object_ref, "TAKE")],
        },
    )
    take_scene_object_codes = _extract_event_codes(take_scene_object_run)
    if "scene_object_taken" not in take_scene_object_codes:
        raise RuntimeError(f"Quickcheck erwartet scene_object_taken, bekam: {take_scene_object_codes}")
    scene_object_context = take_scene_object_run.get("context_after_turn") or {}
    scene_object_entries = (scene_object_context.get("target_catalog") or {}).get("scene_points") or []
    scene_object_after = next((entry for entry in scene_object_entries if entry.get("ref_id") == scene_object_ref.get("ref_id")), None)
    if not scene_object_after or not bool((scene_object_after.get("discovery_state") or {}).get("taken")):
        raise RuntimeError("Quickcheck erwartet discovery_state.taken=true nach TAKE.")

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

    retreat_turn_run = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Gewinne Abstand zu {npc_ref.get('name', 'NPC')}",
            "actions_override": [_build_structured_retreat_action(queue_target_ref or npc_ref)],
        },
    )
    retreat_codes = _extract_event_codes(retreat_turn_run)
    if "retreat_success" not in retreat_codes:
        raise RuntimeError(f"Quickcheck erwartet retreat_success, bekam: {retreat_codes}")
    retreat_context = retreat_turn_run.get("context_after_turn") or {}
    retreat_npcs = (retreat_context.get("target_catalog") or {}).get("npcs") or []
    retreat_target_ref = next((entry for entry in retreat_npcs if entry.get("ref_id") == npc_ref["ref_id"]), None)
    distance_after_retreat = (retreat_target_ref or {}).get("distance_band_to_player")
    if distance_after_retreat != "near":
        raise RuntimeError(f"Quickcheck erwartet Distanz 'near' nach RETREAT, bekam: {distance_after_retreat!r}")

    retreat_turn_run_2 = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Mehr Abstand zu {npc_ref.get('name', 'NPC')}",
            "actions_override": [_build_structured_retreat_action(retreat_target_ref or npc_ref)],
        },
    )
    retreat_codes_2 = _extract_event_codes(retreat_turn_run_2)
    if "retreat_success" not in retreat_codes_2:
        raise RuntimeError(f"Quickcheck erwartet retreat_success im zweiten RETREAT, bekam: {retreat_codes_2}")
    retreat_context_2 = retreat_turn_run_2.get("context_after_turn") or {}
    retreat_npcs_2 = (retreat_context_2.get("target_catalog") or {}).get("npcs") or []
    retreat_target_ref_2 = next((entry for entry in retreat_npcs_2 if entry.get("ref_id") == npc_ref["ref_id"]), None)
    distance_after_retreat_2 = (retreat_target_ref_2 or {}).get("distance_band_to_player")
    if distance_after_retreat_2 != "far":
        raise RuntimeError(
            f"Quickcheck erwartet Distanz 'far' nach zweitem RETREAT, bekam: {distance_after_retreat_2!r}"
        )

    approach_turn_run_1 = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Naehere dich {npc_ref.get('name', 'NPC')}",
            "actions_override": [_build_structured_approach_action(retreat_target_ref_2 or npc_ref)],
        },
    )
    approach_codes_1 = _extract_event_codes(approach_turn_run_1)
    if "approach_success" not in approach_codes_1:
        raise RuntimeError(f"Quickcheck erwartet approach_success im ersten APPROACH, bekam: {approach_codes_1}")
    approach_ctx_1 = approach_turn_run_1.get("context_after_turn") or {}
    approach_npcs_1 = (approach_ctx_1.get("target_catalog") or {}).get("npcs") or []
    approach_target_ref_1 = next((entry for entry in approach_npcs_1 if entry.get("ref_id") == npc_ref["ref_id"]), None)
    distance_after_approach_1 = (approach_target_ref_1 or {}).get("distance_band_to_player")
    if distance_after_approach_1 != "near":
        raise RuntimeError(
            f"Quickcheck erwartet Distanz 'near' nach erstem APPROACH, bekam: {distance_after_approach_1!r}"
        )

    approach_turn_run_2 = _request_json(
        method="POST",
        url=f"{base}/v1/worlds/{urllib.parse.quote(world_id)}/turns/run",
        timeout=timeout,
        payload={
            "player_input": f"UI Quickcheck: Gehe noch naeher zu {npc_ref.get('name', 'NPC')}",
            "actions_override": [_build_structured_approach_action(approach_target_ref_1 or npc_ref)],
        },
    )
    approach_codes_2 = _extract_event_codes(approach_turn_run_2)
    if "approach_success" not in approach_codes_2:
        raise RuntimeError(f"Quickcheck erwartet approach_success im zweiten APPROACH, bekam: {approach_codes_2}")
    approach_ctx_2 = approach_turn_run_2.get("context_after_turn") or {}
    approach_npcs_2 = (approach_ctx_2.get("target_catalog") or {}).get("npcs") or []
    approach_target_ref_2 = next((entry for entry in approach_npcs_2 if entry.get("ref_id") == npc_ref["ref_id"]), None)
    distance_after_approach_2 = (approach_target_ref_2 or {}).get("distance_band_to_player")
    if distance_after_approach_2 != "adjacent":
        raise RuntimeError(
            f"Quickcheck erwartet Distanz 'adjacent' nach zweitem APPROACH, bekam: {distance_after_approach_2!r}"
        )

    result = {
        "world_id": world_id,
        "npc_id": npc_ref.get("ref_id"),
        "npc_name": npc_ref.get("name"),
        "discover_event_codes": discover_codes,
        "discover_repeat_event_codes": discover_repeat_codes,
        "discovered_scene_points_count": len(discovered_scene_points),
        "hidden_npc_count_before_discovery": hidden_npc_count_before,
        "hidden_scene_point_count_before_discovery": hidden_scene_points_before,
        "open_container_event_codes": open_container_codes,
        "search_container_event_codes": search_container_codes,
        "take_scene_object_event_codes": take_scene_object_codes,
        "talk_event_codes": talk_codes,
        "queue_event_codes": queue_codes,
        "had_auto_approach_talk": "auto_approach_for_talk" in talk_codes,
        "had_auto_move_location_talk": "auto_move_location_for_talk" in talk_codes,
        "had_auto_approach_attack_queue": "auto_approach_for_attack" in queue_codes,
        "standing_after_talk": talk_standing,
        "standing_after_queue": queue_standing,
        "distance_after_queue": distance_after_queue,
        "retreat_event_codes": retreat_codes,
        "distance_after_retreat": distance_after_retreat,
        "retreat_event_codes_second": retreat_codes_2,
        "distance_after_retreat_second": distance_after_retreat_2,
        "approach_event_codes_first": approach_codes_1,
        "distance_after_approach_first": distance_after_approach_1,
        "approach_event_codes_second": approach_codes_2,
        "distance_after_approach_second": distance_after_approach_2,
        "context_after_turn_present": bool(approach_turn_run_2.get("context_after_turn")),
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
