from __future__ import annotations

import re

from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnIntentAction


_MOVE_PATTERNS = [
    re.compile(r"\b(?:gehe|geh|laufe|reise|betrete)\s+(?:zum|zur|nach|in den|in die|ins)\s+([a-zA-Z0-9äöüÄÖÜß _-]+)", re.I),
]
_USE_VERBS = ("benutze", "verwende", "nutze", "trinke", "iss", "aktiviere")
_ATTACK_VERBS = ("greife", "attackiere", "schlage", "haue", "steche")
_TALK_VERBS = ("spreche", "rede", "frage", "unterhalte")
_INSPECT_VERBS = ("untersuche", "umschauen", "umsehen", "betrachte", "inspiziere", "schaue", "suche")


def analyze_player_input_preview(
    *,
    world_id: str,
    world_character_id: str,
    player_input: str,
    inventory: list[InventoryItemInstance],
    known_npc_names: list[str] | None = None,
    known_locations: list[str] | None = None,
    known_npc_refs: list[dict[str, str]] | None = None,
    known_location_refs: list[dict[str, str]] | None = None,
) -> TurnIntent:
    text = (player_input or "").strip()
    lowered = text.lower()
    actions: list[TurnIntentAction] = []
    notes: list[str] = []

    npc_ref_index = _build_ref_index(known_npc_refs or [])
    location_ref_index = _build_ref_index(known_location_refs or [])

    destination = _extract_destination(text)
    if destination:
        canonical_destination = _canonicalize_name(destination, known_locations or [])
        resolved_location_id = _lookup_ref_id(canonical_destination, location_ref_index)
        actions.append(
            TurnIntentAction(
                action_type=ActionType.move,
                destination=canonical_destination,
                target_ref=resolved_location_id or None,
                target_kind="location",
                parameters={
                    "intent": "move",
                    "destination_name": canonical_destination,
                    "destination_id": resolved_location_id,
                },
                confidence=0.85,
            )
        )
        notes.append(f"Bewegungsziel erkannt: {canonical_destination}")

    if _contains_any_verb(lowered, _USE_VERBS):
        matched_item = _match_inventory_item(lowered, inventory)
        if matched_item is not None:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.use_item,
                    item_ref=matched_item.inventory_item_id,
                    target_ref=matched_item.name,
                    target_kind="item",
                    parameters={
                        "intent": "use_item",
                        "item_id": matched_item.inventory_item_id,
                        "item_name": matched_item.name,
                    },
                    confidence=0.9,
                )
            )
            notes.append(f"Benutzbares Inventarobjekt erkannt: {matched_item.name}")
        else:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.use_item,
                    target_ref="unbekanntes_item",
                    target_kind="item",
                    parameters={"intent": "use_item"},
                    confidence=0.45,
                )
            )
            notes.append("Item-Verwendung erkannt, aber kein Inventar-Match gefunden.")

    if _contains_any_verb(lowered, _ATTACK_VERBS):
        target = _extract_target_after_verb(text, _ATTACK_VERBS) or "gegner"
        target = _canonicalize_name(target, known_npc_names or [])
        target_id = _lookup_ref_id(target, npc_ref_index)
        actions.append(
            TurnIntentAction(
                action_type=ActionType.attack,
                target_ref=target_id or target,
                target_kind="npc_or_enemy",
                parameters={
                    "intent": "attack",
                    "target_name": target,
                    "target_id": target_id,
                },
                confidence=0.8,
            )
        )
        notes.append(f"Angriff erkannt: {target}")

    if _contains_any_verb(lowered, _TALK_VERBS):
        target = _extract_talk_target(text) or "npc"
        target = _canonicalize_name(target, known_npc_names or [])
        target_id = _lookup_ref_id(target, npc_ref_index)
        actions.append(
            TurnIntentAction(
                action_type=ActionType.talk,
                target_ref=target_id or target,
                target_kind="npc",
                parameters={
                    "intent": "talk",
                    "target_name": target,
                    "target_id": target_id,
                },
                confidence=0.75,
            )
        )
        notes.append(f"Gespraech erkannt: {target}")

    if not actions and _contains_any_verb(lowered, _INSPECT_VERBS):
        actions.append(
            TurnIntentAction(
                action_type=ActionType.inspect,
                target_kind="environment",
                parameters={"intent": "inspect"},
                confidence=0.7,
            )
        )
        notes.append("Untersuchungsaktion erkannt.")

    if not actions:
        actions.append(
            TurnIntentAction(
                action_type=ActionType.clarify,
                parameters={"intent": "clarify"},
                confidence=0.25,
            )
        )
        notes.append("Keine robuste Aktion erkannt, Rueckfrage empfohlen.")

    return TurnIntent(
        world_id=world_id,
        world_character_id=world_character_id,
        raw_player_input=text,
        actions=actions,
        analysis_notes=notes,
    )


