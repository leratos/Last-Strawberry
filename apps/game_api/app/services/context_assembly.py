from __future__ import annotations

import re

from ls_shared_schemas.game_context import GameContextResponse, GameTargetCatalog, GameTargetReference, RetrievedNpcMemoryBundle
from ls_shared_schemas.npc_memory import NPCMemoryBundle
from ls_shared_schemas.turns import PersistedTurnRecord
from ls_shared_schemas.world import JournalEntryRecord, WorldSessionResponse


def assemble_game_context(
    *,
    world: WorldSessionResponse,
    turns: list[PersistedTurnRecord],
    npc_memory: list[NPCMemoryBundle],
    retrieval_player_input: str | None = None,
    scene_points: list[GameTargetReference] | None = None,
    journal_limit: int = 20,
    turn_limit: int = 10,
    memory_per_npc: int = 3,
) -> GameContextResponse:
    safe_journal_limit = max(1, min(journal_limit, 100))
    safe_turn_limit = max(1, min(turn_limit, 50))
    safe_memory_limit = max(1, min(memory_per_npc, 10))

    retrieved_memory, retrieval_notes = _rank_npc_memory_bundles(
        bundles=npc_memory,
        player_input=retrieval_player_input,
        memory_per_npc=safe_memory_limit,
    )

    recent_journal = world.journal[-safe_journal_limit:]
    recent_turns = turns[-safe_turn_limit:]
    target_catalog = _build_target_catalog(world=world, turns=recent_turns, npc_memory=npc_memory, scene_points=scene_points or [])

    return GameContextResponse(
        world=world,
        recent_turns=recent_turns,
        recent_journal=recent_journal,
        npc_memory=retrieved_memory,
        target_catalog=target_catalog,
        retrieval_player_input=retrieval_player_input,
        retrieval_notes=retrieval_notes,
        hidden_npc_count=0,
        hidden_scene_point_count=0,
    )


def _rank_npc_memory_bundles(
    *,
    bundles: list[NPCMemoryBundle],
    player_input: str | None,
    memory_per_npc: int,
) -> tuple[list[RetrievedNpcMemoryBundle], list[str]]:
    if not bundles:
        return [], ["Keine NPC-Memory-Bundles vorhanden."]

    query_tokens = _tokenize(player_input or "")
    results: list[RetrievedNpcMemoryBundle] = []
    notes: list[str] = []
    if query_tokens:
        notes.append(f"Retrieval mit {len(query_tokens)} Query-Tokens.")
    else:
        notes.append("Retrieval ohne Query-Text: Sortierung nach Beziehung/Memory-Wichtigkeit.")

    for bundle in bundles:
        relationship_standing = float(bundle.relationship.standing) if bundle.relationship else 0.0
        memory_score = 0.0
        reasons: list[str] = []

        scored_memories = []
        for memory in bundle.recent_memories:
            token_overlap = 0
            if query_tokens:
                memory_tokens = _tokenize(memory.summary + " " + " ".join(memory.tags))
                token_overlap = len(query_tokens.intersection(memory_tokens))
            score = float(memory.importance) + (token_overlap * 0.3)
            scored_memories.append((score, token_overlap, memory))

        scored_memories.sort(key=lambda item: (item[0], item[1], item[2].created_at), reverse=True)
        selected_memories = [entry[2] for entry in scored_memories[:memory_per_npc]]
        if selected_memories:
            max_memory_score = scored_memories[0][0]
            memory_score = max_memory_score
            reasons.append(f"Top-Memory-Score={max_memory_score:.2f}")
            if scored_memories[0][1] > 0:
                reasons.append(f"Token-Match={scored_memories[0][1]}")

        bundle_score = max(0.0, memory_score + (abs(relationship_standing) / 100.0 * 0.25))
        if bundle.relationship is not None:
            reasons.append(f"Standing={bundle.relationship.standing}")

        bundle_for_context = bundle
        profile_updates: dict[str, object] = {}
        if not selected_memories and (bundle.profile.role or "").strip().lower() not in {"", "unknown"}:
            profile_updates["role"] = "unknown"
        if not selected_memories and (bundle.profile.faction or "").strip():
            profile_updates["faction"] = None
        if profile_updates:
            bundle_for_context = bundle.model_copy(
                update={"profile": bundle.profile.model_copy(update=profile_updates)}
            )
            reasons.append("Rolle noch nicht identifiziert")

        results.append(
            RetrievedNpcMemoryBundle(
                bundle=bundle_for_context.model_copy(update={"recent_memories": selected_memories}),
                relevance_score=round(bundle_score, 4),
                retrieval_reasons=reasons,
            )
        )

    results.sort(key=lambda item: (item.relevance_score, len(item.bundle.recent_memories)), reverse=True)
    return results, notes


def _tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-zA-Z0-9äöüÄÖÜß]+", text.lower())
        if len(token) >= 3
    }


