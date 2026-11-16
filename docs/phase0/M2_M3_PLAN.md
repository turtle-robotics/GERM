# M2 / M3 implementation plan and dependency review

2026-11-15, authorized by the [M1 verdict](M1_REVIEW_VERDICT.md). Dependency order: PR #5 (M0) → #6 (M1) → separate M2 branch/PR → separate M3 branch/PR. No merge is authorized. Requirements remain `M0-provisional-2026-11-15`; controlled release/signoff remains unresolved. No Gantt update is implied.

## M2 / Task 121

1. Promote the existing eleven-table schema fixture to canonical migration 001, preserving existing seed/tests; add transactional migration 002 for the SO-2 audited fields, inference/model and maintenance indexes and a durable restart checkpoint. Stable text sensor/actuator/event IDs preserve contracts; no guessed component foreign key or physical safe state. No destructive downgrade or history deletion.
2. Explicit workspace-scoped host repository configuration only; default HMI remains DatabaseUnavailable. Each connection uses foreign keys, WAL, synchronous FULL and bounded busy timeout. Parameterized bounded HMI queries; UTC/finite/JSON/path validation; errors raise or return explicit failure, never false success. Query failures mark status error.
3. Before any existing-schema upgrade, make and integrity-check a consistent SQLite backup; detect future versions/schema drift and reject. Migrations are transactional and checksummed; test rollback, idempotency, old rows and constraints. Restore only into a new destination; never replace/delete historical data. Image archive/production backup scheduling remain later tasks.
4. Durable profile, maintenance intent and E-stop latch checkpoint with monotonic generation CAS. On boot restore those fields only; always inhibit restart and discard old controller/sensor/confirmation state. Missing/corrupt/unavailable state is conservative. A configured store failure inhibits energization; safing/stop never waits on the persistence lock. Checkpoint writes occur outside the command lock and cannot clear restart permission.
5. Tests: empty and v1 upgrade, indexes, invalid inputs, foreign keys, bounded queries, contention, backup/restore/reopen, corruption/future versions, interrupted migration, CAS and concurrent checkpoint changes, restart/no automatic pump permission. Existing M1 suites remain required.

## M3 / Task 122

1. Validate and persist reused event-v1 envelopes with stable UUID IDs, UTC timestamps, software/source/experiment linkage and finite canonical JSON. Same ID/content retry succeeds without duplicate; same ID/different content fails. Commit acknowledgment is explicit.
2. Drain the M1 bounded queue outside the control lock; durable retry preserves IDs. Record accepted/rejected commands, firmware ACK/transport failure/physical distinction, sensor quality/faults, maintenance transitions and recovery. Actuator and maintenance projections commit atomically with the system event. Rejections never become accepted actuator events.
3. Use explicit host lifecycle installation only; no import-time database or background threads. Expose pending/dropped/error/last durable status. Failure/slow storage never blocks urgent safe-stop under the control lock or grants permission. Restart recovers committed events; crash before a buffered event commits is an explicit loss window, not a durable claim.
4. Test idempotency/conflicts/atomic rollback, process reopen, malformed events, full/locked/failed stores, poison event isolation, concurrent drains, slow sink concurrent safe stop, observed fault and maintenance/restart traceability. No physical output or timing acceptance.

## Open dependencies

SO-2 `components` relationship has no approved dictionary; use existing component text. Safe states, pin mappings, sensor interfaces/polarities/periods remain unconfigured. Existing fixture descriptions containing pin numbers are synthetic legacy text, not approved wiring. M2 adds nullable metadata rather than inferring safety values. Persistence is local and has no network dependency. Production auth/network, real database path/permissions, storage capacity/retention conflict, full operating-record cadence/export/image archive and power-cut/endurance acceptance remain later authorized work; no deletion is implemented.
