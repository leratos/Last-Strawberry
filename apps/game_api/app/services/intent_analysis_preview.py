from __future__ import annotations

import re
import unicodedata

from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnIntentAction


_MOVE_PATTERNS = [
    re.compile(r"\b(?:gehe|geh|laufe|reise|betrete)\s+(?:zum|zur|nach|in den|in die|ins)\s+([\w _-]+)", re.I),
    re.compile(r"\b(?:bewege(?:\s+mich)?|begib(?:\s+mich)?)\s+(?:zu|zum|zur)\s+([\w _-]+)", re.I),
]
_RETREAT_PATTERNS = [
    re.compile(r"\bentferne(?:\s+mich)?\s+von\s+([\w _-]+)", re.I),
    re.compile(r"\bgehe\s+weg\s+von\s+([\w _-]+)", re.I),
    re.compile(r"\bweiche\s+([\w _-]+)\s+aus\b", re.I),
    re.compile(r"\bhalte\s+abstand\s+zu\s+([\w _-]+)", re.I),
    re.compile(r"\bhalte(?:\s+mich)?\s+von\s+([\w _-]+)\s+fern\b", re.I),
]
_APPROACH_PATTERNS = [
    re.compile(r"\bn(?:ae|ä)her(?:e)?(?:\s+mich)?\s+(?:an\s+)?([\w _-]+)", re.I),
    re.compile(r"\bgehe\s+auf\s+([\w _-]+)\s+zu\b", re.I),
    re.compile(r"\bkomme\s+([\w _-]+)\s+n(?:a|ä)her\b", re.I),
    re.compile(r"\btrete(?:\s+einen)?(?:\s+schritt)?\s+n(?:a|ä)her\s+an\s+([\w _-]+)", re.I),
]
_USE_VERBS = ("benutze", "verwende", "nutze", "trinke", "iss", "aktiviere")
_ATTACK_VERBS = ("greife", "attackiere", "schlage", "haue", "steche")
_RANGED_ATTACK_VERBS = ("schiesse", "schieße", "zielen", "feuere", "werfe")
_TALK_VERBS = ("spreche", "rede", "frage", "unterhalte")
_INSPECT_VERBS = ("untersuche", "umschauen", "umsehen", "betrachte", "inspiziere", "schaue", "suche")
_RETREAT_VERBS = ("entferne", "zurueck", "zurück", "rueckzug", "weg", "abstand", "fern")
_APPROACH_VERBS = ("naehere", "nähere", "annaehern", "annähern", "naeher", "näher", "trete")


