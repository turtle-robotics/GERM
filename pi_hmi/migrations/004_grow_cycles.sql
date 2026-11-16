CREATE TABLE grow_profiles (
 profile_id TEXT PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
 definition_json TEXT NOT NULL, approval_status TEXT NOT NULL);
INSERT INTO grow_profiles VALUES('basil','Basil',1,'{"timings":null,"scope":"host-only"}','timings_unapproved');
INSERT INTO grow_profiles VALUES('spearmint','Spearmint',1,'{"timings":null,"scope":"host-only"}','timings_unapproved');
CREATE TABLE grow_cycles (
 cycle_id TEXT PRIMARY KEY, experiment_id INTEGER NOT NULL UNIQUE REFERENCES experiments,
 profile_id TEXT NOT NULL REFERENCES grow_profiles, profile_snapshot_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('paused','running','complete')),
 generation INTEGER NOT NULL CHECK(generation>0), created_at_utc TEXT NOT NULL,
 started_at_utc TEXT, ended_at_utc TEXT);
CREATE UNIQUE INDEX one_open_grow_cycle ON grow_cycles((1)) WHERE status!='complete';
CREATE TABLE grow_schedules (
 schedule_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES grow_cycles,
 target TEXT NOT NULL CHECK(target IN ('lighting','pump')), definition_json TEXT NOT NULL,
 UNIQUE(cycle_id,target));
CREATE INDEX grow_schedule_cycle ON grow_schedules(cycle_id,target);
CREATE TABLE schedule_runs (
 occurrence_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL REFERENCES grow_cycles,
 schedule_id TEXT NOT NULL REFERENCES grow_schedules, generation INTEGER NOT NULL,
 scheduled_at_utc TEXT NOT NULL, command TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('claimed','inhibited','acknowledged','unavailable','missed','uncertain')),
 result_json TEXT, created_at_utc TEXT NOT NULL, definition_snapshot_json TEXT NOT NULL);
CREATE INDEX schedule_run_cycle_time ON schedule_runs(cycle_id,scheduled_at_utc);
