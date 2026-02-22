CREATE TABLE IF NOT EXISTS npc_profiles (
    world_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    faction TEXT,
    personality_tags_json TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (world_id, npc_id),
    FOREIGN KEY (world_id) REFERENCES worlds(world_id)
);

CREATE TABLE IF NOT EXISTS npc_relationships (
    world_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    standing INTEGER NOT NULL,
    tags_json TEXT NOT NULL,
    notes TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (world_id, npc_id, world_character_id),
    FOREIGN KEY (world_id, npc_id) REFERENCES npc_profiles(world_id, npc_id),
    FOREIGN KEY (world_character_id) REFERENCES world_characters(world_character_id)
);

CREATE TABLE IF NOT EXISTS npc_memories (
    memory_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    importance REAL NOT NULL,
    tags_json TEXT NOT NULL,
    source_turn_id TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (world_id, npc_id) REFERENCES npc_profiles(world_id, npc_id),
    FOREIGN KEY (world_character_id) REFERENCES world_characters(world_character_id)
);

CREATE INDEX IF NOT EXISTS idx_npc_profiles_world_name
    ON npc_profiles(world_id, name);

CREATE INDEX IF NOT EXISTS idx_npc_relationships_world_character
    ON npc_relationships(world_id, world_character_id);

CREATE INDEX IF NOT EXISTS idx_npc_memories_world_npc_created_at
    ON npc_memories(world_id, npc_id, created_at DESC);
