CREATE TABLE IF NOT EXISTS worlds (
    world_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    tone TEXT NOT NULL,
    difficulty TEXT NOT NULL,
    world_seed_json TEXT NOT NULL,
    initial_narrative TEXT NOT NULL,
    player_orientation_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_characters (
    world_character_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    character_state_json TEXT NOT NULL,
    inventory_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

CREATE TABLE IF NOT EXISTS journal_entries (
    journal_entry_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

CREATE INDEX IF NOT EXISTS idx_world_characters_world_id ON world_characters(world_id);
CREATE INDEX IF NOT EXISTS idx_journal_entries_world_id ON journal_entries(world_id, created_at);
