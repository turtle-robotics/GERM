-- PHASE 0 REVIEW FIXTURE ONLY. Not a deployed migration or production adapter.
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA synchronous=FULL;
PRAGMA busy_timeout=3000;
BEGIN;
CREATE TABLE experiments (
 experiment_id INTEGER PRIMARY KEY, name TEXT NOT NULL, plant_profile TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('planned','active','paused','complete')),
 start_time_utc TEXT NOT NULL, end_time_utc TEXT);
CREATE TABLE plants (plant_id INTEGER PRIMARY KEY, experiment_id INTEGER NOT NULL REFERENCES experiments,
 position INTEGER NOT NULL CHECK(position BETWEEN 1 AND 6), species TEXT NOT NULL,
 UNIQUE(experiment_id,position));
CREATE TABLE sensors (sensor_id TEXT PRIMARY KEY, unit TEXT NOT NULL, location TEXT NOT NULL,
 expected_period_s REAL NOT NULL CHECK(expected_period_s>0));
CREATE TABLE sensor_readings (reading_id INTEGER PRIMARY KEY, sensor_id TEXT NOT NULL REFERENCES sensors,
 experiment_id INTEGER REFERENCES experiments, timestamp_utc TEXT NOT NULL, value REAL,
 quality_flag TEXT NOT NULL CHECK(quality_flag IN ('good','stale','suspect','invalid','missing')),
 CHECK(quality_flag NOT IN ('invalid','missing') OR value IS NULL));
CREATE TABLE actuators (actuator_id TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE actuator_events (event_id TEXT PRIMARY KEY, actuator_id TEXT NOT NULL REFERENCES actuators,
 experiment_id INTEGER REFERENCES experiments, timestamp_utc TEXT NOT NULL, requested_state TEXT NOT NULL,
 reported_state TEXT, source TEXT NOT NULL, firmware_confirmed INTEGER NOT NULL CHECK(firmware_confirmed IN (0,1)),
 physically_verified INTEGER NOT NULL DEFAULT 0 CHECK(physically_verified IN (0,1)));
CREATE TABLE images (image_id INTEGER PRIMARY KEY, experiment_id INTEGER REFERENCES experiments,
 plant_id INTEGER REFERENCES plants, file_path TEXT NOT NULL UNIQUE,
 timestamp_utc TEXT NOT NULL, sha256 TEXT NOT NULL CHECK(length(sha256)=64),
 size_bytes INTEGER NOT NULL CHECK(size_bytes>0), width_px INTEGER NOT NULL CHECK(width_px>0),
 height_px INTEGER NOT NULL CHECK(height_px>0), capture_reason TEXT NOT NULL CHECK(capture_reason IN ('manual','scheduled','fault')),
 CHECK(file_path NOT LIKE '/%' AND instr(file_path,'..')=0 AND instr(file_path,':')=0 AND instr(file_path,char(92))=0));
CREATE TABLE ml_inferences (inference_id INTEGER PRIMARY KEY, image_id INTEGER NOT NULL REFERENCES images,
 timestamp_utc TEXT NOT NULL, predicted_class TEXT NOT NULL, confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 model_version TEXT NOT NULL, review_required INTEGER NOT NULL CHECK(review_required IN (0,1)),
 inference_ms REAL NOT NULL CHECK(inference_ms>=0));
CREATE TABLE alerts (alert_id INTEGER PRIMARY KEY, experiment_id INTEGER REFERENCES experiments,
 severity TEXT NOT NULL CHECK(severity IN ('info','warning','critical')), source_type TEXT NOT NULL,
 message TEXT NOT NULL, timestamp_utc TEXT NOT NULL, ack_time_utc TEXT, clear_time_utc TEXT);
CREATE TABLE maintenance_events (maintenance_id INTEGER PRIMARY KEY, experiment_id INTEGER REFERENCES experiments,
 timestamp_utc TEXT NOT NULL, action TEXT NOT NULL, component TEXT NOT NULL, details_json TEXT NOT NULL);
CREATE TABLE system_events (event_id TEXT PRIMARY KEY, experiment_id INTEGER REFERENCES experiments,
 schema_version INTEGER NOT NULL CHECK(schema_version=1), timestamp_utc TEXT NOT NULL,
 event_type TEXT NOT NULL, source TEXT NOT NULL, software_version TEXT NOT NULL, payload_json TEXT NOT NULL);
CREATE INDEX readings_sensor_time ON sensor_readings(sensor_id,timestamp_utc);
CREATE INDEX readings_experiment_time ON sensor_readings(experiment_id,timestamp_utc);
CREATE INDEX actuator_time ON actuator_events(actuator_id,timestamp_utc);
CREATE INDEX images_time ON images(experiment_id,timestamp_utc);
CREATE INDEX inference_image ON ml_inferences(image_id,timestamp_utc);
CREATE INDEX active_alerts ON alerts(clear_time_utc,severity,timestamp_utc);
PRAGMA user_version=1;
COMMIT;
