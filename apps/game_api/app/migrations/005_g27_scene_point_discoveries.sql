CREATE TABLE IF NOT EXISTS scene_point_discoveries (
    world_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    location_name TEXT NOT NULL,
    point_ref_id TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (world_id, world_character_id, location_name, point_ref_id)
);

CREATE INDEX IF NOT EXISTS idx_scene_point_discoveries_world_character
ON scene_point_discoveries(world_id, world_character_id, location_name);
