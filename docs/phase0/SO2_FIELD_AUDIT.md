# SO-2 field audit of reused Phase 0 schema fixture

Source: SO-2 Database Outline, Drive ID `1BYqpePrA7GVw6m5lS_Im-uvxjNZ21uw_`; reviewed during November 15 discovery. Comparison target: `pi_hmi/tests/fixtures/schema_v1.sql` from PR #2. No fixture is promoted to production and no deployed schema is changed by M0.

| Entity | Covered by fixture | Differences / M2 obligation |
| --- | --- | --- |
| experiments | ID/name/start/end/status; fixture adds plant_profile | Add SO-2 notes; review profile ownership and grow-cycle persistence. |
| plants | ID/experiment/species/position | Add cultivar, planting_date, status; position is restricted numeric 1–6 instead of SO-2 text. |
| sensors | ID/unit/location; fixture adds expected_period_s | Fixture uses text ID instead of integer; add name, measurement_type, interface, calibration_date, active. |
| sensor_readings | ID/sensor/experiment/time/value/quality | Add source_sequence; fixture adds missing quality and requires null invalid values. Preserve raw rejected value in diagnostics and document quality mapping. |
| actuators | Text ID/description | Audit integer ID versus stable text key; add name/type/location/safe_state/active. Physical safe-state values await electrical review. |
| actuator_events | ID/actuator/experiment/time/requested/reported/source and explicit ACK/physical flags | Text IDs differ; add reason/request/ACK timestamps and rejection diagnostic linkage without conflating accepted events. |
| images | ID/plant/experiment/time/path/hash/dimensions; size added | Add lighting_state; reconcile manual/scheduled/fault with SO-2 manual/scheduled/alert/dataset. Validate content dimensions/hash/path via adapter. |
| ml_inferences | ID/image/time/model/class/confidence/runtime; review_required added | Add review_label; preserve multiple model results per image, uncertainty threshold and consecutive-abnormal policy. |
| alerts | ID/experiment/time/severity/source_type/message/ack/clear | Add source_id, recommended action and outbox linkage where reviewed. Ack never clears. |
| maintenance_events | ID/experiment/time/action/component/details_json | Reconcile component_id name/type; add performed_by, notes, next_due_utc. SO-2 relationship mentions components but has no components table definition: track dictionary decision. |
| system_events | Text ID/experiment/time/type/source/version/payload/schema version | Reconcile SO-2 system_event_id/severity/details with event envelope. Validate JSON/time; do not silently drop source fields. |

## Indexes and aggregate records

Fixture covers sensor/time, experiment/time, actuator/time, image experiment/time and active alert queries. Its inference index is image/time, while SO-2 explicitly recommends image/model_version. Maintenance component/time index is missing. M2 must implement/test those indexes and bounded HMI queries, and review whether both inference indexes are useful.

SR-DAT-03 complete scheduled operating snapshots require a reviewed materialized record or deterministic as-of join across profile, air/RH/electronics/water/door, pump/light, alarms, maintenance and available ML. Merely populating eleven tables is insufficient. Snapshot/profile/restart/outbox structures are additional reviewed needs, not already implemented schema.

SO-5 canonical proposed DB path is `/var/lib/germ/germ.db`. PR #2's `/var/lib/germ/germ.sqlite3` suggestion is superseded in M0 documents; neither is a currently configured production adapter. M2 must freeze configuration and write ownership before migration implementation. Foreign keys per connection, WAL, synchronous FULL, short writes, backup-before-upgrade and parameterized queries remain required. The fixture's 3000ms busy timeout is a test value pending target performance review.
