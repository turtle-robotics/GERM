CREATE INDEX history_events_experiment_time ON system_events(experiment_id,timestamp_utc,event_id);
CREATE INDEX history_events_type_time ON system_events(event_type,timestamp_utc,event_id);
CREATE INDEX history_maintenance_experiment_time ON maintenance_events(experiment_id,timestamp_utc,maintenance_id);
CREATE INDEX history_actuator_experiment_time ON actuator_events(experiment_id,timestamp_utc,event_id);
CREATE TABLE export_jobs (
 request_id TEXT PRIMARY KEY, definition_json TEXT NOT NULL, status TEXT NOT NULL
 CHECK(status IN ('queued','running','complete','complete_with_errors','failed','interrupted')),
 attempt INTEGER NOT NULL, created_at_utc TEXT NOT NULL, updated_at_utc TEXT NOT NULL,
 result_json TEXT, error TEXT);
