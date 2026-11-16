# M4 / Tasks 129 and 130 — host HMI and grow cycles

Version `m4-review-1`, 2026-11-16. Branch `codex/m4-grow-hmi` starts at reviewed M3 `201a758c6e1c06fa45244ee751c57a4a04f2e6c6` plus verdict-record `cc05295`. [M2/M3 accepted with restrictions](M2_M3_REVIEW_VERDICT.md). The M4 PR targets `codex/m3-durable-events`; dependency order remains #5 M0 → #6 M1 → #7 M2 → #8 M3 → M4. No merge/deployment/hardware authorization is implied. Requirements remain [M0-provisional-2026-11-15](REQUIREMENTS_BASELINE.json); controlled release/signoff is unresolved.

## Implemented functionality

Migration 004 adds persistent basil/spearmint profile templates, grow cycles linked to the existing experiments table, schedules and a durable occurrence ledger. Profiles are copied into each cycle as versioned snapshots. The templates contain **no approved mist/light timings**: discovery Task 130 explicitly lists approved settings as a dependency and the reviewed contracts supply none. Both templates therefore begin unconfigured. The host editor accepts explicit simulation settings; displayed input examples are labelled as such and do not run until enabled, saved, fresh checks pass and Start is confirmed. No agronomic recipe, physical PWM/load/polarity or cooling policy is invented.

An operator can create a paused cycle, configure a UTC light window/RGB and fixed-five-second pump pulse interval, Start/Resume, Pause, enter/exit maintenance, perform a reviewed synthetic manual test or confirm completion. Only one open cycle is allowed by a unique SQLite index. Completion preserves all experiment/history/occurrence rows and permits selection of the other profile. Editing schedules requires a paused cycle and uses generation CAS. Current definitions may change; each occurrence retains its definition snapshot/generation. Disabled schedules are explicit rows, never deleted history.

The HMI now reads the injected M2 repository for experiments, alerts, trends and captures and displays active profile/cycle state, UTC grow day/schedules, normalized water/door state, E-stop indication, highest alarm by severity, electronics temperature availability and last recorded maintenance. Missing electronics/other interfaces remain NO DATA; invalid/stale nulls cannot render as numeric zero. Backend failures clear health/alarm indications to unknown and retain the last-known maintenance banner with an explicit warning. Camera/ML remain unavailable without adapters; camera status cannot claim a live image when unavailable. Home provides Start/Pause/Maintenance; full workflows and host schedule editing are available in Settings/Maintenance. Content scrolls at 739×447; the browser evidence includes the lower Home details. Full novice/touch/refresh acceptance remains a later gate.

## Command and persistence boundaries

All actuator-affecting paths still call M1 `CommandGateway`, including schedule commands and safe stop on faults. A pure additional gateway check requires a live, scoped scheduler grant for automatic energization. Neither profile data, an automatic-source string, restored running status nor an HTTP parameter supplies that grant. The grant is bound to occurrence ID, normalized command and cycle generation, exists only during the locked dispatch and is removed immediately afterward. Reviewed safe-off commands remain available through the same gateway while inhibited.

Grow-cycle Start first passes the existing backend-issued one-use confirmation and M1 interlocks. Scheduling remains disarmed and manual energization is blocked while the cycle's running intent is being committed. The cycle arms only after successful commit, unchanged authoritative revision and fresh valid state. A concurrent stop revokes that start. Failed storage operations latch `grow_storage_unavailable`, request gateway safe stop and never arm a cycle. Recovery explicitly checks storage and pauses; it cannot start anything. A repeated invalid Start while already running is rejected without silently disarming the existing session.

Changing profile/cycle or schedule configuration increments the authoritative revision **after commit**, revoking confirmations prepared during a slow write. Start confirmation text includes the current profile and enabled host settings. Existing actuator routes/confirmations remain; M4 adds four grow-data routes and confirmed `complete_cycle`. See [API catalog](API_ENDPOINTS.json) and [45-row checklist](HMI_API_CHECKLIST.md). Default app startup still has DatabaseUnavailable, an unavailable hardware adapter and production POST denial. Only explicitly injected synthetic host fixtures install GrowService/SQLite. No environment/HTTP flag enables production control, serial, GPIO, camera, flashing or deployment.

## Schedule behavior and recovery

| Concern | Host behavior |
| --- | --- |
| Conflicts | At most one pump and one lighting schedule; duplicate targets, unknown commands/targets and malformed/range/type values rejected |
| Lighting | Explicit HH:MM UTC daily window, including across midnight; reconcile current ON/OFF state once per edge/session; white channel unavailable |
| Pump | Existing bounded PUMP_5S only; integer host interval 10–86400 s (implementation guard, not a crop recommendation); no PUMP_ON from scheduling |
| Late pulse | More than one second after its scheduled slot is marked missed; no catch-up burst |
| Safety | Each tick reevaluates authoritative inhibits; faults disarm/request gateway STOP; every actual command is checked again under the gateway lock |
| Repeated/concurrent tick | UUID5 occurrence ID + durable unique claim before dispatch; duplicate claims never dispatch again |
| Failed ACK/outcome commit | Explicit unavailable or retained claimed/uncertain attempt; safe stop/restart inhibit; no automatic retry of that occurrence |
| Clock rollback | Latches schedule_clock_fault, disarms and requests gateway STOP; explicit recovery and confirmed restart required |
| Restart | Previously running SQLite cycle is committed paused; old sensor/controller health and scheduling grants are not restored; fresh checks and separate confirmation required |
| Maintenance/E-stop | Entry disarms/pauses; exit/reset cannot rearm. A separate confirmed Start after healthy input/persistence is required |

