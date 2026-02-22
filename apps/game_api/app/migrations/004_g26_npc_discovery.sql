CREATE TABLE IF NOT EXISTS npc_discoveries (
    world_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    npc_id TEXT NOT NULL,
    discovered_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (world_id, world_character_id, npc_id)
);

CREATE INDEX IF NOT EXISTS idx_npc_discoveries_world_character
ON npc_discoveries(world_id, world_character_id);