RefMetaIndex = dict[str, dict[str, str]]


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
    text = unicodedata.normalize("NFC", (player_input or "").strip())
    lowered = text.lower()
    actions: list[TurnIntentAction] = []
    notes: list[str] = []

    npc_ref_index = _build_ref_index(known_npc_refs or [])
    location_ref_index = _build_ref_index(known_location_refs or [])

    has_talk_verb = _contains_any_verb(lowered, _TALK_VERBS)
    destination = _extract_destination(text)
    if destination:
        canonical_destination = _canonicalize_name(destination, known_locations or [])
        location_meta = _lookup_ref_entry(canonical_destination, location_ref_index) or {}
        npc_meta = _lookup_ref_entry(_canonicalize_name(destination, known_npc_names or []), npc_ref_index) or {}
        looks_like_npc_approach = bool(
            has_talk_verb and not location_meta and str(npc_meta.get("ref_id") or "").strip()
        )
        if looks_like_npc_approach:
            notes.append("Bewegung zu NPC erkannt; Orts-MOVE uebersprungen (TALK Auto-Approach).")
        else:
            resolved_location_id = str(location_meta.get("ref_id") or "").strip() or None
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
                        "target_location_name": str(location_meta.get("location_name") or canonical_destination),
                        "target_zone_id": str(location_meta.get("scene_zone_id") or "") or None,
                        "target_zone_name": str(location_meta.get("scene_zone_name") or "") or None,
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

    has_melee_attack_verb = _contains_any_verb(lowered, _ATTACK_VERBS)
    has_ranged_attack_verb = _contains_any_verb(lowered, _RANGED_ATTACK_VERBS)
    if has_melee_attack_verb or has_ranged_attack_verb:
        attack_mode = "ranged" if has_ranged_attack_verb else "melee"
        target = _extract_target_after_verb(text, _ATTACK_VERBS + _RANGED_ATTACK_VERBS) or "gegner"
        target = _canonicalize_name(target, known_npc_names or [])
        target_meta = _lookup_ref_entry(target, npc_ref_index) or {}
        target_id = str(target_meta.get("ref_id") or "").strip() or None
        actions.append(
            TurnIntentAction(
                action_type=ActionType.attack,
                target_ref=target_id or target,
                target_kind="npc_or_enemy",
                parameters={
                    "intent": "attack",
                    "attack_mode": attack_mode,
                    "target_name": target,
                    "target_id": target_id,
                    "target_location_name": str(target_meta.get("location_name") or "") or None,
                    "target_zone_id": str(target_meta.get("scene_zone_id") or "") or None,
                    "target_zone_name": str(target_meta.get("scene_zone_name") or "") or None,
                    "target_distance_band": str(target_meta.get("distance_band_to_player") or "") or None,
                },
                confidence=0.8,
            )
        )
        notes.append(f"{'Fernkampf' if attack_mode == 'ranged' else 'Nahkampf'} erkannt: {target}")

    if has_talk_verb:
        target = _extract_talk_target(text) or "npc"
        target = _canonicalize_name(target, known_npc_names or [])
        target_meta = _lookup_ref_entry(target, npc_ref_index) or {}
        target_id = str(target_meta.get("ref_id") or "").strip() or None
        actions.append(
            TurnIntentAction(
                action_type=ActionType.talk,
                target_ref=target_id or target,
                target_kind="npc",
                parameters={
                    "intent": "talk",
                    "target_name": target,
                    "target_id": target_id,
                    "target_location_name": str(target_meta.get("location_name") or "") or None,
                    "target_zone_id": str(target_meta.get("scene_zone_id") or "") or None,
                    "target_zone_name": str(target_meta.get("scene_zone_name") or "") or None,
                    "target_distance_band": str(target_meta.get("distance_band_to_player") or "") or None,
                },
                confidence=0.75,
            )
        )
        notes.append(f"Gespraech erkannt: {target}")

    approach_target = _extract_approach_target(text)
    if approach_target or _contains_any_verb(lowered, _APPROACH_VERBS):
        canonical_approach_target = _canonicalize_name(approach_target or "", known_npc_names or [])
        approach_meta = _lookup_ref_entry(canonical_approach_target, npc_ref_index) if canonical_approach_target else None
        approach_id = str((approach_meta or {}).get("ref_id") or "").strip() or None
        actions.append(
            TurnIntentAction(
                action_type=ActionType.approach,
                target_ref=approach_id or (canonical_approach_target or None),
                target_kind="npc" if (approach_id or canonical_approach_target) else "environment",
                parameters={
                    "intent": "approach",
                    "target_name": canonical_approach_target or None,
                    "target_id": approach_id,
                    "target_location_name": str((approach_meta or {}).get("location_name") or "") or None,
                    "target_zone_id": str((approach_meta or {}).get("scene_zone_id") or "") or None,
                    "target_zone_name": str((approach_meta or {}).get("scene_zone_name") or "") or None,
                    "target_distance_band": str((approach_meta or {}).get("distance_band_to_player") or "") or None,
                },
                confidence=0.78 if approach_target else 0.55,
            )
        )
        if canonical_approach_target:
            notes.append(f"Annaehern erkannt: {canonical_approach_target}")
        else:
            notes.append("Annaehern erkannt.")

    retreat_target = _extract_retreat_target(text)
    if retreat_target or _contains_any_verb(lowered, _RETREAT_VERBS):
        canonical_retreat_target = _canonicalize_name(retreat_target or "", known_npc_names or [])
        retreat_meta = _lookup_ref_entry(canonical_retreat_target, npc_ref_index) if canonical_retreat_target else None
        retreat_id = str((retreat_meta or {}).get("ref_id") or "").strip() or None
        actions.append(
            TurnIntentAction(
                action_type=ActionType.retreat,
                target_ref=retreat_id or (canonical_retreat_target or None),
                target_kind="npc" if (retreat_id or canonical_retreat_target) else "environment",
                parameters={
                    "intent": "retreat",
                    "target_name": canonical_retreat_target or None,
                    "target_id": retreat_id,
                    "target_location_name": str((retreat_meta or {}).get("location_name") or "") or None,
                    "target_zone_id": str((retreat_meta or {}).get("scene_zone_id") or "") or None,
                    "target_zone_name": str((retreat_meta or {}).get("scene_zone_name") or "") or None,
                    "target_distance_band": str((retreat_meta or {}).get("distance_band_to_player") or "") or None,
                },
                confidence=0.78 if retreat_target else 0.55,
            )
        )
        if canonical_retreat_target:
            notes.append(f"Rueckzug/Abstand erkannt: {canonical_retreat_target}")
        else:
            notes.append("Rueckzug/Abstand erkannt.")

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


def _extract_retreat_target(text: str) -> str | None:
    for pattern in _RETREAT_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        target = _trim_entity_phrase(match.group(1))
        if target:
            return target
    return None


def _extract_approach_target(text: str) -> str | None:
    for pattern in _APPROACH_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        target = _trim_entity_phrase(match.group(1))
        if target:
            return target
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
    for item in inventory:
        item_tokens = [token for token in re.split(r"\W+", item.name.lower()) if len(token) >= 4]
        if item_tokens and any(token in text_lower for token in item_tokens):
            return item
    return None


def _extract_target_after_verb(text: str, verbs: tuple[str, ...]) -> str | None:
    for verb in verbs:
        match = re.search(rf"\b{verb}\b\s+(?:den|die|das|einen|eine)?\s*([\w _-]+)", text, re.I)
        if match:
            target = _trim_entity_phrase(match.group(1))
            if target:
                return target
    return None


def _extract_talk_target(text: str) -> str | None:
    match = re.search(r"\b(?:mit|zu)\s+(?:dem|der|den|einem|einer)?\s*([\w _-]+)", text, re.I)
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


def _build_ref_index(entries: list[dict[str, str]]) -> RefMetaIndex:
    index: RefMetaIndex = {}
    for entry in entries:
        name = str(entry.get("name") or "").strip()
        ref_id = str(entry.get("ref_id") or "").strip()
        if not name or not ref_id:
            continue
        index[name.lower()] = {str(k): str(v) for k, v in entry.items() if v is not None}
    return index


def _lookup_ref_entry(name: str, ref_index: RefMetaIndex) -> dict[str, str] | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    if normalized in ref_index:
        return ref_index[normalized]
    for known_name, ref_entry in ref_index.items():
        if normalized in known_name or known_name in normalized:
            return ref_entry
    return None
