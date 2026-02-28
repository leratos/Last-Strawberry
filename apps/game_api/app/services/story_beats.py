from __future__ import annotations

from ls_shared_schemas.turns import TurnResolution


def build_story_beats_from_resolution(resolution: TurnResolution) -> list[str]:
    beats: list[str] = []
    character_state = resolution.resulting_character_state
    location = character_state.location_name
    zone = character_state.scene_zone_name
    beats.append(f"scene: Ort={location}; Zone={zone}")

    primary_events = [
        event for event in resolution.system_events if not event.code.startswith("npc_reacts_")
    ]
    if primary_events:
        beats.append(f"action: {primary_events[0].code} | {primary_events[0].message}")
    if len(primary_events) > 1:
        beats.append(f"consequence: {primary_events[1].code} | {primary_events[1].message}")

    loot_event = next(
        (
            event
            for event in resolution.system_events
            if event.code in {"container_loot_found", "container_empty", "container_already_searched"}
        ),
        None,
    )
    if loot_event is not None:
        beats.append(f"loot: {loot_event.code} | {loot_event.message}")

    reaction_event = next(
        (event for event in resolution.system_events if event.code.startswith("npc_reacts_")),
        None,
    )
    if reaction_event is not None:
        beats.append(f"npc_reaction: {reaction_event.code} | {reaction_event.message}")

    quest_event = next(
        (event for event in resolution.system_events if event.code in {"quest_objective_updated", "quest_completed", "quest_unlocked"}),
        None,
    )
    if quest_event is not None:
        beats.append(f"quest: {quest_event.code} | {quest_event.message}")

    resources = character_state.resources
    beats.append(
        "state: "
        f"hp={resources.hp}/{resources.max_hp}; "
        f"stamina={resources.stamina}/{resources.max_stamina}; "
        f"focus={resources.focus}/{resources.max_focus}"
    )
    return beats[:8]
