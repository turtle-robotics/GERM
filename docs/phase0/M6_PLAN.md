# M6 host-only plan — Task 131 history and export

2026-11-16. **HOST-ONLY IMPLEMENTATION AUTHORIZED** by the [final M5 review](M5_FINAL_REVIEW.md) at `2d73aebb88378ce46ac67859e91ad90b75593ad2`. This remains the controlling plan for `codex/m6-history-export`, with a separate PR above `codex/m5-camera-ml`; preserve the complete unmerged dependency stack. Use existing M2 repository, M3 envelopes/outbox and M4/M5 experiment/image/model identities. Requirements remain `M0-provisional-2026-11-15`; controlled release, retention, production authentication, real camera/model and physical acceptance remain unresolved. Implementation and evidence are described in [M6_IMPLEMENTATION.md](M6_IMPLEMENTATION.md).

## Read-only browsing and repository contracts

| Resource | Existing source / provenance | Filters / stable order |
| --- | --- | --- |
| Experiments / cycles | experiments, grow_cycles, stored profile snapshot | Experiment, status/date; created/start UTC + stable PK |
| Sensor history | sensor_readings joined to sensors dictionary | Experiment, half-open UTC range, sensor, quality; timestamp_utc + reading_id |
| Images | images, capture_requests and schedule generation | Experiment, plant/date/reason/source; timestamp_utc + image_id |
| Inference | ml_inferences, ml_jobs, model_manifests and policy snapshot | Experiment/plant/date/model/result; timestamp_utc + inference_id |
| Actuator outcomes | actuator_events and linked system event | Experiment/date/actuator/source/ACK state; timestamp_utc + event_id |
| Maintenance | maintenance_events, system_events | Experiment/date/component/action; timestamp_utc + maintenance_id |
| Events / faults | system_events canonical envelopes; media_outbox status separately | Experiment/date/event_type/source; timestamp_utc + event_id |

Introduce parameterized repository queries and read-only GET history endpoints only after the gate. Reject unsupported filters/timezones/invalid ranges/types. Default page size 100, hard maximum 500, validated keyset cursors bound to resource/filter/order and an initial PK high-water. Equal timestamps require the PK tiebreaker; new inserts cannot shift an offset. Stable ordering is not a promise of an immutable multi-request view of mutable ack/status fields: expose retrieval/as-of bounds honestly. Point-in-time consistency belongs to an export snapshot. Preserve unknown experiment/plant/model/source/legacy metadata as null/unknown, rather than dropping or guessing rows. Rejections remain diagnostic events, not accepted actuator history. Review query plans and add only justified indexes; no hardware or command-gateway mutation path.

## CSV format and injection handling

Each entity has a versioned UTF-8 CSV schema using the standard CSV writer, documented quoting/newlines and explicit UTC ISO-8601 `_utc` columns. Include units from the snapshotted sensor dictionary, quality flags, nullable values, requested/reported/ACK/physical distinctions, experiment/plant/profile/model/policy/hash/source linkage and durable event/outbox status. Confidence is labelled confidence, not accuracy. Missing/invalid numeric sensor values are empty with their quality/reason, never substituted zeros.

Treat user/model/source text as untrusted spreadsheet input. Neutralize formula prefixes (`=`, `+`, `-`, `@`, tabs/CR/leading whitespace/control-character variants) with a documented text escape; keep verified typed numeric negatives numeric. Test Unicode/normalization cases and embedded delimiters/quotes/newlines. Record the escape policy/schema version in the manifest and retain canonical raw text/JSON provenance separately so safe CSV does not silently change the source record. UTF-8 is the default; a BOM option, if needed, must be explicit and tested.

## Consistent exports while writers continue

Create an explicitly scoped host export job and consistent SQLite backup snapshot through the existing M2 backup API. Read the completed snapshot through read-only/query-only connections; do not hold the application control lock or a long live writer transaction while producing files. All tables/filter joins, model manifests and pending/committed outbox state come from that same snapshot. Include snapshot creation UTC, source schema/migration versions, software/tested SHA, selected filters, row counts, ordering and table hashes. Volatile queued events are not durable history; any separately observed live queue count must be labelled as outside the snapshot and cannot claim a common point in time.

Exports must not mutate source history or invoke the gateway. An export-start POST may create only request-owned artifacts/job state and retain the existing host-only authorizer/token; all production POST restrictions remain. Read-only download endpoints expose only completed, verified owned artifacts. Interrupted jobs never appear complete; retries use job identity and separate staging paths. No code for those endpoints is implemented in this plan.

## JPEG archive/download

Propose ZIP64 containing `manifest.json`, versioned `tables/*.csv`, canonical provenance JSON and `images/<experiment>/<image-id>_<hash>.jpg`. Use generated safe POSIX member names, not raw notes/user filenames; reject traversal, absolute paths, links and member collisions. No executable/model weights are bundled by implication. Stage the archive, verify every member/hash/count, then publish exclusively under an opaque job ID. Record the final archive SHA-256 outside the archive to avoid self-referential hashes.

Image rows are selected from the DB snapshot; bytes must be read under the configured image root and checked against that snapshot's size/SHA/dimensions. The filesystem is not transactionally snapshotted with SQLite. If a file is missing, corrupt or changes while reading, record the exact image ID/expected hash/error and omit invalid JPEG bytes; return `complete_with_errors`, or fail the entire archive in an explicit strict mode. Never substitute thumbnails/placeholders or silently call a partial archive complete. Verify that the bytes actually archived match the manifest. Preserve all source files and records. Export artifacts and failed stages are retained pending an explicit cleanup policy; no automated retention, pruning or deletion.

## Planned implementation increments and tests

1. Freeze read/export schema and null/legacy/provenance semantics; implement bounded repository queries with keyset cursors and meaningful query-plan tests. Test empty/large (including >=100,000-row) fixtures, equal timestamps, new writes between pages, invalid cursors/filter changes and database failures.
2. Implement read-only history UI/API for each resource, filters and bounded pages. Preserve alarm acknowledgement/control UI separation. Browser tests cover empty/error/loading states, keyboard/touch navigation, long/Unicode text and unavailable/corrupt image links; no claim of novice acceptance from scripts alone.
3. Implement snapshot-backed CSV jobs; test simultaneous inserts/updates and stable exported row counts/joins, UTF-8/newlines/quoting, null/unit/quality fields, formula-injection cases, disk-full/DB/backup failure and interrupted jobs. Bound memory via streaming/chunks and explicit disk/job quotas; quotas do not authorize deletion.
4. Implement archive manifests/download verification; test mixed valid/missing/corrupt JPEGs, changing files, SHA/byte/dimension mismatch, ZIP path/member safety, archive hashes, strict/partial status and repeated/concurrent requests.
5. Publish separate M6 PR with test logs/source hashes/browser evidence, requirement traceability and remaining dependencies. Run all prior host/C++/browser suites. Return for review; no merge, production deployment, real camera/model/hardware, firmware, Gantt or retention change.

Traceability: Task 131 history/filtering; SR-DAT-01 local/offline store/export; SR-DAT-02 CSV+images while preserving the unresolved retention conflict; SR-DAT-03 explicit profile/timestamps/quality/operating provenance; SR-ML-03 versioned image/result linkage; SR-UI-02 honest missing/error states. Full endurance/completeness/latency, physical and novice acceptance remain separate gates.
