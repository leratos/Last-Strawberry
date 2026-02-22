from __future__ import annotations

from ls_shared_schemas.turns import NarrativeEnvelope, TurnResolution


def build_narrative_from_resolution(resolution: TurnResolution) -> NarrativeEnvelope:
    events = [event.message for event in resolution.system_events]
    event_summary = " ".join(events[:3]).strip() or "Die Situation entwickelt sich weiter."
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
        actionable_options=[
            "Umsehen und Hinweise sammeln",
            "Mit einer Person sprechen",
            "Ein Item aus dem Inventar verwenden",
        ],
    )
