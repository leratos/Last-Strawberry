CREATE TABLE IF NOT EXISTS world_quest_states (
    world_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    quest_id TEXT NOT NULL,
    quest_state_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (world_id, world_character_id, quest_id)
);

CREATE INDEX IF NOT EXISTS idx_world_quest_states_world_character
ON world_quest_states(world_id, world_character_id);
