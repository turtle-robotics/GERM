# Proposed milestones for review

This plan is part of Phase 0 discovery. No implementation milestone is approved or started by this document. Sequence is inferred from technical dependencies, not invented Gantt predecessor data. Existing dates/statuses remain untouched. The November deadlines for 119/120/121/128 have elapsed or overlap; obtain a recovery schedule after scope review instead of silently moving dates.

After approval, use `codex/<milestone-name>` feature branches and one reviewable PR per functional increment. Preserve all untracked root files and existing branches. Reuse a suitable checkout; do not reset or overwrite this working tree to obtain current main. Review existing PRs before merging/cherry-picking. Each milestone must include configuration/deployment impact, compatibility, exact test results, limitations, and criterion-linked evidence. A PR or host test pass does not close hardware acceptance.

## M0 — Reconcile the baseline and shared contract review

- Tasks: 119 and 128. Sources: Phase 0 brief, SO-2/3/4/5 and SR-UI-01/02/03.
- Files: reuse PR #2 `docs/phase0/*`, `ASSET_INVENTORY.md`, tests/fixtures, `test_phase0.py`, sample builder and `.github/workflows/phase0-host.yml`; current main `pi_hmi/sim/run_sim.py`; PR #3 firmware/HMI files; this discovery package.
- Interfaces: serial protocol 2, seven-screen/API field/error catalog, repository and ML signatures, sensor quality, command/request/ACK/physical state, event envelope and provisional schema. Existing callers remain compatible; new fields should be additive unless a documented requirement forces change.
- Approach: pin latest main and both PR heads; reconcile pin/PWM/firmware differences against deployed source and electrical mapping. Update simulator/fixtures for the selected baseline rather than accepting conflicting fan behavior. Audit fixture SQL field-by-field against SO-2 and complete required Home/API checklist. Record each unresolved contract as proposed/unavailable. Confirm SR release/version and storage retention conflict.
- Tests: rerun existing integration plus 24 contract checks on the reconciled branch; compare API endpoint catalog and synthetic schema; firmware C++ harness in a compiler-equipped environment/CI; read-only target smoke and source hashes. A simulator is explicit synthetic data, never evidence of installed sensors.
- Done/evidence: reviewed baseline commit set, source/ownership map, full seven-screen checklist, fixture catalog, logs/environment and decisions D1–D8 resolved or scoped with downstream restrictions. Baseline Gate review recorded. No schema fixture labeled production.
- Hardware/risk: no actuation required. Electrical signal mapping and controlled SR release require external review. Physical acceptance stays open if hardware remains unavailable.

## M1 — Authoritative state, command permission and sensor policy

- Tasks: 12/120; groundwork for 129/130. SR-SAF-03/10, SR-AUT-02; supporting SR-SAF-01/02/07, SR-WAT-03 and SR-ENV-01/02/03.
- Files: proposed `pi_hmi/services/state_service.py`, `sensor_policy.py`, state/fault tests; integrate existing app/dashboard/serial/readers and firmware service without creating competing device owners.
- Interfaces: one transition/permission boundary consumes controller feedback, per-sensor quality, door/leak/water-level/E-stop, profile, maintenance and recovery; returns explicit allowed/rejected reason. Every actuator-affecting route, automatic job, legacy helper and firmware-mode/upload path must be covered. Requested, accepted, ACK and physically verified fields remain distinct.
- Approach: implement STARTUP CHECK, NORMAL, WARNING, DEGRADED, MAINTENANCE, SAFE STOP and E STOP with reviewed per-actuator policy. Unknown required interlocks inhibit pump. Reset/condition clearance never restarts equipment. Safe-off requests stay available under defined degraded policies. Use monotonic deadlines and configurable per-sensor expected periods; reject nonfinite, impossible and future readings. Emit immutable transition/command events through an injected sink so missing optional storage cannot authorize unsafe behavior or block control.
- Tests: deterministic clock, all state transitions and prohibited edges; <=two-period fault detection; maintenance automatic-start rejection and exact persistent banner; confirmed exit and safe manual test; controller loss, late/mismatched ACK, exception, concurrent requests, stale confirmations and explicit restart. Verify rejected commands make zero hardware writes.
- Done/evidence: Safety Software Review of transition/permission/sensor tables and passing injected-fault tests, visible inhibit/API examples and event traces. Durable profile/maintenance recovery completion is cross-checked after M2/M3; do not close SR-AUT-02 here.
- Hardware/risk: simulate missing inputs honestly. Approved as-built signal polarity/update periods are needed for real adapters; no software watchdog substitutes for independent physical protections. No flashing or output energizing under this plan review.

