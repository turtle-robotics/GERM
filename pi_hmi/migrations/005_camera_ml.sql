CREATE TABLE capture_requests (
 request_id TEXT PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments,
 plant_id INTEGER REFERENCES plants, capture_reason TEXT NOT NULL CHECK(capture_reason IN ('manual','scheduled','fault')),
 scheduled_at_utc TEXT, created_at_utc TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('claimed','prepared','indexed','failed','interrupted','needs_review','missed')),
 metadata_json TEXT, image_id INTEGER UNIQUE REFERENCES images, error TEXT);
ALTER TABLE images ADD COLUMN capture_request_id TEXT REFERENCES capture_requests(request_id);
ALTER TABLE images ADD COLUMN source TEXT;
CREATE UNIQUE INDEX image_capture_request ON images(capture_request_id);
CREATE INDEX capture_status_time ON capture_requests(status,created_at_utc);
CREATE TABLE capture_schedule (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation INTEGER NOT NULL CHECK(generation>0),
 enabled INTEGER NOT NULL CHECK(enabled IN (0,1)), interval_s INTEGER NOT NULL CHECK(interval_s BETWEEN 60 AND 86400),
 anchor_utc TEXT NOT NULL);
CREATE TABLE model_manifests (
 manifest_sha256 TEXT PRIMARY KEY, model_id TEXT NOT NULL, model_version TEXT NOT NULL,
 artifact_sha256 TEXT NOT NULL, manifest_json TEXT NOT NULL, scope TEXT NOT NULL);
CREATE TABLE ml_jobs (
 job_seq INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT NOT NULL UNIQUE,
 image_id INTEGER NOT NULL REFERENCES images, manifest_sha256 TEXT NOT NULL REFERENCES model_manifests,
 policy_sha256 TEXT NOT NULL, policy_json TEXT NOT NULL, created_at_utc TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('running','completed','error','timed_out','interrupted')),
 inference_id INTEGER UNIQUE REFERENCES ml_inferences, error TEXT,
 UNIQUE(image_id,manifest_sha256,policy_sha256));
ALTER TABLE ml_inferences ADD COLUMN request_id TEXT REFERENCES ml_jobs(request_id);
ALTER TABLE ml_inferences ADD COLUMN manifest_sha256 TEXT REFERENCES model_manifests;
ALTER TABLE ml_inferences ADD COLUMN raw_label TEXT;
ALTER TABLE ml_inferences ADD COLUMN scores_json TEXT;
ALTER TABLE ml_inferences ADD COLUMN assessment TEXT;
ALTER TABLE ml_inferences ADD COLUMN abnormal_streak INTEGER;
ALTER TABLE ml_inferences ADD COLUMN alert_eligible INTEGER;
ALTER TABLE ml_inferences ADD COLUMN scope TEXT;
CREATE UNIQUE INDEX inference_request ON ml_inferences(request_id);
CREATE INDEX ml_job_model_status ON ml_jobs(manifest_sha256,status,job_seq);
CREATE TABLE media_outbox (
 event_id TEXT PRIMARY KEY, event_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('pending','committed')),
 capture_request_id TEXT UNIQUE REFERENCES capture_requests(request_id),
 ml_request_id TEXT UNIQUE REFERENCES ml_jobs(request_id));
