CREATE TABLE IF NOT EXISTS scene_point_proposals (
    proposal_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    world_character_id TEXT NOT NULL,
    status TEXT NOT NULL,
    scene_point_json TEXT NOT NULL,
    source TEXT,
    requested_by TEXT,
    provider_trace_json TEXT,
    decision_note TEXT,
    reviewed_by TEXT,
    applied_to_world_seed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    reviewed_at TEXT,
    CHECK(status IN ('proposed', 'approved', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_scene_point_proposals_world_status_created
ON scene_point_proposals(world_id, status, created_at DESC);