## M2 — Production SQLite foundation

- Task: 121. SO-2/3, SR-DAT-01/02/03.
- Files: existing `services/database_service.py`; proposed `pi_hmi/migrations/*`, repository/migration/constraint/concurrency tests, data dictionary and recovery instructions.
- Interfaces: preserve all existing repository methods and DatabaseUnavailable/error semantics; add reviewed state/profile/event/ML/outbox methods through the same service boundary. Schema includes the eleven SO-2 entities plus explicitly reviewed profile/settings/operating-snapshot/outbox additions needed for criteria.
- Approach: versioned forward migrations with pre-migration consistent backup; UTC, units, stable IDs, constraints/FKs, parameterized statements, local SQLite WAL/FULL/busy timeout, short transactions and one routine write owner. Add all SO-2 indexes including maintenance/time and inference/model-version, and realistic bounded HMI queries. Synthetic seed data stays in fixtures, separate from production initialization.
- Tests: empty and previous-version migrations, idempotent version detection, constraints, bad paths/units/status/time, backup failure refusal, interrupted migration recovery, restart, foreign-key/integrity checks, query plans and concurrent writer/HMI reads. Do not use production data.
- Done/evidence: Data Design Review matches every SO-2 field and required operating snapshot; effective pragmas and all repository queries verified; backup/restore interface defined for M7. Migration rollback means documented recovery from backup, not destructive down migrations.
- Hardware/risk: host files suffice for initial tests; Pi filesystem performance and actual power-loss durability require later authorized testing. No existing data is migrated until reviewed deployment approval.

## M3 — Durable events, logger, alerts and operating snapshots

- Task: 122; integrates 12/120 and supports 13/129. SO-2/5, SR-DAT-03, SR-SAF-10, SR-ENV-01/02, SR-NET-01.
- Files: proposed event/logging/outbox services and tests; existing readers, state service, repository and app/dashboard.
- Interfaces: typed/validated event v1, stable IDs for retry, immutable source/time/experiment/software version; separate alarm created/acknowledged/cleared. Required operating records carry profile, growth-zone values, electronics temp, water/door/output state, alarms, maintenance and available ML result.
- Approach: single write pipeline; proposed 60-second validated per-sensor rows, complete five-minute snapshots and immediate faults/transitions/accepted commands/ACKs. Preserve last unavailable values as context, never healthy substitutes. Add specified temperature/RH alert delays. Bound retries/backpressure, expose dropped/failed writes and degraded storage; persist critical remote alarms with unsent status and independent delivery worker.
- Tests: deterministic cadence/missed-record accounting, threshold timers, outbox restart/retry/idempotence, ack not clear, blocked writer/ENOSPC and controller continuity while storage/network fail. Test remote five-minute delivery with a fake endpoint; no external messages sent during development.
- Done/evidence: sensor→state→event→SQLite→API integration, durable state/profile recovery and representative snapshot joins; logs correlate event IDs to DB rows. Delivery channel configuration remains explicit if none selected. Finish durable portions deferred from M1.
- Hardware/risk: actual sensor locations/calibration and remote transport/channel selection remain dependencies; no invented channel credentials or real notifications.

## M4 — Home and safety workflow UI

- Tasks: 129/130 plus 128 refinements. SR-UI-01/02/03, SR-SAF-03, SR-AUT-01/02, SO-4; schedule supports SR-LGT-01.
- Files: existing dashboard/HMI JS/CSS/templates; proposed profile/schedule services and browser/state workflow tests.
- Interfaces: authoritative state/inhibits, server-validated action/confirmation context, persisted profiles and schedule requests. Keep legacy URLs and serial command formats compatible.
- Approach: add missing Home fields with honest unavailable status, highest alarm, stale reasons and explicit requested/reported/physical state; preloaded basil/spearmint, Start/Pause/Maintenance/Safe Manual Test, persistent banner, confirmed exit and pump restart. Persist grow-cycle/profile selection; execute reviewed mist/light schedules through M1 permissions using deterministic time behavior. No automatic actuation enabled before safety review.
- Tests: all seven screens against real test repository/state service; cancel/stale/denied commands, full navigation preserves maintenance/E-stop, reset does not resume, fault during confirmation, profile persistence and clock/schedule/restart edge cases. Measure backend-update-to-DOM timestamps, not just poll interval.
- Done/evidence: checklist rows implemented with browser traces/screenshots and API tests; every command has confirmed or rejected outcome. Novice/hardware acceptance remains M9.
- Hardware/risk: reviewed horticultural schedules/settings and final touchscreen layout required. Physical light output and pump behavior remain separate from scheduling software.

