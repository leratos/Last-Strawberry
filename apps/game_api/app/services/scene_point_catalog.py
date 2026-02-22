from __future__ import annotations

import re

from ls_shared_schemas.game_context import GameTargetReference
from ls_shared_schemas.world import WorldSessionResponse


def build_scene_point_targets_for_location(
    *,
    world: WorldSessionResponse,
    location_name: str,
) -> list[GameTargetReference]:
    """Return deterministic discoverable interaction points for a location."""
    location = (location_name or "").strip()
    if not location:
        return []

    points = _base_points_for_location(location)
    if _looks_urban_occult(world):
        points.extend(_urban_occult_points_for_location(location))

    deduped: dict[str, GameTargetReference] = {}
    for ref in points:
        deduped[ref.ref_id] = ref
    return list(deduped.values())


def _base_points_for_location(location_name: str) -> list[GameTargetReference]:
    slug = _slug(location_name)
    refs = [
        _scene_point_ref(
            point_id=f"poi-{slug}-crowd-flow",
            name="Menschenstrom",
            location_name=location_name,
            scene_zone_id=f"zone-poi-{slug}-crowd",
            scene_zone_name="Passantenstrom",
            aliases=["menge", "passanten", "menschen"],
        ),
        _scene_point_ref(
            point_id=f"poi-{slug}-notice-board",
            name="Anschlagtafel",
            location_name=location_name,
            scene_zone_id=f"zone-poi-{slug}-board",
            scene_zone_name="Anschlagbereich",
            aliases=["tafel", "hinweise", "zettel"],
        ),
    ]
    if slug in {"marktplatz", "market-square"}:
        refs.append(
            _scene_point_ref(
                point_id="poi-marktplatz-brunnen",
                name="Brunnenanlage",
                location_name=location_name,
                scene_zone_id="zone-fountain-ring",
                scene_zone_name="Brunnenplatz",
                aliases=["brunnen", "wasserbecken"],
            )
        )
    return refs


def _urban_occult_points_for_location(location_name: str) -> list[GameTargetReference]:
    slug = _slug(location_name)
    if slug == "marktplatz":
        return [
            _scene_point_ref(
                point_id="poi-marktplatz-runenspuren",
                name="Verkohlte Runenspuren",
                location_name=location_name,
                scene_zone_id="zone-fountain-ring",
                scene_zone_name="Brunnenplatz",
                aliases=["runen", "ritualspuren", "sigillen"],
            ),
            _scene_point_ref(
                point_id="poi-marktplatz-laternenkasten",
                name="Flackernder Laternenkasten",
                location_name=location_name,
                scene_zone_id="zone-market-edge",
                scene_zone_name="Randgasse",
                aliases=["laterne", "stromkasten", "kabel"],
            ),
        ]
    return [
        _scene_point_ref(
            point_id=f"poi-{slug}-arcane-residue",
            name="Arkane Rueckstaende",
            location_name=location_name,
            scene_zone_id=f"zone-poi-{slug}-arcane",
            scene_zone_name="Stoerungsbereich",
            aliases=["magiespuren", "resonanz", "rueckstaende"],
        )
    ]


def _looks_urban_occult(world: WorldSessionResponse) -> bool:
    haystack = " ".join(
        [
            world.world_seed.name,
            world.world_seed.summary,
            world.world_seed.start_hook,
            *world.world_seed.factions,
            *world.world_seed.open_threads,
        ]
    ).lower()
    keywords = (
        "binder",
        "champion",
        "ritual",
        "arkane",
        "magie",
        "beschwoer",
        "beschwör",
        "konklave",
    )
    return any(token in haystack for token in keywords)


def _scene_point_ref(
    *,
    point_id: str,
    name: str,
    location_name: str,
    scene_zone_id: str,
    scene_zone_name: str,
    aliases: list[str],
) -> GameTargetReference:
    return GameTargetReference(
        ref_id=point_id,
        kind="scene_point",
        name=name,
        aliases=aliases,
        source="scene_catalog",
        location_name=location_name,
        scene_zone_id=scene_zone_id,
        scene_zone_name=scene_zone_name,
        distance_band_to_player=None,
    )


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "location"
