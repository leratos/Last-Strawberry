from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .character import CharacterState, CharacterTemplateSeed, WorldCharacterSeed
from .common import LSBaseModel, utc_now
from .inventory import InventoryItemInstance
from .npc_memory import NPCProfile


class WorldBootstrapRequest(LSBaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    world_description: str = Field(min_length=10, max_length=4000)
    character_description: str = Field(min_length=10, max_length=3000)
    tone: str = Field(default="adventure", min_length=1, max_length=80)
    difficulty: str = Field(default="normal", min_length=1, max_length=40)
    safety_preferences: list[str] = Field(default_factory=list)


class WorldSeed(LSBaseModel):
    world_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=4000)
    start_location_name: str = Field(min_length=1, max_length=120)
    start_hook: str = Field(min_length=1, max_length=2000)
    factions: list[str] = Field(default_factory=list)
    open_threads: list[str] = Field(default_factory=list)
    starter_npcs: list[NPCProfile] = Field(default_factory=list)
    suggested_character_template: CharacterTemplateSeed
    created_character_seed: WorldCharacterSeed
    starter_inventory: list[InventoryItemInstance] = Field(default_factory=list)


class WorldBootstrapResult(LSBaseModel):
    world_seed: WorldSeed
    initial_narrative: str = Field(min_length=1, max_length=8000)
    player_orientation: list[str] = Field(default_factory=list)


class JournalEntryRecord(LSBaseModel):
    journal_entry_id: str = Field(min_length=1, max_length=120)
    world_id: str = Field(min_length=1, max_length=120)
    entry_type: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=8000)
    created_at: datetime = Field(default_factory=utc_now)


class WorldSessionResponse(LSBaseModel):
    world_id: str = Field(min_length=1, max_length=120)
    user_id: str = Field(min_length=1, max_length=120)
    tone: str = Field(min_length=1, max_length=80)
    difficulty: str = Field(min_length=1, max_length=40)
    world_seed: WorldSeed
    initial_narrative: str = Field(min_length=1, max_length=8000)
    player_orientation: list[str] = Field(default_factory=list)
    character_state: CharacterState
    inventory: list[InventoryItemInstance] = Field(default_factory=list)
    journal: list[JournalEntryRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
