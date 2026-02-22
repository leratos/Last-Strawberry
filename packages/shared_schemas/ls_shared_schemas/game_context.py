from __future__ import annotations

from pydantic import Field

from .common import LSBaseModel
from .npc_memory import NPCMemoryBundle
from .turns import PersistedTurnRecord
from .world import JournalEntryRecord, WorldSessionResponse


class RetrievedNpcMemoryBundle(LSBaseModel):
    bundle: NPCMemoryBundle
    relevance_score: float = Field(default=0.0, ge=0.0)
    retrieval_reasons: list[str] = Field(default_factory=list)


class GameContextResponse(LSBaseModel):
    world: WorldSessionResponse
    recent_turns: list[PersistedTurnRecord] = Field(default_factory=list)
    recent_journal: list[JournalEntryRecord] = Field(default_factory=list)
    npc_memory: list[RetrievedNpcMemoryBundle] = Field(default_factory=list)
    retrieval_player_input: str | None = Field(default=None, max_length=2000)
    retrieval_notes: list[str] = Field(default_factory=list)
