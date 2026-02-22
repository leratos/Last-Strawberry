from __future__ import annotations

from enum import Enum

from pydantic import Field

from .common import LSBaseModel


class ItemUseMode(str, Enum):
    inspect = "inspect"
    use = "use"
    equip = "equip"
    consume = "consume"
    activate = "activate"


class ItemEffect(LSBaseModel):
    effect_type: str = Field(min_length=1, max_length=80)
    stat: str | None = Field(default=None, max_length=80)
    amount: int | float | None = None
    duration_turns: int | None = Field(default=None, ge=1)


class InventoryItemInstance(LSBaseModel):
    inventory_item_id: str = Field(min_length=1, max_length=120)
    item_def_id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="misc", min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    quantity: int = Field(default=1, ge=0)
    stackable: bool = True
    equipped: bool = False
    use_modes: list[ItemUseMode] = Field(default_factory=lambda: [ItemUseMode.inspect])
    effects: list[ItemEffect] = Field(default_factory=list)

    def supports(self, mode: ItemUseMode) -> bool:
        return mode in self.use_modes
