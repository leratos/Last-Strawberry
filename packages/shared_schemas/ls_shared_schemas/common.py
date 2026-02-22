from __future__ import annotations

from datetime import datetime, UTC

from pydantic import BaseModel, ConfigDict


class LSBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def utc_now() -> datetime:
    return datetime.now(UTC)
