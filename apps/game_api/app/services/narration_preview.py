from __future__ import annotations

from apps.game_api.app.services.story_beats import build_story_beats_from_resolution
from ls_shared_schemas.turns import NarrativeEnvelope, TurnResolution


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


def build_narrative_from_resolution(resolution: TurnResolution) -> NarrativeEnvelope:
    story_beats = build_story_beats_from_resolution(resolution)
    primary_events = [
        event.message for event in resolution.system_events if not event.code.startswith("npc_reacts_")
    ]
    event_codes = [event.code for event in resolution.system_events if not event.code.startswith("npc_reacts_")]
    reaction_events = [
        event.message for event in resolution.system_events if event.code.startswith("npc_reacts_")
    ]
    location = resolution.resulting_character_state.location_name
    hp = resolution.resulting_character_state.resources.hp
    technical_codes = {"dialog_topic_applied", "dialog_topic_skill_check", "partial_multiaction_parse"}
    action_messages = [
        _as_sentence(event.message)
        for event in resolution.system_events
        if not event.code.startswith("npc_reacts_") and event.code not in technical_codes
    ]
    action_messages = [message for message in action_messages if message]
    first_action = action_messages[0] if action_messages else ""
    second_action = action_messages[1] if len(action_messages) > 1 else ""

    has_move = any(code in {"move_success", "auto_move_location_for_talk"} for code in event_codes)
    has_talk = any("talk" in code for code in event_codes)
    has_attack = any("attack" in code for code in event_codes)

    if has_move:
        opening = _as_sentence(f"Du erreichst {location}")
    elif has_talk:
        opening = _as_sentence(f"In {location} entspinnt sich ein Gespraech")
    elif has_attack:
        opening = _as_sentence(f"In {location} spitzt sich die Lage kurz zu")
    else:
        opening = _as_sentence(f"Die Szene in {location} entwickelt sich weiter")

    narrative_parts: list[str] = [opening]
    if first_action and first_action.lower() not in opening.lower():
        narrative_parts.append(first_action)
    if second_action:
        narrative_parts.append(_as_sentence(f"Danach {_lowercase_first(second_action)}"))

    if reaction_events:
        narrative_parts.append(_as_sentence(f"Die Reaktion darauf: {reaction_events[0]}"))

    if resolution.state_delta.inventory_gained:
        gained_entry = resolution.state_delta.inventory_gained[0]
        gained_name = str(gained_entry.get("name") or gained_entry.get("item_name") or "ein Gegenstand").strip()
        gained_quantity_raw = gained_entry.get("quantity")
        gained_quantity = int(gained_quantity_raw) if isinstance(gained_quantity_raw, int) else 1
        narrative_parts.append(_as_sentence(f"Du sicherst {gained_name} x{max(1, gained_quantity)}"))
    elif primary_events:
        loot_messages = [
            _as_sentence(event.message)
            for event in resolution.system_events
            if event.code in {"container_loot_found", "container_empty", "container_already_searched"}
        ]
        if loot_messages:
            narrative_parts.append(_as_sentence(f"Beim Durchsuchen zeigt sich: {loot_messages[0]}"))

    hp_delta = int(resolution.state_delta.hp_delta or 0)
    if hp_delta < 0:
        state_line = _as_sentence(f"Der Zug kostet Kraft, aber du bleibst im Spiel (HP: {hp})")
    elif hp_delta > 0:
        state_line = _as_sentence(f"Du sammelst dich etwas und wirkst stabiler (HP: {hp})")
    else:
        state_line = _as_sentence(f"Du wirkst weiterhin handlungsfaehig (HP: {hp})")
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
