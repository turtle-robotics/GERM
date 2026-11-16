ALTER TABLE system_events ADD COLUMN envelope_json TEXT;
ALTER TABLE actuator_events ADD COLUMN system_event_id TEXT REFERENCES system_events(event_id);
ALTER TABLE maintenance_events ADD COLUMN system_event_id TEXT REFERENCES system_events(event_id);
ALTER TABLE sensor_readings ADD COLUMN system_event_id TEXT REFERENCES system_events(event_id);
CREATE UNIQUE INDEX maintenance_system_event ON maintenance_events(system_event_id);
CREATE UNIQUE INDEX reading_system_event ON sensor_readings(system_event_id);
CREATE INDEX actuator_system_event ON actuator_events(system_event_id);
