CREATE TABLE IF NOT EXISTS world_authoring_audit_log (
    audit_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL,
    world_character_id TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    requested_by TEXT,
    source TEXT,
    request_json TEXT NOT NULL,
    result_json TEXT,
    error_code TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_world_authoring_audit_log_world_created
ON world_authoring_audit_log(world_id, created_at DESC);
