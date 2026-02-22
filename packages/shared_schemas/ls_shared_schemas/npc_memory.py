from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import LSBaseModel, utc_now


class NPCProfile(LSBaseModel):
    npc_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="npc", min_length=1, max_length=120)
    faction: str | None = Field(default=None, max_length=120)
    personality_tags: list[str] = Field(default_factory=list)
    stats: dict[str, int | float | str] = Field(default_factory=dict)


class NPCRelationship(LSBaseModel):
    npc_id: str = Field(min_length=1, max_length=120)
    world_character_id: str = Field(min_length=1, max_length=120)
    standing: int = Field(default=0, ge=-100, le=100)
    tags: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)
    updated_at: datetime = Field(default_factory=utc_now)


class NPCMemoryEntry(LSBaseModel):
    memory_id: str = Field(min_length=1, max_length=120)
    npc_id: str = Field(min_length=1, max_length=120)
    world_id: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=2000)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source_turn_id: str | None = Field(default=None, max_length=120)
    created_at: datetime = Field(default_factory=utc_now)


class NPCMemoryBundle(LSBaseModel):
    profile: NPCProfile
    relationship: NPCRelationship | None = None
    recent_memories: list[NPCMemoryEntry] = Field(default_factory=list)
    canonical_facts: list[str] = Field(default_factory=list)
