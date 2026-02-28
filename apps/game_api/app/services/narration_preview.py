from __future__ import annotations

from apps.game_api.app.services.story_beats import build_story_beats_from_resolution
from ls_shared_schemas.turns import NarrativeEnvelope, TurnResolution


def build_narrative_from_resolution(resolution: TurnResolution) -> NarrativeEnvelope:
    story_beats = build_story_beats_from_resolution(resolution)
    primary_events = [
        event.message for event in resolution.system_events if not event.code.startswith("npc_reacts_")
    ]
    event_codes = [event.code for event in resolution.system_events if not event.code.startswith("npc_reacts_")]
    reaction_events = [
        event.message for event in resolution.system_events if event.code.startswith("npc_reacts_")
    ]
    summary_parts: list[str] = []
    if primary_events:
        summary_parts.append(" ".join(primary_events[:2]).strip())
    loot_messages = [
        event.message
        for event in resolution.system_events
        if event.code in {"container_loot_found", "container_empty", "container_already_searched"}
    ]
    if loot_messages:
        summary_parts.append(f"Fund: {loot_messages[0]}")
    elif "container_opened" in event_codes:
        opened_message = next(
            (event.message for event in resolution.system_events if event.code == "container_opened"),
            "",
        )
        if opened_message:
            summary_parts.append(f"Behaeltnis: {opened_message}")
    if reaction_events:
        summary_parts.append(f"Reaktion: {reaction_events[0]}")
    event_summary = " ".join(part for part in summary_parts if part).strip() or "Die Situation entwickelt sich weiter."
    location = resolution.resulting_character_state.location_name
    hp = resolution.resulting_character_state.resources.hp
    narrative = (
        f"Du befindest dich nun in {location}. {event_summary} "
        f"Dein aktueller Zustand wirkt stabil (HP: {hp}). Was tust du als naechstes?"
    )
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