## M5 — Camera/index/model integration

- Task: 123, child of 13; supports 131. SO-2/4/5, SR-DAT-02/03, SR-ML-01/03.
- Files: camera/camera_service/ml_service/dashboard; proposed capture/index/recovery tests and model manifest handling.
- Interfaces: single camera owner; saved file→committed image ID→inference record. Expose frame age, capture/inference progress/error and model version. All inference runs locally from installed artifacts.
- Approach: manual and proposed 30-minute routine captures (at least hourly requirement), file size/dimensions/hash/provenance, idempotent orphan reconciliation and atomic save/failure handling. Integrate actual versioned model when supplied; retain MLUnavailable otherwise. Confidence <0.70 displays Uncertain; two consecutive abnormal outputs required for alert except reviewed severe rule. Model failure cannot stop core sensing/control.
- Tests: image writes/index failures, stale camera, duplicate recovery, missing/corrupt artifacts, inference timeout, confidence boundaries and abnormal sequence reset. Use labeled synthetic images and fake model results for fault tests.
- Done/evidence: trace an image/hash/path through DB and model result to HMI; recover after restart without duplicate records; document missing model/hardware honestly. Actual runtime <=10s and <=250MB artifact size require real artifact evidence.
- Hardware/risk: working camera and ML-team manifest/runtime needed for complete acceptance; held-out model accuracy SR-ML-02 is a separate dataset campaign, never inferred from adapter tests.

## M6 — History, captures and exports UI

- Task: 131. SO-2/4/5, SR-DAT-02/03 and SR-UI-02.
- Files: existing dashboard/HMI; proposed history/export API and browser tests. Depends on M2/M3/M5; export/storage actions depend on M7 contracts.
- Approach: production bounded trends, experiment/event/alert/capture history with quality gaps, model linkage, CSV/images export progress and storage/backup state. Enforce API error mapping and safe download paths. M6 may land read-only history first; export controls land only when M7 is usable.
- Tests: mixed-quality seeded experiment, empty/unavailable/error cases, large query limits, image links, exports with matching IDs/hashes and backend failures. Do not infer no alarms from empty unavailable results.
- Done/evidence: screen/API/DB correlation, exported representative experiment and errors visible to operator.
- Hardware/risk: host fixtures suffice for initial UI; actual Pi capacity/performance later.

## M7 — Storage, backups, exports and restore

- Task: 124. SO-5, SR-DAT-02 and SR-NET-01; depends on M2/M3/M5.
- Files: proposed storage/backup/export/restore services, CLI and tests; configuration/runbook; HMI status endpoints.
- Approach: monitor 80% warning / 90% critical proposed SO-5 thresholds, calculate 90-day records and image budget, preserve >=30 days of images, suppress nonessential images on critical pressure while protecting records/events. Resolve D2 before real pruning. Nightly consistent SQLite backup plus image/config/model/software manifest to configured external target; end-experiment archive; checksum/integrity verification; restore to a fresh separate directory. Optional remote sync stays independent and queued.
- Tests: ENOSPC, partial copy, absent USB target, interrupted backup, corrupted manifest, concurrent writes during backup, unavailable sync, export completeness and restored row/hash comparison. Retention tests only delete disposable synthetic fixtures. Dry-run production policy until explicit authorization.
- Done/evidence: reproducible backup/export and verified clean-location restore, policy/budget approval, failure behavior and capacity tests. A successful backup command alone does not pass.
- Hardware/risk: external media and Pi storage trials required. Historical-data deletion and replacing deployed data remain outside current authorization.

## M8 — Service recovery and offline usability

