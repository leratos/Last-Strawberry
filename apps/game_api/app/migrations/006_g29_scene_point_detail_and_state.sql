ALTER TABLE scene_point_discoveries
ADD COLUMN detail_level INTEGER NOT NULL DEFAULT 1;

ALTER TABLE scene_point_discoveries
ADD COLUMN state_json TEXT NOT NULL DEFAULT '{}';
