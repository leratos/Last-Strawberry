CREATE TABLE IF NOT EXISTS world_story_flags (
    world_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    flags_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (world_id, world_character_id)
);
