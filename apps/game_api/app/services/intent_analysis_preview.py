from __future__ import annotations

import json
import re
import unicodedata

from ls_shared_schemas.inventory import InventoryItemInstance
from ls_shared_schemas.turns import ActionType, TurnIntent, TurnIntentAction

from apps.game_api.app.services.urban_occult_basis import resolve_unique_role_title_npc_reference

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
_OPEN_VERBS = ("oeffne", "öffne", "mache auf", "klappe auf")
_SEARCH_VERBS = ("durchsuche", "durchforste", "wuehle", "wühle")
_TAKE_VERBS = ("nimm", "nehme", "hebe", "packe", "pack", "stecke")
_ATTACK_VERBS = ("greife", "attackiere", "schlage", "haue", "steche")
_RANGED_ATTACK_VERBS = ("schiesse", "schieße", "zielen", "feuere", "werfe")
_TALK_VERBS = ("spreche", "rede", "frage", "unterhalte")
_INSPECT_VERBS = ("untersuche", "umschauen", "umsehen", "betrachte", "inspiziere", "schaue", "schau", "suche")
_RETREAT_VERBS = ("entferne", "zurueck", "zurück", "rueckzug", "weg", "abstand", "fern")
_APPROACH_VERBS = ("naehere", "nähere", "annaehern", "annähern", "naeher", "näher", "trete")
_GENERIC_NPC_TARGET_WORDS = {
    "npc",
    "char",
    "charakter",
    "figur",
    "person",
    "mann",
    "frau",
    "gegner",
    "ziel",
}
_DESCRIPTIVE_NPC_REFERENCE_HINTS = (
    "zweite",
    "zweiten",
    "zweiter",
    "dritte",
    "dritten",
    "ander",
    "kollege",
    "kollegin",
    "freund",
    "begleiter",
    "typ",
    "person",
    "von ",
)


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
    known_scene_point_refs: list[dict[str, str]] | None = None,
) -> TurnIntent:
    text = unicodedata.normalize("NFC", (player_input or "").strip())
    lowered = text.lower()
    actions: list[TurnIntentAction] = []
    notes: list[str] = []

    npc_ref_index = _build_ref_index(known_npc_refs or [])
    location_ref_index = _build_ref_index(known_location_refs or [])
    scene_point_ref_index = _build_ref_index(known_scene_point_refs or [])

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
        target, target_meta, clarify_message = _resolve_npc_target_reference(
            target,
            known_npc_names or [],
            known_npc_refs or [],
            npc_ref_index,
        )
        if clarify_message:
            actions.append(
                _clarify_action_for_npc_target(
                    message=clarify_message,
                    reason="ambiguous_npc_target",
                    candidate_entries=_npc_clarify_candidates_from_role_title(target, known_npc_refs or []),
                    suggested_action="select_visible_npc",
                )
            )
            notes.append(clarify_message)
            target_meta = {}
            target = ""
        target_id = str(target_meta.get("ref_id") or "").strip() or None
        if not clarify_message:
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
                        "target_role": str(target_meta.get("role") or "") or None,
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
        target_was_known_name = bool(
            target and any(target.strip().lower() == known_name.lower() for known_name in (known_npc_names or []))
        )
        target, target_meta, clarify_message = _resolve_npc_target_reference(
            target,
            known_npc_names or [],
            known_npc_refs or [],
            npc_ref_index,
        )
        if not clarify_message and not target_was_known_name and _requires_existing_npc_resolution(target=target, target_meta=target_meta):
            clarify_message = (
                "Die angesprochene Person ist nicht bekannt oder nicht sichtbar. "
                "Bitte nenne einen bekannten Namen, waehle ein Ziel aus der Liste oder schau dich zuerst um."
            )
        if not clarify_message and _looks_like_descriptive_unresolved_npc_reference(target=target, target_meta=target_meta):
            clarify_message = (
                "Die beschriebene Person ist nicht eindeutig zuordenbar. "
                "Bitte waehle einen sichtbaren NPC aus der Liste oder nenne einen bekannten Namen."
            )
        if clarify_message:
            role_title_candidates = _npc_clarify_candidates_from_role_title(target or "", known_npc_refs or [])
            clarify_reason = "ambiguous_npc_role_title" if role_title_candidates else "unknown_or_ambiguous_npc_talk_target"
            clarify_suggested_action = "select_visible_npc" if role_title_candidates else "inspect_broad"
            actions.append(
                _clarify_action_for_npc_target(
                    message=clarify_message,
                    reason=clarify_reason,
                    candidate_entries=role_title_candidates or _npc_visible_candidates(known_npc_refs or []),
                    suggested_action=clarify_suggested_action,
                )
            )
            notes.append(clarify_message)
            target_meta = {}
            target = ""
        target_id = str(target_meta.get("ref_id") or "").strip() or None
        if not clarify_message:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.talk,
                    target_ref=target_id or target,
                    target_kind="npc",
                    parameters={
                        "intent": "talk",
                        "target_name": target,
                        "target_id": target_id,
                        "target_role": str(target_meta.get("role") or "") or None,
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
        canonical_approach_target, approach_meta, clarify_message = _resolve_npc_target_reference(
            approach_target or "",
            known_npc_names or [],
            known_npc_refs or [],
            npc_ref_index,
        )
        if clarify_message:
            actions.append(
                _clarify_action_for_npc_target(
                    message=clarify_message,
                    reason="ambiguous_npc_target",
                    candidate_entries=_npc_clarify_candidates_from_role_title(approach_target or "", known_npc_refs or []),
                    suggested_action="select_visible_npc",
                )
            )
            notes.append(clarify_message)
            approach_meta = {}
            canonical_approach_target = ""
        approach_id = str((approach_meta or {}).get("ref_id") or "").strip() or None
        if not clarify_message:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.approach,
                    target_ref=approach_id or (canonical_approach_target or None),
                    target_kind="npc" if (approach_id or canonical_approach_target) else "environment",
                    parameters={
                        "intent": "approach",
                        "target_name": canonical_approach_target or None,
                        "target_id": approach_id,
                        "target_role": str((approach_meta or {}).get("role") or "") or None,
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
        canonical_retreat_target, retreat_meta, clarify_message = _resolve_npc_target_reference(
            retreat_target or "",
            known_npc_names or [],
            known_npc_refs or [],
            npc_ref_index,
        )
        if clarify_message:
            actions.append(
                _clarify_action_for_npc_target(
                    message=clarify_message,
                    reason="ambiguous_npc_target",
                    candidate_entries=_npc_clarify_candidates_from_role_title(retreat_target or "", known_npc_refs or []),
                    suggested_action="select_visible_npc",
                )
            )
            notes.append(clarify_message)
            retreat_meta = {}
            canonical_retreat_target = ""
        retreat_id = str((retreat_meta or {}).get("ref_id") or "").strip() or None
        if not clarify_message:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.retreat,
                    target_ref=retreat_id or (canonical_retreat_target or None),
                    target_kind="npc" if (retreat_id or canonical_retreat_target) else "environment",
                    parameters={
                        "intent": "retreat",
                        "target_name": canonical_retreat_target or None,
                        "target_id": retreat_id,
                        "target_role": str((retreat_meta or {}).get("role") or "") or None,
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
        inspect_target = _extract_inspect_target(text)
        inspect_meta, inspect_candidates = _resolve_scene_target_reference_with_candidates(inspect_target or "", scene_point_ref_index)
        inspect_target_id = str(inspect_meta.get("ref_id") or "").strip() or None
        inspect_target_kind = str(inspect_meta.get("kind") or "").strip() or None
        if inspect_target and not inspect_target_id and inspect_candidates:
            actions.append(
                _clarify_action_for_scene_target(
                    message="Mehrere passende Interaktionspunkte gefunden. Bitte waehle ein sichtbares Ziel.",
                    reason="ambiguous_scene_target",
                    action_type="INSPECT",
                    candidate_entries=inspect_candidates,
                )
            )
            notes.append("Fokussierte Untersuchung erkannt, aber mehrere sichtbare Interaktionspunkte passen.")
        elif inspect_target and inspect_target_id:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.inspect,
                    target_ref=inspect_target_id,
                    target_kind=inspect_target_kind or "scene_point",
                    parameters={
                        "intent": "inspect",
                        "target_id": inspect_target_id,
                        "target_name": str(inspect_meta.get("name") or inspect_target),
                        "target_kind": inspect_target_kind or "scene_point",
                        "target_location_name": str(inspect_meta.get("location_name") or "") or None,
                        "target_zone_id": str(inspect_meta.get("scene_zone_id") or "") or None,
                        "target_zone_name": str(inspect_meta.get("scene_zone_name") or "") or None,
                    },
                    confidence=0.82,
                )
            )
            notes.append(f"Fokussierte Untersuchung erkannt: {inspect_meta.get('name') or inspect_target}")
        else:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.inspect,
                    target_kind="environment",
                    parameters={"intent": "inspect"},
                    confidence=0.7,
                )
            )
            notes.append("Untersuchungsaktion erkannt.")

    if not actions and _contains_any_verb(lowered, _OPEN_VERBS):
        open_target = _extract_open_search_target(text)
        open_meta, open_candidates = _resolve_scene_target_reference_with_candidates(open_target or "", scene_point_ref_index)
        open_target_id = str(open_meta.get("ref_id") or "").strip() or None
        open_target_kind = str(open_meta.get("kind") or "").strip() or None
        if open_target and not open_target_id and open_candidates:
            actions.append(
                _clarify_action_for_scene_target(
                    message="Mehrere passende Objekte/Behaeltnisse gefunden. Bitte waehle ein sichtbares Ziel.",
                    reason="ambiguous_open_target",
                    action_type="OPEN",
                    candidate_entries=open_candidates,
                )
            )
            notes.append("Oeffnen erkannt, aber mehrere sichtbare Ziele passen.")
        elif open_target and open_target_id:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.open,
                    target_ref=open_target_id,
                    target_kind=open_target_kind or "scene_object",
                    parameters={
                        "intent": "open",
                        "target_id": open_target_id,
                        "target_name": str(open_meta.get("name") or open_target),
                        "target_kind": open_target_kind or "scene_object",
                        "target_location_name": str(open_meta.get("location_name") or "") or None,
                        "target_zone_id": str(open_meta.get("scene_zone_id") or "") or None,
                        "target_zone_name": str(open_meta.get("scene_zone_name") or "") or None,
                    },
                    confidence=0.82,
                )
            )
            notes.append(f"Oeffnen erkannt: {open_meta.get('name') or open_target}")
        else:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.clarify,
                    target_kind="environment",
                    parameters={
                        "intent": "clarify",
                        "reason": "unknown_open_target",
                        "message": "Unklar, was geoeffnet werden soll. Bitte waehle ein sichtbares Objekt/Behaeltnis.",
                    },
                    confidence=0.35,
                )
            )
            notes.append("Oeffnen erkannt, aber kein sichtbares Objekt/Behaeltnis zugeordnet.")

    if not actions and _contains_any_verb(lowered, _SEARCH_VERBS):
        search_target = _extract_open_search_target(text)
        search_meta, search_candidates = _resolve_scene_target_reference_with_candidates(search_target or "", scene_point_ref_index)
        search_target_id = str(search_meta.get("ref_id") or "").strip() or None
        search_target_kind = str(search_meta.get("kind") or "").strip() or None
        if search_target and not search_target_id and search_candidates:
            actions.append(
                _clarify_action_for_scene_target(
                    message="Mehrere passende Ziele zum Durchsuchen gefunden. Bitte waehle ein sichtbares Objekt/Behaeltnis.",
                    reason="ambiguous_search_target",
                    action_type="SEARCH",
                    candidate_entries=search_candidates,
                )
            )
            notes.append("Durchsuchen erkannt, aber mehrere sichtbare Ziele passen.")
        elif search_target and search_target_id:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.search,
                    target_ref=search_target_id,
                    target_kind=search_target_kind or "scene_object",
                    parameters={
                        "intent": "search",
                        "target_id": search_target_id,
                        "target_name": str(search_meta.get("name") or search_target),
                        "target_kind": search_target_kind or "scene_object",
                        "target_location_name": str(search_meta.get("location_name") or "") or None,
                        "target_zone_id": str(search_meta.get("scene_zone_id") or "") or None,
                        "target_zone_name": str(search_meta.get("scene_zone_name") or "") or None,
                    },
                    confidence=0.82,
                )
            )
            notes.append(f"Durchsuchen erkannt: {search_meta.get('name') or search_target}")
        else:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.clarify,
                    target_kind="environment",
                    parameters={
                        "intent": "clarify",
                        "reason": "unknown_search_target",
                        "message": "Unklar, was durchsucht werden soll. Bitte waehle ein sichtbares Objekt/Behaeltnis.",
                    },
                    confidence=0.35,
                )
            )
            notes.append("Durchsuchen erkannt, aber kein sichtbares Objekt/Behaeltnis zugeordnet.")

    if not actions and _contains_any_verb(lowered, _TAKE_VERBS):
        take_target = _extract_take_target(text)
        take_meta, take_candidates = _resolve_scene_target_reference_with_candidates(take_target or "", scene_point_ref_index)
        take_target_id = str(take_meta.get("ref_id") or "").strip() or None
        take_target_kind = str(take_meta.get("kind") or "").strip() or None
        if take_target and not take_target_id and take_candidates:
            actions.append(
                _clarify_action_for_scene_target(
                    message="Mehrere passende Objekte gefunden. Bitte waehle ein sichtbares Objekt zum Mitnehmen.",
                    reason="ambiguous_take_target",
                    action_type="TAKE",
                    candidate_entries=take_candidates,
                )
            )
            notes.append("Aufnehmen erkannt, aber mehrere sichtbare Objekte passen.")
        elif take_target and take_target_id:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.take,
                    target_ref=take_target_id,
                    target_kind=take_target_kind or "scene_object",
                    parameters={
                        "intent": "take",
                        "target_id": take_target_id,
                        "target_name": str(take_meta.get("name") or take_target),
                        "target_kind": take_target_kind or "scene_object",
                        "target_location_name": str(take_meta.get("location_name") or "") or None,
                        "target_zone_id": str(take_meta.get("scene_zone_id") or "") or None,
                        "target_zone_name": str(take_meta.get("scene_zone_name") or "") or None,
                    },
                    confidence=0.78,
                )
            )
            notes.append(f"Aufnehmen erkannt: {take_meta.get('name') or take_target}")
        else:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.clarify,
                    target_kind="environment",
                    parameters={
                        "intent": "clarify",
                        "reason": "unknown_take_target",
                        "message": "Unklar, was aufgenommen werden soll. Bitte waehle ein sichtbares Objekt.",
                    },
                    confidence=0.35,
                )
            )
            notes.append("Aufnehmen erkannt, aber kein sichtbares Objekt zugeordnet.")

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


