CREATE TABLE storage_jobs (
 request_id TEXT PRIMARY KEY, definition_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('queued','running','complete','incomplete','failed','interrupted')),
 attempt INTEGER NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
 result_json TEXT, error TEXT);
