from __future__ import annotations

from ls_shared_schemas.game_context import GameTargetReference
from ls_shared_schemas.world import ScenePointSeed, WorldSessionResponse

from apps.game_api.app.services.world_pack_authoring import scene_points_for_world_seed


def build_scene_point_targets_for_location(
    *,
    world: WorldSessionResponse,
    location_name: str,
) -> list[GameTargetReference]:
    """Return discoverable interaction points for a location from authored world content."""
    location = (location_name or "").strip()
    if not location:
        return []

    authored_points = scene_points_for_world_seed(world.world_seed)
    points = [_scene_point_seed_to_ref(entry) for entry in authored_points if entry.location_name.strip() == location]

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
        _scene_point_ref(
            point_id=f"obj-{slug}-supply-crate",
            name="Vorratskiste",
            kind="container",
            location_name=location_name,
            scene_zone_id=f"zone-poi-{slug}-crate",
            scene_zone_name="Kistenbereich",
            aliases=["kiste", "kiste am rand", "truhe"],
        ),
        _scene_point_ref(
            point_id=f"obj-{slug}-discarded-bag",
            name="Liegende Tasche",
            kind="scene_object",
            location_name=location_name,
            scene_zone_id=f"zone-poi-{slug}-bag",
            scene_zone_name="Randbereich",
            aliases=["tasche", "beutel", "sack"],
        ),
    ]
    if slug in {"marktplatz", "market-square"}:
        refs.append(
            _scene_point_ref(
                point_id="poi-marktplatz-brunnen",
                name="Brunnenanlage",
                kind="scene_point",
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
                point_id="poi-marktplatz-shadow-dispute",
                name="Streitende Schattenfiguren",
                kind="scene_point",
                location_name=location_name,
                scene_zone_id="zone-fountain-ring",
                scene_zone_name="Brunnenplatz",
                aliases=["schattenfiguren", "streit", "streitende gruppe", "schatten"],
            ),
            _scene_point_ref(
                point_id="poi-marktplatz-runenspuren",
                name="Verkohlte Runenspuren",
                kind="scene_point",
                location_name=location_name,
                scene_zone_id="zone-fountain-ring",
                scene_zone_name="Brunnenplatz",
                aliases=["runen", "ritualspuren", "sigillen"],
            ),
            _scene_point_ref(
                point_id="poi-marktplatz-laternenkasten",
                name="Flackernder Laternenkasten",
                kind="scene_object",
                location_name=location_name,
                scene_zone_id="zone-market-edge",
                scene_zone_name="Randgasse",
                aliases=["laterne", "stromkasten", "kabel"],
            ),
            _scene_point_ref(
                point_id="obj-marktplatz-siegelkoffer",
                name="Versiegelter Instrumentenkoffer",
                kind="container",
                location_name=location_name,
                scene_zone_id="zone-market-edge",
                scene_zone_name="Randgasse",
                aliases=["koffer", "instrumentenkoffer", "versiegelter koffer"],
            ),
        ]
    return [
        _scene_point_ref(
            point_id=f"poi-{slug}-arcane-residue",
            name="Arkane Rueckstaende",
            kind="scene_point",
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
    kind: str = "scene_point",
    location_name: str,
    scene_zone_id: str,
    scene_zone_name: str,
    aliases: list[str],
) -> GameTargetReference:
    return GameTargetReference(
        ref_id=point.ref_id,
        kind=point.kind,
        name=point.name,
        aliases=list(point.aliases),
        source="world_pack_seed",
        location_name=point.location_name,
        scene_zone_id=point.scene_zone_id,
        scene_zone_name=point.scene_zone_name,
        distance_band_to_player=None,
    )
