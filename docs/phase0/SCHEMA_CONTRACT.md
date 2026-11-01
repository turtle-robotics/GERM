# Review schema and migration contract

The existing INTEGRATION.md names eleven SO-2 entities and repository signatures. tests/fixtures/schema_v1.sql is a proposed initial schema with all eleven entities, constraints and six query indexes; tests/fixtures/seed.sql supplies synthetic data. Neither is a production migration. There is no old deployed schema to upgrade. Empty→v1 is executable; prior-version migration and production rollback are pending Phase 2 review.

## Data dictionary

| Entity | Keys and fields | Consumer |
| --- | --- | --- |
| experiments | experiment_id PK, name, plant_profile, status planned/active/paused/complete, start_time_utc, end_time_utc nullable | Settings, experiment queries and all evidence linkage |
| plants | plant_id PK, experiment_id FK, unique position 1..6 per experiment, species | Plant and image linkage |
| sensors | sensor_id PK, unit, location, expected_period_s>0 | Current values, validation and trends |
| sensor_readings | reading_id PK, sensor_id FK, experiment_id nullable FK, timestamp_utc, value nullable, quality_flag good/stale/suspect/invalid/missing | Trends and event logger; invalid/missing must be null |
| actuators | actuator_id PK, description | Control/event dictionary |
| actuator_events | event_id text PK, actuator_id FK, experiment_id nullable FK, timestamp_utc, requested_state text, reported_state nullable text, source, firmware_confirmed, physically_verified | Controls, diagnostics and durability |
| images | image_id PK, experiment_id/plant_id nullable FK, relative file_path unique, timestamp_utc, sha256 length 64, size_bytes, width_px, height_px, capture_reason manual/scheduled/fault | Capture history and inference linkage |
| ml_inferences | inference_id PK, image_id FK, timestamp_utc, predicted_class, confidence 0..1, model_version, review_required bool, inference_ms>=0 | Latest result and ML audit |
| alerts | alert_id PK, experiment_id nullable FK, severity info/warning/critical, source_type, message, timestamp_utc, ack_time_utc nullable, clear_time_utc nullable | Active/history and acknowledgement |
| maintenance_events | maintenance_id PK, experiment_id nullable FK, timestamp_utc, action, component, details_json | Maintenance history |
| system_events | event_id text PK, experiment_id nullable FK, schema_version=1, timestamp_utc, event_type, source, software_version, payload_json | State, storage, startup/recovery and remote unsent-alarm envelopes |

All timestamps must be validated UTC ISO-8601 with explicit offset by the future adapter; SQL fixture only declares text, not a complete timestamp/JSON validator. SHA-256 hex and image-content dimensions likewise require adapter checks. Requested/reported fields serialize primitive/array/object state consistently (JSON in production proposal). No JPEG BLOBs. Raw invalid sensor values should go in diagnostic event payloads; invalid reading.value remains null.

## Required record coverage

SR-DAT-03 timestamp/profile uses experiment linkage; growth-zone temperature/RH/electronics temperature, water-level and door state use sensors/readings; pump/light use actuator events; alarms and maintenance use alert/maintenance rows and state-transition snapshots. ML label/confidence uses inference→image→experiment. Planned logger must produce a coherent scheduled snapshot or documented join/as-of policy, including null values with quality for missing sensors. The fixture does not implement that logger or claim completeness. A materialized snapshot/export schema is a Phase 2 review decision.

The repository boundary alone owns migration application and writes. Migration versions increase via user_version and must be applied transactionally once with a consistent backup before upgrade. Use foreign_keys=ON per connection, WAL, synchronous=FULL, busy_timeout=3000 ms in this fixture; production timeout requires performance review. Parameterized SQL and short writes are mandatory. Indexes cover sensor/time, experiment/time, actuator/time, image/experiment/time, inference/image/time, active alerts. Proposed database location /var/lib/germ/germ.sqlite3 is not consumed by the current application.

Backup fixtures use sqlite3.Connection.backup into a separate database and compare persisted rows plus integrity_check after reopen. They do not validate a production backup scheduler, image archive, unclean power interruption or a prior-schema upgrade. Phase 2 must reconcile the full external SO-2 design, approve fields and relationship policies, and add production adapter/migration tests before replacing DatabaseUnavailable.
