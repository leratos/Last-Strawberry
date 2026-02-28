from __future__ import annotations

from dataclasses import dataclass
import json

from ls_shared_schemas.world import WorldSeed


@dataclass(frozen=True)
class AuthoredWorldPack:
    pack_id: str
    version: str
    display_name: str
    genre: str
    starter_story_flags: dict[str, str | int | bool]
    quest_chain_ids: tuple[str, ...] = ()
    quest_entry_rule: str = ""
    quest_exit_rule: str = ""
    quest_reentry_rule: str = ""
    discovery_entry_rule: str = ""


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
        "urban_occult_chain_stage": "starter_active",
        "urban_occult_followup_entry_open": False,
        "urban_occult_followup_exit_open": False,
        "urban_occult_reentry_enabled": False,
    },
    quest_chain_ids=(
        "quest-urban-occult-market-ritual-leads",
        "quest-urban-occult-resonance-followup",
    ),
    quest_entry_rule=(
        "Starterquest ist bei Weltstart aktiv. Folgequest wird nach Starter-Abschluss via quest_unlocked freigeschaltet."
    ),
    quest_exit_rule=(
        "Quest gilt als abgeschlossen, wenn alle Objectives completed sind und Stage auf completed gesetzt ist."
    ),
    quest_reentry_rule=(
        "Nach Followup-Abschluss bleibt die Welt offen fuer neue authored oder spaeter dynamische Questketten (Reentry)."
    ),
    discovery_entry_rule=(
        "Neue NPCs/Interaktionspunkte sind initial verborgen und werden erst durch Discovery (INSPECT/Umsehen) sichtbar."
    ),
)

GENERIC_STARTER_WORLD_PACK = AuthoredWorldPack(
    pack_id="worldpack-generic-starter-v1",
    version="1.0.0",
    display_name="Generische Starterwelt",
    genre="generic_adventure",
    starter_story_flags={
        "starter_world_initialized": True,
    },
    quest_chain_ids=(),
    quest_entry_rule="Keine feste Questkette im Generic-Starter.",
    quest_exit_rule="N/A",
    quest_reentry_rule="N/A",
    discovery_entry_rule="Discovery optional, ohne feste Kettenregeln.",
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
        "quest_chain_ids_csv": ",".join(pack.quest_chain_ids),
        "quest_chain_ids_json": json.dumps(list(pack.quest_chain_ids), ensure_ascii=True),
        "quest_entry_rule": pack.quest_entry_rule,
        "quest_exit_rule": pack.quest_exit_rule,
        "quest_reentry_rule": pack.quest_reentry_rule,
        "discovery_entry_rule": pack.discovery_entry_rule,
    }