- Tasks: 125/132. SR-AUT-02, SR-DAT-01, SR-NET-01, SR-UI-01/03, SO-4/5; depends on M1–M7.
- Files: startup/supervision code, systemd/kiosk/deployment scripts, local configuration and HMI safeguards; recovery/offline/browser tests.
- Approach: startup checks <=2min; retained profile/history; pump inhibited until all required signals safe and explicit resume rules satisfied. Isolate/recover worker faults, graceful shutdown and versioned deployment manifest covering all services/assets. Audit offline bundled assets, one-touch Home, text/icon redundancy, keyboard focus and >=approx48px touch targets at target viewport.
- Tests: disposable process restart/crash, missing configuration/DB/model/controller, worker dead/stale frames, recovery flags, browser connection loss and local service faults. SO-5 requires >=8h representative network-disabled run; later Pi power-interruption and physical reset tests require controlled authorization.
- Done/evidence: no false NORMAL at boot/fault, complete restart/kiosk timelines and failure traces; offline scenario artifacts. Actual hardware de-energization is not inferred from reported settings.
- Hardware/risk: final Pi OS packages, touchscreen, controller/interlocks and deployment approval needed for target changes.

## M9 — Backend/HMI acceptance and production release

- Tasks: 126/133, then 127/134, then 135; parent task 13 only closes when child criteria/evidence close. Sources: SO-2–5, SR-DAT-01/02/03, UI-01/02/03, NET-01, AUT-01/02, SAF-03/10 and applicable physical interlocks/ML criteria.
- Files: reusable acceptance fixtures/scripts, defect register, operator/deployment/migration/recovery guides, release manifest and `docs/evidence/task-<id>/` packages.
- Approach: freeze source/config/model/hardware versions; run combined offline/concurrency/migration/storage/restore/controller/sensor/ML/HMI tests; close defects with targeted regression; execute separately authorized Pi/hardware procedures. Release review precedes deployment. Tasks 127/134 harden production integration Jan 11–Feb 7, 2027; task 135 final usability window Mar 1–23, 2027 remains a separate Gantt obligation.
- Acceptance: genuine 72h endurance with <1% missing scheduled records, schedules maintained, <=one noncritical warning and no uncontrolled shutdown/manual reset/refill; five novice users with <=5min orientation, >=4 completing specified tasks within 5min with no critical and <=one noncritical error; visible updates <=2s from new backend data. Include >=8h SO-5 offline campaign, image retention/export/restore and <=2min safe startup. Physical timings use calibrated/controlled measurement and actual hardware, not simulated clocks.
- Done/evidence: per-criterion verdict and raw artifacts, linked PR/commit/tag, reviewer checklist, deviations and signed acceptance record. Do not mark SR/Gantt satisfied while actual criteria remain unproven. Release and final usability evidence remain distinct from passing development tests.
- Hardware/risk: working complete system, approved procedures, calibrated instruments, external backup media, actual model/dataset and five novice participants are prerequisites for full closure.

## Work that can proceed concurrently after contract review

This identifies independent workstreams, not authorization to spawn agents or assign people.

| Parallel work | Ownership boundary | Merge condition |
| --- | --- | --- |
| M1 state/sensor logic and M2 migrations/repository | State files vs database/migrations; share reviewed immutable event/repository contracts | M3 binds approved interfaces; one maintainer coordinates app/dashboard changes |
| M0/M4 screen checklist and M2 schema | HMI contract/tests/docs vs persistence code | Field names/units/errors frozen before UI production binding |
| M5 camera/index and M4 profile/workflow UI | Camera/ML services vs state/profile/HMI | Database image/state APIs stable; shared dashboard edits serialized |
| M7 backup/export backend and M6 read-only history UI | Storage services vs renderer/query callers | Export contracts agreed; dependent UI actions land with working backend |
| Acceptance procedure drafting and feature implementation | Evidence/test procedure documents vs runtime | Procedures reviewed against exact final requirements before execution |

## Evidence required in every milestone PR

Task and SR IDs; exact files and commit SHA; PR link; interface/configuration changes; exact test commands, environment and outcomes; raw logs/DB/export/screenshot artifacts as applicable; clear simulation/Pi/physical labels; unresolved dependencies; reviewer checklist and approval record. Use the evidence index in this package until an approved repository-wide index supersedes it. Never fill absent results with proposed outcomes.
