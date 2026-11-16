ALTER TABLE experiments ADD COLUMN notes TEXT;
ALTER TABLE plants ADD COLUMN cultivar TEXT;
ALTER TABLE plants ADD COLUMN planting_date TEXT;
ALTER TABLE plants ADD COLUMN status TEXT;
ALTER TABLE sensors ADD COLUMN name TEXT;
ALTER TABLE sensors ADD COLUMN measurement_type TEXT;
ALTER TABLE sensors ADD COLUMN interface TEXT;
ALTER TABLE sensors ADD COLUMN calibration_date TEXT;
ALTER TABLE sensors ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1));
ALTER TABLE sensor_readings ADD COLUMN source_sequence INTEGER CHECK(source_sequence>=0);
ALTER TABLE actuators ADD COLUMN name TEXT;
ALTER TABLE actuators ADD COLUMN type TEXT;
ALTER TABLE actuators ADD COLUMN location TEXT;
ALTER TABLE actuators ADD COLUMN safe_state TEXT;
ALTER TABLE actuators ADD COLUMN active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1));
ALTER TABLE actuator_events ADD COLUMN reason TEXT;
ALTER TABLE actuator_events ADD COLUMN request_id TEXT;
ALTER TABLE actuator_events ADD COLUMN accepted_at_utc TEXT;
ALTER TABLE actuator_events ADD COLUMN acknowledged_at_utc TEXT;
ALTER TABLE images ADD COLUMN lighting_state TEXT;
ALTER TABLE ml_inferences ADD COLUMN review_label TEXT;
ALTER TABLE alerts ADD COLUMN source_id TEXT;
ALTER TABLE alerts ADD COLUMN recommended_action TEXT;
ALTER TABLE maintenance_events ADD COLUMN performed_by TEXT;
ALTER TABLE maintenance_events ADD COLUMN notes TEXT;
ALTER TABLE maintenance_events ADD COLUMN next_due_utc TEXT;
ALTER TABLE system_events ADD COLUMN severity TEXT;
CREATE INDEX inference_image_model ON ml_inferences(image_id,model_version,timestamp_utc);
CREATE INDEX maintenance_component_time ON maintenance_events(component,timestamp_utc);
CREATE INDEX system_event_time ON system_events(timestamp_utc,event_id);
CREATE INDEX actuator_request ON actuator_events(request_id);
CREATE TABLE restart_state (
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), generation INTEGER NOT NULL CHECK(generation>0),
 schema_version INTEGER NOT NULL CHECK(schema_version=1), profile TEXT,
 maintenance INTEGER NOT NULL CHECK(maintenance IN (0,1)),
 estop_latched INTEGER NOT NULL CHECK(estop_latched IN (0,1)),
 restart_required INTEGER NOT NULL CHECK(restart_required=1), updated_at_utc TEXT NOT NULL);
