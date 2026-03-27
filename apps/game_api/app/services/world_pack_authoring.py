from __future__ import annotations

from dataclasses import dataclass
import json

from ls_shared_schemas.world import ScenePointSeed, WorldSeed


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
    scene_points: tuple[ScenePointSeed, ...] = ()


def _generic_marktplatz_scene_points() -> tuple[ScenePointSeed, ...]:
    return (
        ScenePointSeed(
            ref_id="poi-marktplatz-crowd-flow",
            name="Menschenstrom",
            kind="scene_point",
            location_name="Marktplatz",
            scene_zone_id="zone-poi-marktplatz-crowd",
            scene_zone_name="Passantenstrom",
            aliases=["menge", "passanten", "menschen"],
        ),
        ScenePointSeed(
            ref_id="poi-marktplatz-notice-board",
            name="Anschlagtafel",
            kind="scene_point",
            location_name="Marktplatz",
            scene_zone_id="zone-poi-marktplatz-board",
            scene_zone_name="Anschlagbereich",
            aliases=["tafel", "hinweise", "zettel"],
        ),
        ScenePointSeed(
            ref_id="obj-marktplatz-supply-crate",
            name="Vorratskiste",
            kind="container",
            location_name="Marktplatz",
            scene_zone_id="zone-poi-marktplatz-crate",
            scene_zone_name="Kistenbereich",
            aliases=["kiste", "kiste am rand", "truhe"],
        ),
        ScenePointSeed(
            ref_id="obj-marktplatz-discarded-bag",
            name="Liegende Tasche",
            kind="scene_object",
            location_name="Marktplatz",
            scene_zone_id="zone-poi-marktplatz-bag",
            scene_zone_name="Randbereich",
            aliases=["tasche", "beutel", "sack"],
        ),
        ScenePointSeed(
            ref_id="poi-marktplatz-brunnen",
            name="Brunnenanlage",
            kind="scene_point",
            location_name="Marktplatz",
            scene_zone_id="zone-fountain-ring",
            scene_zone_name="Brunnenplatz",
            aliases=["brunnen", "wasserbecken"],
        ),
    )


def _urban_occult_marktplatz_scene_points() -> tuple[ScenePointSeed, ...]:
    return (
        ScenePointSeed(
            ref_id="poi-marktplatz-shadow-dispute",
            name="Streitende Schattenfiguren",
            kind="scene_point",
            location_name="Marktplatz",
            scene_zone_id="zone-fountain-ring",
            scene_zone_name="Brunnenplatz",
            aliases=["schattenfiguren", "streit", "streitende gruppe", "schatten"],
        ),
        ScenePointSeed(
            ref_id="poi-marktplatz-runenspuren",
            name="Verkohlte Runenspuren",
            kind="scene_point",
            location_name="Marktplatz",
            scene_zone_id="zone-fountain-ring",
            scene_zone_name="Brunnenplatz",
            aliases=["runen", "ritualspuren", "sigillen"],
        ),
        ScenePointSeed(
            ref_id="poi-marktplatz-laternenkasten",
            name="Flackernder Laternenkasten",
            kind="scene_object",
            location_name="Marktplatz",
            scene_zone_id="zone-market-edge",
            scene_zone_name="Randgasse",
            aliases=["laterne", "stromkasten", "kabel"],
        ),
        ScenePointSeed(
            ref_id="obj-marktplatz-siegelkoffer",
            name="Versiegelter Instrumentenkoffer",
            kind="container",
            location_name="Marktplatz",
            scene_zone_id="zone-market-edge",
            scene_zone_name="Randgasse",
            aliases=["koffer", "instrumentenkoffer", "versiegelter koffer"],
        ),
    )


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
    scene_points=(
        *_generic_marktplatz_scene_points(),
        *_urban_occult_marktplatz_scene_points(),
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
    scene_points=_generic_marktplatz_scene_points(),
)


def resolve_world_pack_for_seed(world_seed: WorldSeed) -> AuthoredWorldPack:
    pack_id = (world_seed.world_pack_id or "").strip().lower()
    if pack_id == URBAN_OCCULT_WORLD_PACK.pack_id:
        return URBAN_OCCULT_WORLD_PACK
    return GENERIC_STARTER_WORLD_PACK


def initial_story_flags_for_world_seed(world_seed: WorldSeed) -> dict[str, str | int | bool]:
    pack = resolve_world_pack_for_seed(world_seed)
    return dict(pack.starter_story_flags)


def scene_points_for_world_seed(world_seed: WorldSeed) -> list[ScenePointSeed]:
    if world_seed.scene_points:
        return [point.model_copy(deep=True) for point in world_seed.scene_points]
    pack = resolve_world_pack_for_seed(world_seed)
    return [point.model_copy(deep=True) for point in pack.scene_points]


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