def _extract_destination(text: str) -> str | None:
    for pattern in _MOVE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        destination = match.group(1).strip(" .,!?:;")
        destination = re.split(r"\b(?:und|dann|anschlie(?:ss|ß)end)\b", destination, maxsplit=1, flags=re.I)[0]
        destination = destination.strip(" .,!?:;")
        if destination:
            return destination
    return None


def _contains_any_verb(text_lower: str, verbs: tuple[str, ...]) -> bool:
    for verb in verbs:
        if re.search(rf"\b{re.escape(verb)}\b", text_lower, re.I):
            return True
    return False


def _match_inventory_item(text_lower: str, inventory: list[InventoryItemInstance]) -> InventoryItemInstance | None:
    for item in inventory:
        if item.name.lower() in text_lower:
            return item
    # fallback: token overlap
    for item in inventory:
        item_tokens = [token for token in re.split(r"\W+", item.name.lower()) if len(token) >= 4]
        if item_tokens and any(token in text_lower for token in item_tokens):
            return item
    return None


def _extract_target_after_verb(text: str, verbs: tuple[str, ...]) -> str | None:
    for verb in verbs:
        match = re.search(rf"\b{verb}\b\s+(?:den|die|das|einen|eine)?\s*([a-zA-Z0-9äöüÄÖÜß _-]+)", text, re.I)
        if match:
            target = _trim_entity_phrase(match.group(1))
            if target:
                return target
    return None


def _extract_talk_target(text: str) -> str | None:
    match = re.search(r"\b(?:mit|zu)\s+(?:dem|der|den|einem|einer)?\s*([a-zA-Z0-9äöüÄÖÜß _-]+)", text, re.I)
    if not match:
        return None
    target = _trim_entity_phrase(match.group(1))
    return target or None


def _trim_entity_phrase(value: str) -> str:
    target = value.strip(" .,!?:;")
    target = re.split(
        r"\b(?:und|ueber|über|wegen|beziehungsweise|danach|anschlie(?:ss|ß)end)\b",
        target,
        maxsplit=1,
        flags=re.I,
    )[0]
    return target.strip(" .,!?:;")


def _canonicalize_name(candidate: str, known_names: list[str]) -> str:
    normalized_candidate = candidate.strip()
    if not normalized_candidate or not known_names:
        return normalized_candidate
    lowered_candidate = normalized_candidate.lower()
    for known_name in known_names:
        if lowered_candidate == known_name.lower():
            return known_name
    for known_name in known_names:
        if lowered_candidate in known_name.lower() or known_name.lower() in lowered_candidate:
            return known_name
    return normalized_candidate


def _build_ref_index(entries: list[dict[str, str]]) -> dict[str, str]:
    index: dict[str, str] = {}
    for entry in entries:
        name = str(entry.get("name") or "").strip()
        ref_id = str(entry.get("ref_id") or "").strip()
        if not name or not ref_id:
            continue
        index[name.lower()] = ref_id
    return index


def _lookup_ref_id(name: str, ref_index: dict[str, str]) -> str | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    if normalized in ref_index:
        return ref_index[normalized]
    for known_name, ref_id in ref_index.items():
        if normalized in known_name or known_name in normalized:
            return ref_id
    return None
