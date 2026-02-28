from __future__ import annotations

from apps.game_api.app.services.story_beats import build_story_beats_from_resolution
from ls_shared_schemas.turns import NarrativeEnvelope, TurnResolution


_TECHNICAL_EVENT_CODES = {
    "dialog_topic_applied",
    "dialog_topic_skill_check",
    "partial_multiaction_parse",
    "partial_multiclause_parse",
}

_QUEST_EVENT_CODES = {"quest_objective_updated", "quest_completed", "quest_unlocked"}


def _as_sentence(text: str) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        return ""
    if cleaned[-1] not in ".!?":
        return f"{cleaned}."
    return cleaned


def _lowercase_first(text: str) -> str:
    if not text:
        return text
    return text[0].lower() + text[1:]


def _compact_sentence(text: str) -> str:
    return _as_sentence(" ".join((text or "").strip().split()))


def _pick_opening(location: str, event_codes: list[str]) -> str:
    has_attack = any("attack" in code for code in event_codes)
    has_talk = any("talk" in code for code in event_codes)
    has_discovery = any(
        code.startswith("inspect_") or code.startswith("search_") or code.startswith("open_")
        for code in event_codes
    )
    has_move = any(code in {"move_success", "auto_move_location_for_talk"} for code in event_codes)

    if has_attack:
        return _compact_sentence(f"In {location} spannt sich die Lage fuer einen Moment gefaehrlich an")
    if has_talk and has_move:
        return _compact_sentence(f"Du erreichst {location} und kommst dort schnell ins Gespraech")
    if has_talk:
        return _compact_sentence(f"In {location} ergibt sich ein Gespraech mit neuer Richtung")
    if has_discovery:
        return _compact_sentence(f"In {location} gehst du den naechsten Spuren aufmerksam nach")
    if has_move:
        return _compact_sentence(f"Du verschaffst dir in {location} einen neuen Ueberblick")
    return _compact_sentence(f"Die Szene in {location} bleibt in Bewegung")


def _build_resource_line(resolution: TurnResolution) -> str:
    resources = resolution.resulting_character_state.resources
    hp_delta = int(resolution.state_delta.hp_delta or 0)
    stamina_delta = int(resolution.state_delta.stamina_delta or 0)
    focus_delta = int(resolution.state_delta.focus_delta or 0)
    low_hp = resources.hp <= max(1, resources.max_hp // 2)

    if hp_delta == 0 and stamina_delta == 0 and focus_delta == 0 and not low_hp:
        return ""

    deltas: list[str] = []
    if hp_delta != 0:
        deltas.append(f"HP {hp_delta:+d}")
    if stamina_delta != 0:
        deltas.append(f"Ausdauer {stamina_delta:+d}")
    if focus_delta != 0:
        deltas.append(f"Fokus {focus_delta:+d}")
    delta_text = ", ".join(deltas) if deltas else "keine direkten Verluste"

    if low_hp:
        return _compact_sentence(f"Du bist weiter angeschlagen (HP: {resources.hp}/{resources.max_hp}; {delta_text})")
    return _compact_sentence(f"Dein Zustand bleibt kontrollierbar ({delta_text})")


def build_narrative_from_resolution(resolution: TurnResolution) -> NarrativeEnvelope:
    story_beats = build_story_beats_from_resolution(resolution)
    non_reaction_events = [event for event in resolution.system_events if not event.code.startswith("npc_reacts_")]
    event_codes = [event.code for event in non_reaction_events]
    reaction_events = [
        event.message for event in resolution.system_events if event.code.startswith("npc_reacts_")
    ]
    location = resolution.resulting_character_state.location_name
    action_messages = [
        _as_sentence(event.message)
        for event in non_reaction_events
        if event.code not in _TECHNICAL_EVENT_CODES and event.code not in _QUEST_EVENT_CODES
    ]
    action_messages = [message for message in action_messages if message]
    first_action = action_messages[0] if action_messages else ""
    second_action = action_messages[1] if len(action_messages) > 1 else ""

    opening = _pick_opening(location=location, event_codes=event_codes)
    narrative_parts: list[str] = [opening]
    if first_action and first_action.lower() not in opening.lower():
        narrative_parts.append(first_action)
    if second_action:
        narrative_parts.append(_compact_sentence(f"Dabei {_lowercase_first(second_action)}"))

    if reaction_events:
        narrative_parts.append(_compact_sentence(f"Daraufhin {_lowercase_first(reaction_events[0])}"))

    if resolution.state_delta.inventory_gained:
        gained_entry = resolution.state_delta.inventory_gained[0]
        gained_name = str(gained_entry.get("name") or gained_entry.get("item_name") or "ein Gegenstand").strip()
        gained_quantity_raw = gained_entry.get("quantity")
        gained_quantity = int(gained_quantity_raw) if isinstance(gained_quantity_raw, int) else 1
        narrative_parts.append(_compact_sentence(f"Zwischen den Spuren sicherst du {gained_name} x{max(1, gained_quantity)}"))
    elif non_reaction_events:
        loot_messages = [
            _as_sentence(event.message)
            for event in non_reaction_events
            if event.code in {"container_loot_found", "container_empty", "container_already_searched"}
        ]
        if loot_messages:
            narrative_parts.append(_compact_sentence(f"Beim Durchsuchen zeigt sich: {_lowercase_first(loot_messages[0])}"))

    quest_messages = [
        _as_sentence(event.message) for event in non_reaction_events if event.code in _QUEST_EVENT_CODES
    ]
    if quest_messages:
        narrative_parts.append(_compact_sentence(f"Fuer deinen Auftrag zaehlt dabei: {_lowercase_first(quest_messages[0])}"))

    if any(code in _TECHNICAL_EVENT_CODES for code in event_codes):
        narrative_parts.append(
            _compact_sentence(
                "Nicht jede Teilaktion wurde bereits vollstaendig aufgeloest; offene Schritte kannst du im naechsten Zug gezielt nachziehen"
            )
        )

    state_line = _build_resource_line(resolution)
    if state_line:
        narrative_parts.append(state_line)

    narrative = f"{' '.join(part for part in narrative_parts if part).strip()} Was tust du als naechstes?"
    return NarrativeEnvelope(
        world_id=resolution.world_id,
        world_character_id=resolution.world_character_id,
        narrative=narrative,
        story_beats=story_beats,
        actionable_options=[
            "Umsehen und Hinweise sammeln",
            "Mit einer Person sprechen",
            "Ein Item aus dem Inventar verwenden",
        ],
    )
