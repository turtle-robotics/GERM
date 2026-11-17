-- M5 correction only: schema version 6 does not implement milestone M6.
ALTER TABLE capture_schedule ADD COLUMN last_observed_utc TEXT;
ALTER TABLE capture_schedule ADD COLUMN clock_fault INTEGER NOT NULL DEFAULT 0 CHECK(clock_fault IN (0,1));
ALTER TABLE capture_schedule ADD COLUMN resume_not_before_utc TEXT;
ALTER TABLE capture_requests ADD COLUMN schedule_generation INTEGER;
CREATE INDEX scheduled_capture_time ON capture_requests(capture_reason,scheduled_at_utc,created_at_utc);
-- Older versions did not persist every tick. Seed conservatively from all durable
-- scheduled claims, including failed/missed/interrupted claims; do not invent ticks.
UPDATE capture_schedule SET last_observed_utc=(
 SELECT MAX(observed) FROM (
  SELECT created_at_utc AS observed FROM capture_requests WHERE capture_reason='scheduled'
  UNION ALL
  SELECT scheduled_at_utc AS observed FROM capture_requests WHERE capture_reason='scheduled'
 ));
