from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import Field

from .character import CharacterState
from .common import LSBaseModel, utc_now
from .inventory import InventoryItemInstance


class ActionType(str, Enum):
    move = "MOVE"
    inspect = "INSPECT"
    talk = "TALK"
    attack = "ATTACK"
    use_item = "USE_ITEM"
    skill_check = "SKILL_CHECK"
    clarify = "CLARIFY"


class TurnIntentAction(LSBaseModel):
    action_type: ActionType
    target_ref: str | None = Field(default=None, max_length=120)
    destination: str | None = Field(default=None, max_length=120)
    item_ref: str | None = Field(default=None, max_length=120)
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)


class TurnIntent(LSBaseModel):
    world_id: str = Field(min_length=1, max_length=120)
    world_character_id: str = Field(min_length=1, max_length=120)
    raw_player_input: str = Field(min_length=1, max_length=2000)
    actions: list[TurnIntentAction] = Field(default_factory=list)
    analysis_notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class TurnSystemEvent(LSBaseModel):
    code: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=1000)
    severity: str = Field(default="info", pattern="^(info|warning|error)$")


class StateDelta(LSBaseModel):
    location_changed_to: str | None = Field(default=None, max_length=120)
    hp_delta: int = 0
    stamina_delta: int = 0
    focus_delta: int = 0
    inventory_consumed: list[dict[str, str | int]] = Field(default_factory=list)
    inventory_gained: list[dict[str, str | int]] = Field(default_factory=list)
    status_added: list[str] = Field(default_factory=list)
    status_removed: list[str] = Field(default_factory=list)
    relationship_changes: list[dict[str, str | int]] = Field(default_factory=list)


class TurnResolution(LSBaseModel):
    world_id: str = Field(min_length=1, max_length=120)
    world_character_id: str = Field(min_length=1, max_length=120)
    applied_actions: list[TurnIntentAction] = Field(default_factory=list)
    rejected_actions: list[TurnIntentAction] = Field(default_factory=list)
    system_events: list[TurnSystemEvent] = Field(default_factory=list)
    state_delta: StateDelta = Field(default_factory=StateDelta)
    resulting_character_state: CharacterState
    resulting_inventory: list[InventoryItemInstance] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class NarrativeEnvelope(LSBaseModel):
    world_id: str = Field(min_length=1, max_length=120)
    world_character_id: str = Field(min_length=1, max_length=120)
    narrative: str = Field(min_length=1, max_length=8000)
    actionable_options: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