def _build_target_catalog(
    *,
    world: WorldSessionResponse,
    turns: list[PersistedTurnRecord],
    npc_memory: list[NPCMemoryBundle],
    scene_points: list[GameTargetReference],
) -> GameTargetCatalog:
    npc_refs: dict[str, GameTargetReference] = {}
    item_refs: dict[str, GameTargetReference] = {}
    location_refs: dict[str, GameTargetReference] = {}
    role_revealed_npc_ids = {bundle.profile.npc_id for bundle in npc_memory if bundle.recent_memories}

    for npc in world.world_seed.starter_npcs:
        npc_refs[npc.npc_id] = GameTargetReference(
            ref_id=npc.npc_id,
            kind="npc",
            name=npc.name,
            role=npc.role if npc.npc_id in role_revealed_npc_ids else "unknown",
            faction=npc.faction if npc.npc_id in role_revealed_npc_ids else None,
            aliases=[],
            source="world_seed",
            location_name=npc.location_name or world.world_seed.start_location_name,
            scene_zone_id=npc.scene_zone_id,
            scene_zone_name=npc.scene_zone_name,
            distance_band_to_player=_distance_band_for_entity(
                world=world,
                entity_location_name=npc.location_name or world.world_seed.start_location_name,
                entity_zone_id=npc.scene_zone_id,
            ),
        )
    for bundle in npc_memory:
        profile = bundle.profile
        npc_refs[profile.npc_id] = GameTargetReference(
            ref_id=profile.npc_id,
            kind="npc",
            name=profile.name,
            role=profile.role if profile.npc_id in role_revealed_npc_ids else "unknown",
            faction=profile.faction if profile.npc_id in role_revealed_npc_ids else None,
            aliases=[],
            source="npc_memory",
            location_name=profile.location_name or world.world_seed.start_location_name,
            scene_zone_id=profile.scene_zone_id,
            scene_zone_name=profile.scene_zone_name,
            distance_band_to_player=_distance_band_for_entity(
                world=world,
                entity_location_name=profile.location_name or world.world_seed.start_location_name,
                entity_zone_id=profile.scene_zone_id,
            ),
        )

    for item in world.inventory:
        item_refs[item.inventory_item_id] = GameTargetReference(
            ref_id=item.inventory_item_id,
            kind="item",
            name=item.name,
            aliases=[item.item_def_id] if item.item_def_id and item.item_def_id != item.inventory_item_id else [],
            source="inventory",
        )

    current_location = world.character_state.location_name.strip()
    if current_location:
        location_refs[_location_ref_id_from_name(current_location)] = GameTargetReference(
            ref_id=_location_ref_id_from_name(current_location),
            kind="location",
            name=current_location,
            aliases=[],
            source="character_state",
            location_name=current_location,
            scene_zone_id=world.character_state.scene_zone_id,
            scene_zone_name=world.character_state.scene_zone_name,
            distance_band_to_player="adjacent",
        )
    start_location = world.world_seed.start_location_name.strip()
    if start_location:
        location_refs[_location_ref_id_from_name(start_location)] = GameTargetReference(
            ref_id=_location_ref_id_from_name(start_location),
            kind="location",
            name=start_location,
            aliases=[],
            source="world_seed",
            location_name=start_location,
            distance_band_to_player=_distance_band_for_entity(
                world=world,
                entity_location_name=start_location,
                entity_zone_id=None,
            ),
        )

    for turn in turns:
        for action in turn.intent.actions:
            if action.action_type.value == "MOVE":
                move_name = str(action.destination or action.parameters.get("destination_name") or "").strip()
                if move_name:
                    ref_id = str(action.parameters.get("destination_id") or _location_ref_id_from_name(move_name))
                    location_refs[ref_id] = GameTargetReference(
                        ref_id=ref_id,
                        kind="location",
                        name=move_name,
                        aliases=[],
                        source="turn_intent",
                        location_name=move_name,
                        distance_band_to_player=_distance_band_for_entity(
                            world=world,
                            entity_location_name=move_name,
                            entity_zone_id=None,
                        ),
                    )

    return GameTargetCatalog(
        npcs=sorted(npc_refs.values(), key=lambda ref: ref.name.lower()),
        items=sorted(item_refs.values(), key=lambda ref: ref.name.lower()),
        locations=sorted(location_refs.values(), key=lambda ref: ref.name.lower()),
        scene_points=sorted(scene_points, key=lambda ref: ref.name.lower()),
    )


def _location_ref_id_from_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"loc-{(slug or 'unknown')[:48]}"


def _distance_band_for_entity(
    *,
    world: WorldSessionResponse,
    entity_location_name: str | None,
    entity_zone_id: str | None,
) -> str:
    player_location = (world.character_state.location_name or "").strip()
    player_zone = (world.character_state.scene_zone_id or "").strip()
    target_location = (entity_location_name or "").strip()
    target_zone = (entity_zone_id or "").strip()

    if target_location and player_location and target_location != player_location:
        return "far"

    if target_zone and player_zone:
        if target_zone == player_zone:
            return "adjacent"
        if player_zone.startswith("zone-distance-far"):
            return "far"
        if player_zone.startswith("zone-distance-near"):
            return "near"
        return "near"

    if target_location and player_location and target_location == player_location:
        return "near"

    return "near"
