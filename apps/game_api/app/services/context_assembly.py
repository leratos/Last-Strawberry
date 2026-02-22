from __future__ import annotations

import re

from ls_shared_schemas.game_context import GameContextResponse, RetrievedNpcMemoryBundle
from ls_shared_schemas.npc_memory import NPCMemoryBundle
from ls_shared_schemas.turns import PersistedTurnRecord
from ls_shared_schemas.world import JournalEntryRecord, WorldSessionResponse


def assemble_game_context(
    *,
    world: WorldSessionResponse,
    turns: list[PersistedTurnRecord],
    npc_memory: list[NPCMemoryBundle],
    retrieval_player_input: str | None = None,
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

    return GameContextResponse(
        world=world,
        recent_turns=recent_turns,
        recent_journal=recent_journal,
        npc_memory=retrieved_memory,
        retrieval_player_input=retrieval_player_input,
        retrieval_notes=retrieval_notes,
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

        results.append(
            RetrievedNpcMemoryBundle(
                bundle=bundle.model_copy(update={"recent_memories": selected_memories}),
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