def _extract_inspect_target(text: str) -> str | None:
    patterns = [
        r"\b(?:untersuche|inspiziere|betrachte)\s+(?:den|die|das|dem|der|einen|eine|einem)?\s*([\w _-]+)",
        r"\b(?:schau(?:e)?|sieh)\s+(?:mir\s+)?(?:den|die|das|dem|der|einen|eine|einem)?\s*([\w _-]+)\s+an\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        target = _trim_entity_phrase(match.group(1))
        normalized = (target or "").strip().lower()
        if normalized in {"", "mich", "mich um", "um", "umgebung", "die umgebung"}:
            continue
        return target
    return None


def _extract_open_search_target(text: str) -> str | None:
    patterns = [
        r"\b(?:oeffne|öffne|durchsuche|durchforste|wuehle|wühle)\s+(?:den|die|das|dem|der|einen|eine|einem)?\s*([\w _-]+)",
        r"\bmache\s+(?:den|die|das)\s+([\w _-]+)\s+auf\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        target = _trim_entity_phrase(match.group(1))
        if target:
            return target
    return None


def _extract_take_target(text: str) -> str | None:
    patterns = [
        r"\b(?:nimm|nehme|hebe)\s+(?:den|die|das|dem|der|einen|eine|einem)?\s*([\w _-]+)",
        r"\b(?:packe?|stecke?)\s+(?:den|die|das|einen|eine)?\s*([\w _-]+)\s+ein\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        target = _trim_entity_phrase(match.group(1))
        if target:
            return target
    return None


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


def _resolve_scene_target_reference_with_candidates(
    candidate: str,
    scene_ref_index: RefMetaIndex,
) -> tuple[dict[str, str], list[dict[str, str]]]:
    if not candidate.strip():
        return {}, []
    matches = _find_scene_ref_matches(candidate, scene_ref_index)
    if not matches:
        return {}, []
    if len(matches) == 1:
        return matches[0], []
    return {}, matches[:8]


def _resolve_npc_target_reference(
    candidate: str,
    known_npc_names: list[str],
    known_npc_refs: list[dict[str, str]],
    npc_ref_index: RefMetaIndex,
) -> tuple[str, dict[str, str], str | None]:
    canonical_name = _canonicalize_name(candidate, known_npc_names)
    target_meta = _lookup_ref_entry(canonical_name, npc_ref_index) or {}
    if target_meta:
        return canonical_name, target_meta, None

    role_resolution = resolve_unique_role_title_npc_reference(candidate, known_npc_refs)
    if not role_resolution:
        return canonical_name, {}, None
    if str(role_resolution.get("status")) == "ambiguous":
        role_name = str(role_resolution.get("role") or "npc")
        candidates = [str(name) for name in (role_resolution.get("candidates") or []) if str(name).strip()]
        if candidates:
            return (
                canonical_name,
                {},
                f"Mehrdeutige Rollen-Anrede erkannt ({role_name}). Bitte praezisieren: {', '.join(candidates[:4])}.",
            )
        return canonical_name, {}, f"Mehrdeutige Rollen-Anrede erkannt ({role_name}). Bitte praezisieren."

    matched_entry = dict(role_resolution.get("entry") or {})
    matched_name = str(matched_entry.get("name") or canonical_name).strip() or canonical_name
    return matched_name, matched_entry, None


def _clarify_action_for_npc_target(
    *,
    message: str,
    reason: str,
    candidate_entries: list[dict[str, str]] | None = None,
    suggested_action: str | None = None,
) -> TurnIntentAction:
    clarify_parameters: dict[str, str | int | float | bool | None] = {
        "intent": "clarify",
        "reason": reason,
        "message": message,
    }
    if suggested_action:
        clarify_parameters["suggested_action"] = suggested_action
    encoded_candidates = _encode_clarify_candidates(candidate_entries or [])
    if encoded_candidates:
        clarify_parameters["candidates_json"] = encoded_candidates
    return TurnIntentAction(
        action_type=ActionType.clarify,
        target_kind="npc",
        parameters=clarify_parameters,
        confidence=0.35,
    )


def _clarify_action_for_scene_target(
    *,
    message: str,
    reason: str,
    action_type: str,
    candidate_entries: list[dict[str, str]] | None = None,
) -> TurnIntentAction:
    clarify_parameters: dict[str, str | int | float | bool | None] = {
        "intent": "clarify",
        "reason": reason,
        "message": message,
        "suggested_action": "select_visible_scene_target",
    }
    encoded_candidates = _encode_clarify_candidates(
        _scene_clarify_candidates(candidate_entries or [], action_type=action_type)
    )
    if encoded_candidates:
        clarify_parameters["candidates_json"] = encoded_candidates
    return TurnIntentAction(
        action_type=ActionType.clarify,
        target_kind="environment",
        parameters=clarify_parameters,
        confidence=0.35,
    )


def _npc_visible_candidates(known_npc_refs: list[dict[str, str]]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for entry in known_npc_refs:
        ref_id = str(entry.get("ref_id") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not ref_id or not name:
            continue
        candidates.append(
            {
                "action_type": "TALK",
                "target_ref": ref_id,
                "target_kind": "npc",
                "label": name,
                "name": name,
                "role": str(entry.get("role") or "").strip(),
            }
        )
    return candidates[:8]


def _npc_clarify_candidates_from_role_title(candidate_text: str, known_npc_refs: list[dict[str, str]]) -> list[dict[str, str]]:
    role_resolution = resolve_unique_role_title_npc_reference(candidate_text, known_npc_refs)
    if not role_resolution or str(role_resolution.get("status")) != "ambiguous":
        return []
    raw_entries = role_resolution.get("candidate_entries") or []
    if not isinstance(raw_entries, list):
        return []
    candidates: list[dict[str, str]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            continue
        ref_id = str(raw_entry.get("ref_id") or "").strip()
        name = str(raw_entry.get("name") or "").strip()
        if not ref_id or not name:
            continue
        candidates.append(
            {
                "action_type": "TALK",
                "target_ref": ref_id,
                "target_kind": "npc",
                "label": name,
                "name": name,
                "role": str(raw_entry.get("role") or "").strip(),
            }
        )
    return candidates[:8]


def _encode_clarify_candidates(entries: list[dict[str, str]]) -> str | None:
    if not entries:
        return None
    safe_entries: list[dict[str, str]] = []
    for entry in entries:
        action_type = str(entry.get("action_type") or "").strip().upper()
        target_ref = str(entry.get("target_ref") or "").strip()
        if not action_type or not target_ref:
            continue
        safe_entries.append(
            {
                "action_type": action_type,
                "target_ref": target_ref,
                "target_kind": str(entry.get("target_kind") or "").strip(),
                "label": str(entry.get("label") or entry.get("name") or target_ref).strip(),
                "name": str(entry.get("name") or "").strip(),
                "role": str(entry.get("role") or "").strip(),
                "kind": str(entry.get("kind") or "").strip(),
            }
        )
    if not safe_entries:
        return None
    return json.dumps(safe_entries, ensure_ascii=False)


def _find_scene_ref_matches(candidate: str, scene_ref_index: RefMetaIndex) -> list[dict[str, str]]:
    normalized = candidate.strip().lower()
    if not normalized:
        return []
    exact = ref_index_entry = scene_ref_index.get(normalized)
    if exact:
        return [ref_index_entry]

    matches: list[dict[str, str]] = []
    for known_name, ref_entry in scene_ref_index.items():
        alias_tokens = [token.strip().lower() for token in str(ref_entry.get("aliases_csv") or "").split(",") if token.strip()]
        haystacks = [known_name, *alias_tokens]
        if any(normalized in hay or hay in normalized for hay in haystacks if hay):
            matches.append(ref_entry)

    unique_by_ref: dict[str, dict[str, str]] = {}
    for entry in matches:
        ref_id = str(entry.get("ref_id") or "").strip()
        if ref_id and ref_id not in unique_by_ref:
            unique_by_ref[ref_id] = entry
    return list(unique_by_ref.values())


def _scene_clarify_candidates(entries: list[dict[str, str]], *, action_type: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for entry in entries:
        ref_id = str(entry.get("ref_id") or "").strip()
        name = str(entry.get("name") or "").strip()
        kind = str(entry.get("kind") or "scene_point").strip()
        if not ref_id or not name:
            continue
        candidates.append(
            {
                "action_type": action_type.upper(),
                "target_ref": ref_id,
                "target_kind": kind,
                "label": f"{name} ({kind})",
                "name": name,
                "kind": kind,
            }
        )
    return candidates[:8]


def _requires_existing_npc_resolution(*, target: str, target_meta: dict[str, str]) -> bool:
    if target_meta:
        return False
    return True


def _looks_like_descriptive_unresolved_npc_reference(*, target: str, target_meta: dict[str, str]) -> bool:
    if target_meta:
        return False
    normalized = (target or "").strip().lower()
    if not normalized:
        return False
    return any(hint in normalized for hint in _DESCRIPTIVE_NPC_REFERENCE_HINTS)
