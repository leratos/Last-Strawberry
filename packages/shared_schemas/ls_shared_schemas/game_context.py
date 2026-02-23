from __future__ import annotations

from pydantic import Field

from .common import LSBaseModel
from .npc_memory import NPCMemoryBundle
from .turns import PersistedTurnRecord
from .world import JournalEntryRecord, WorldSessionResponse


class GameTargetReference(LSBaseModel):
    ref_id: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    role: str | None = Field(default=None, max_length=80)
    faction: str | None = Field(default=None, max_length=120)
    aliases: list[str] = Field(default_factory=list)
    source: str = Field(default="derived", min_length=1, max_length=80)
    location_name: str | None = Field(default=None, max_length=120)
    scene_zone_id: str | None = Field(default=None, max_length=120)
    scene_zone_name: str | None = Field(default=None, max_length=120)
    distance_band_to_player: str | None = Field(default=None, max_length=40)
    detail_level: int | None = Field(default=None, ge=0, le=10)
    discovery_state: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class GameTargetCatalog(LSBaseModel):
    npcs: list[GameTargetReference] = Field(default_factory=list)
    items: list[GameTargetReference] = Field(default_factory=list)
    locations: list[GameTargetReference] = Field(default_factory=list)
    scene_points: list[GameTargetReference] = Field(default_factory=list)


class RetrievedNpcMemoryBundle(LSBaseModel):
    bundle: NPCMemoryBundle
    relevance_score: float = Field(default=0.0, ge=0.0)
    retrieval_reasons: list[str] = Field(default_factory=list)


class GameContextResponse(LSBaseModel):
    world: WorldSessionResponse
    recent_turns: list[PersistedTurnRecord] = Field(default_factory=list)
    recent_journal: list[JournalEntryRecord] = Field(default_factory=list)
    npc_memory: list[RetrievedNpcMemoryBundle] = Field(default_factory=list)
    target_catalog: GameTargetCatalog = Field(default_factory=GameTargetCatalog)
    retrieval_player_input: str | None = Field(default=None, max_length=2000)
    retrieval_notes: list[str] = Field(default_factory=list)
    discovery_counts: dict[str, int] = Field(default_factory=dict)
