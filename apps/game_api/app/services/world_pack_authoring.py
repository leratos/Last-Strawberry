from __future__ import annotations

from dataclasses import dataclass

from ls_shared_schemas.world import WorldSeed


@dataclass(frozen=True)
class AuthoredWorldPack:
    pack_id: str
    version: str
    display_name: str
    genre: str
    starter_story_flags: dict[str, str | int | bool]


URBAN_OCCULT_WORLD_PACK = AuthoredWorldPack(
    pack_id="worldpack-urban-occult-fuyora-market-v1",
    version="1.0.0",
    display_name="Fuyora Marktplatz - Ritualspuren (Urban Occult)",
    genre="urban_occult_investigation",
    starter_story_flags={
        "ritual_scene_known": False,
        "kael_interviewed": False,
        "supply_crate_inspected": False,
        "mira_report_completed": False,
        "ritual_leads_quest_completed": False,
        "occult_heat_level": 1,
    },
)

GENERIC_STARTER_WORLD_PACK = AuthoredWorldPack(
    pack_id="worldpack-generic-starter-v1",
    version="1.0.0",
    display_name="Generische Starterwelt",
    genre="generic_adventure",
    starter_story_flags={
        "starter_world_initialized": True,
    },
)


def resolve_world_pack_for_seed(world_seed: WorldSeed) -> AuthoredWorldPack:
    pack_id = (world_seed.world_pack_id or "").strip().lower()
    if pack_id == URBAN_OCCULT_WORLD_PACK.pack_id:
        return URBAN_OCCULT_WORLD_PACK
    return GENERIC_STARTER_WORLD_PACK


def initial_story_flags_for_world_seed(world_seed: WorldSeed) -> dict[str, str | int | bool]:
    pack = resolve_world_pack_for_seed(world_seed)
    return dict(pack.starter_story_flags)


def build_world_pack_context(world_seed: WorldSeed) -> dict[str, str]:
    pack = resolve_world_pack_for_seed(world_seed)
    return {
        "pack_id": pack.pack_id,
        "version": pack.version,
        "display_name": pack.display_name,
        "genre": pack.genre,
    }
