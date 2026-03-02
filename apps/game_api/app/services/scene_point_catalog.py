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


def _scene_point_seed_to_ref(point: ScenePointSeed) -> GameTargetReference:
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