Light-window reconciliation uses current UTC window state; the occurrence's scheduled time may precede the cycle start. Pump phase is anchored to the first cycle start; resume does not replay missed pulses. Grow day is one plus completed 24-hour periods since first start (UTC), including paused time. These are documented host semantics, not assumed local-time/DST or horticultural policies. No actuator-specific continuation or shared-supply load policy is inferred. Supported control ownership is one gateway/service process; a multi-process/distributed controller lease is not implemented.

The ledger provides at-most-once dispatch intent per occurrence, **not exactly-once physical actuation**. A crash after claim but before/after hardware acknowledgment can leave a claimed record whose physical outcome is unknown. Recovery never retries it automatically; a newly confirmed session uses a new generation. Database writes and logging occur outside the M1 control lock. Slow cycle writes cannot block an urgent gateway stop; the scheduler's final state/generation check prevents stale dispatch after a concurrent pause.

M3 events link the active experiment and record configuration, cycle transitions, scheduling decisions, faults and maintenance. Command acceptance, firmware ACK and physical verification remain distinct. Configuration/occurrence ledger commit and event-pipeline commit are separate facts: the HMI shows pending/dropped status and whether the last command envelope is actually committed. Queued events remain vulnerable to process loss as documented in M3; a successful SQLite configuration write does not imply its trace event is durable. No deletion/retention job is added.

## Automated validation / traceability

`tests/test_m4.py` covers template persistence, strict/conflicting schedules, backend confirmations, gateway-only scheduling, occurrence dedup/concurrency, restart/no old health, missing/stale/unsafe sensors/controller/E-stop, maintenance and controlled resume, storage claim/config/start/outcome failures, slow-start concurrent stop, configuration-commit nonce revocation, late pulses/cross-midnight/rollback/grow day, retained history/completion and HTTP/SQL/highest-alarm integration. Existing M0–M3 tests are reused. `browser_m4.cjs` drives real Flask/SQLite/gateway/scheduler/event services with synthetic adapters, profile selection/schedule forms, cancel/accept, queue/commit display, unavailable electronics/stale nulls and seven-screen maintenance. CI repeats Python, actual-sketch C++ and both browser suites. Exact logs/source hashes/screenshots are in `docs/evidence/m4/`.

| Requirement / task | Host evidence | Open acceptance/dependency |
| --- | --- | --- |
| Task 129 / SR-UI-02 | Home fields, availability/source, profile/day/schedules, highest alarm, maintenance and queue/commit display | Real electronics/water/interlock/camera/ML interfaces; measured <=2 s target and user acceptance |
| Task 130 / SR-UI-01/03 | Basil/spearmint templates; persistent workflow, backend confirmation, paused edits, maintenance/manual test | Approved crop timings; novice usability and physical manual-test review |
| SR-AUT-01/02 | Persistent cycle/config recovery, inhibited restart and deterministic scheduling/fault tests | 72 h endurance, physical de-energization and timed startup/power-cut tests |
| SR-DAT-01/03 | Local M2 repository + M3 trace linkage, committed/queued distinctions | Full periodic operating snapshot/cadence and missing-record campaign |
| SR-SAF-02/03/10 | Final gateway checks for door/E-stop/unknown inputs and persistent inhibits | Electrical protection, polarity and physical response timing/certification |
| SR-LGT-01 | Symbolic scheduled RGB window and OFF logic | Actual spectrum, intensity, electrical mapping and approved photoperiod |

## M5 camera/ML readiness

Ready to design/test **host-side** M5 against existing image/inference tables, bounded repository queries, active experiment IDs and M3 envelopes. Not ready for physical camera activation, model acceptance or deployment. Proposed increments:

1. One-owner injected camera/frame contract with UTC/monotonic freshness and honest unavailable/stale state. Compute exact JPEG dimensions/size/hash; stage/finalize and index idempotently. Current manual capture metadata has fixed dimensions and lacks size; M5 must replace that assumption and test partial file/index/restart recovery.
2. Explicit capture scheduler linked to cycle/experiment, independent of actuator writers; synthetic hourly/missed-capture fixtures, safe disk/DB failure handling and no automatic deletion. Retention/export/image archive policy remains unresolved.
3. Local ML adapter with a reviewed model manifest/hash/runtime/labels/dataset. Preserve unavailable/slow/error states; apply <0.70 uncertainty and the reviewed two-consecutive-abnormal policy with versioned result/image linkage. No model weights, clinical/agronomic accuracy or image dataset is supplied/approved here.
4. Separate M5 PR with corrupted/stale images, unavailable/slow model, queue/restart/idempotency, uncertainty and browser tests. Physical calibration, local model latency/accuracy, licensing/dataset review and target acceptance remain separate gates.

All 15 original file hashes/untracked work are preserved. The existing PR stack stays unmerged. No firmware flashing, live actuator operation, deployed software change, production POST enablement, historical deletion, safety certification or Gantt update occurred.
