from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .common import LSBaseModel, utc_now


class CharacterAttributes(LSBaseModel):
    strength: int = Field(default=10, ge=1, le=30)
    dexterity: int = Field(default=10, ge=1, le=30)
    intelligence: int = Field(default=10, ge=1, le=30)
    charisma: int = Field(default=10, ge=1, le=30)


class CharacterResources(LSBaseModel):
    hp: int = Field(default=10, ge=0)
    max_hp: int = Field(default=10, ge=1)
    stamina: int = Field(default=10, ge=0)
    max_stamina: int = Field(default=10, ge=1)
    focus: int = Field(default=0, ge=0)
    max_focus: int = Field(default=0, ge=0)


class CharacterTemplateSeed(LSBaseModel):
    template_name: str = Field(min_length=1, max_length=80)
    archetype: str = Field(default="adventurer", min_length=1, max_length=80)
    background: str = Field(default="", max_length=2000)
    attributes: CharacterAttributes = Field(default_factory=CharacterAttributes)


class WorldCharacterSeed(LSBaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    motivation: str = Field(default="", max_length=500)
    template: CharacterTemplateSeed
    starter_location_name: str = Field(default="Start Area", min_length=1, max_length=120)


class CharacterState(LSBaseModel):
    world_character_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=80)
    level: int = Field(default=1, ge=1)
    xp: int = Field(default=0, ge=0)
    location_name: str = Field(default="Unknown", min_length=1, max_length=120)
    attributes: CharacterAttributes = Field(default_factory=CharacterAttributes)
    resources: CharacterResources = Field(default_factory=CharacterResources)
    status_effects: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)
