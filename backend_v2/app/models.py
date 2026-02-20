from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field


class TurnRequest(BaseModel):
    world_id: int = Field(gt=0)
    player_id: int = Field(gt=0)
    player_command: str = Field(min_length=1, max_length=2000)
    world_name: str = Field(default="default_world", max_length=120)
    player_name: str = Field(default="player", max_length=64)
    npc_context: str = Field(default="No NPCs currently present.", max_length=4000)
    recent_events: list[Annotated[str, Field(max_length=600)]] = Field(default_factory=list, max_length=20)
    memory_context: list[Annotated[str, Field(max_length=600)]] = Field(default_factory=list, max_length=20)


class LoginRequest(BaseModel):
    user_id: int = Field(gt=0)
    username: str = Field(min_length=1, max_length=64)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int


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


class WorldCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)


class WorldResponse(BaseModel):
    id: int
    owner_id: int
    name: str
    description: str
    created_at: datetime


class TurnRecordResponse(BaseModel):
    id: int
    world_id: int
    player_id: int
    player_command: str
    narrative: str
    extracted_commands: list[dict[str, Any]]
    provider: str
    analysis_model: str
    narrative_model: str
    created_at: datetime


class MemoryItemResponse(BaseModel):
    id: int
    world_id: int
    memory_type: str
    content: str
    importance: float
    source_turn_id: int | None
    created_at: datetime
    updated_at: datetime
