from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TurnRequest(BaseModel):
    world_id: int = Field(gt=0)
    player_id: int = Field(gt=0)
    player_command: str = Field(min_length=1)
    world_name: str = Field(default="default_world")
    player_name: str = Field(default="player")
    npc_context: str = Field(default="No NPCs currently present.")
    recent_events: list[str] = Field(default_factory=list)


class TurnResponse(BaseModel):
    narrative: str
    extracted_commands: list[dict[str, Any]]
    provider: str
    models: dict[str, str]
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    provider: str
    configured_models: dict[str, str]
