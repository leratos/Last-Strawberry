from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import LSBaseModel, utc_now


class QuestObjectiveState(LSBaseModel):
    objective_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    status: str = Field(default="pending", min_length=1, max_length=40)
    hint: str | None = Field(default=None, max_length=1000)


class WorldQuestState(LSBaseModel):
    quest_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    status: str = Field(default="active", min_length=1, max_length=40)
    current_stage: str = Field(default="start", min_length=1, max_length=120)
    objectives: list[QuestObjectiveState] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

