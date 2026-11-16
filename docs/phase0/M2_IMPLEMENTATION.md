# M2 / Task 121 host implementation

Branch `codex/m2-sqlite-recovery` starts at M1 acceptance-record `3951173`, above reviewed M1 `99a42a2`. Separate PR targets `codex/m1-state-permissions`; PR #5 → #6 → M2 dependency order remains unmerged. [Plan/dependency review](M2_M3_PLAN.md), [M1 verdict](M1_REVIEW_VERDICT.md). Requirements are still `M0-provisional-2026-11-15` with unresolved controlled-release approval.

## Schema and repository

The original eleven-table fixture was moved unchanged to `pi_hmi/migrations/001_baseline.sql`. Existing Phase0 builder/tests and seeds reuse it. Migration 002 adds fields identified in the SO-2 audit, inference/image/model, maintenance/component/time, system-event/time and actuator/request indexes plus a singleton generation-CAS restart checkpoint. Unknown safe_state remains NULL. Text IDs, numeric plant position 1–6, legacy manual/scheduled/fault capture reasons and component text preserve existing contracts; broader SO-2 taxonomy/components and full scheduled snapshots remain explicit future decisions. No migration drops rows/tables or deletes history.

`SQLiteRepository(path, workspace_root=..., create=True)` requires explicit host scope and creates no default database. Neither app imports nor environment variables install it. `DatabaseUnavailable` remains the default HMI repository and physical/production controls remain disabled. Methods preserve the existing repository read/write signatures; structured log_event is intentionally deferred to M3. Per-operation connections close explicitly and use foreign keys, synchronous FULL, persistent WAL and bounded busy timeout (100 ms host default, configurable 0–3000 ms; no target performance claim). Parameterized queries cap histories at 1000 rows rather than silently calling a truncated history complete. Validation enforces UTC, finite values, null invalid/missing readings, source sequence, relative image path/hash/dimensions/size and explicit ACK/physical flags. Image-content verification remains Task 123.

Version 0→2 and known fixture v1→2 are supported. Schema comparison rejects unknown drift; version/checksum ledger rejects future or modified migrations. Existing v1 databases receive a UUID-named verified consistent backup before upgrading. DDL/version/ledger updates commit together; interruption rolls back. No deployed schema is presumed compatible. No downgrade or automatic repair exists. Constructor failures raise; read/write failures mark status error and raise, and no result claims commit success before COMMIT.

Backups use SQLite's backup API and integrity/foreign-key checks. Destination creation is exclusive; a failed partial backup is left for inspection, never reused as a valid success. Restore validates the source and creates only a new host destination. It never overwrites the source or an existing destination. This tests DB recovery, not image archive completeness, backup scheduling or power-loss behavior.

## Restart contract

`attach_restart_store(gateway, repository)` is explicit trusted host bootstrap. It discards prior sensor/controller/startup/request state, restores only profile, maintenance and E-stop latch and always sets restart_required. It never restores confirmations, an active permission, or old healthy measurements. A missing checkpoint requires a first explicit checkpoint. Failed/corrupt reads enter conservative maintenance with profile unknown. The record always stores restart_required=true even if the live simulation has subsequently been started.

Checkpoint saves use generation compare-and-swap to reject stale writers. Changes to profile/maintenance/E-stop make persistence dirty and inhibit energization. Workflow completion attempts a checkpoint outside the control lock, after any safe-off dispatch. Failed writes report HTTP 503/persistence_failed and cannot clear restart. A confirmed start that clears the E-stop latch resumes only after a successful checkpoint plus a fresh permission/revision check; concurrent state changes cannot use that grant. Safe-off/status never wait on the checkpoint mutex. Pure StateManager acquisition/profile callers must explicitly checkpoint changed durable fields; M3 lifecycle wires acquisition checkpoint draining. Until committed, dirty state is explicitly inhibited. A crash before a newly changed in-memory intent is committed can retain the earlier intent; recovery nevertheless always inhibits restart and requires fresh checks. No physical power-cut guarantee is claimed.

## Validation / traceability

`test_m2.py` covers empty/repeated migration, v1 row preservation/backup, atomic interruption, schema/checksum/future-version/corruption rejection, required indexes/pragmas, reused seeds, query bounds/injection, ack distinct from clear, invalid/FK/image records, lock failure visibility, exclusive backup/restore/reopen, generation conflict, discarded old health, retained maintenance/profile/latch and slow/failed checkpoint isolation. The existing 80 M1/Phase0/integration tests remain required; preserved untracked root-app tests are separate. Exact logs are in `docs/evidence/m2/` once committed; CI includes M2 plus actual-sketch C++ and synthetic browser checks.

| Requirement / contract | Host evidence | Open acceptance |
| --- | --- | --- |
| Task 121 / SO-2 schema, repository, indexes | migration/adapter/fixture suites | ID/taxonomy/component decisions, production path/permissions |
| SR-DAT-01 local SQLite/offline | stdlib SQLite repository, no network dependencies | Pi deployment/endurance and ML remain unapproved |
| SR-AUT-02 profile/storage recovery, pump inhibit | checkpoint/reopen/restore/no automatic start tests | physical de-energization, power-cut/two-minute target checks |
| SR-DAT-03 linked timestamp/quality/profile evidence | existing entities and validated writes | full scheduled operating snapshot/cadence/missing-record campaign |
| SR-DAT-02 retention/storage | no deletion implementation | retain unresolved 90-day records / 30-day images / 80%-capacity policy conflict |

M3 follows in a separate PR for atomic structured event persistence and outcome projections. No hardware, flashing, production POST enablement, deployment, merge or Gantt change occurred. This package is for host review only.
