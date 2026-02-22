CREATE TABLE IF NOT EXISTS turns (
    turn_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    raw_player_input TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    resolution_json TEXT NOT NULL,
    narrative_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(world_id),
    FOREIGN KEY (world_character_id) REFERENCES world_characters(world_character_id)
);

CREATE INDEX IF NOT EXISTS idx_turns_world_id_created_at ON turns(world_id, created_at DESC);
