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
_INSPECT_VERBS = ("untersuche", "umschauen", "umsehen", "betrachte", "inspiziere")


def analyze_player_input_preview(
    *,
    world_id: str,
    world_character_id: str,
    player_input: str,
    inventory: list[InventoryItemInstance],
) -> TurnIntent:
    text = (player_input or "").strip()
    lowered = text.lower()
    actions: list[TurnIntentAction] = []
    notes: list[str] = []

    destination = _extract_destination(text)
    if destination:
        actions.append(
            TurnIntentAction(
                action_type=ActionType.move,
                destination=destination,
                confidence=0.85,
            )
        )
        notes.append(f"Bewegungsziel erkannt: {destination}")

    if any(verb in lowered for verb in _USE_VERBS):
        matched_item = _match_inventory_item(lowered, inventory)
        if matched_item is not None:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.use_item,
                    item_ref=matched_item.inventory_item_id,
                    target_ref=matched_item.name,
                    confidence=0.9,
                )
            )
            notes.append(f"Benutzbares Inventarobjekt erkannt: {matched_item.name}")
        else:
            actions.append(
                TurnIntentAction(
                    action_type=ActionType.use_item,
                    target_ref="unbekanntes_item",
                    confidence=0.45,
                )
            )
            notes.append("Item-Verwendung erkannt, aber kein Inventar-Match gefunden.")

    if any(verb in lowered for verb in _ATTACK_VERBS):
        target = _extract_target_after_verb(text, _ATTACK_VERBS) or "gegner"
        actions.append(
            TurnIntentAction(action_type=ActionType.attack, target_ref=target, confidence=0.8)
        )
        notes.append(f"Angriff erkannt: {target}")

    if any(verb in lowered for verb in _TALK_VERBS):
        target = _extract_talk_target(text) or "npc"
        actions.append(TurnIntentAction(action_type=ActionType.talk, target_ref=target, confidence=0.75))
        notes.append(f"Gespraech erkannt: {target}")

    if not actions and any(verb in lowered for verb in _INSPECT_VERBS):
        actions.append(TurnIntentAction(action_type=ActionType.inspect, confidence=0.7))
        notes.append("Untersuchungsaktion erkannt.")

    if not actions:
        actions.append(TurnIntentAction(action_type=ActionType.clarify, confidence=0.25))
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
            target = match.group(1).strip(" .,!?:;")
            if target:
                return target
    return None


def _extract_talk_target(text: str) -> str | None:
    match = re.search(r"\b(?:mit|zu)\s+(?:dem|der|den|einem|einer)?\s*([a-zA-Z0-9äöüÄÖÜß _-]+)", text, re.I)
    if not match:
        return None
    target = match.group(1).strip(" .,!?:;")
    return target or None
