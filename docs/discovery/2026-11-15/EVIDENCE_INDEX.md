# Evidence index and baseline test report

Assessment date: 2026-11-15. Current local tracked revision: `b84736f7604abf6c2089a7f361b0bf2a795b5613`. Discovery documents are uncommitted review artifacts; they have no new commit SHA or PR. Existing application files were not changed. No new evidence was written to Drive or used to modify Gantt completion.

## Current execution evidence

| Evidence ID | Environment / command or observation | Actual result | Scope / artifact |
| --- | --- | --- | --- |
| E01 | Windows; from repo root: `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` | PASS, 9 tests, unittest elapsed 0.299s | Existing untracked root protocol-1 control app, FakeDevice/serial/compiler mocks. Transcript-derived result summary below; not Pi integration. |
| E02 | Windows; from `pi_hmi`: `..\.venv\Scripts\python.exe check_integration.py` | PASS, 12 tests, unittest elapsed 0.850s | Current tracked Pi application, hardware modules/background workers/uploader mocked. Not physical actuation. |
| E03 | `node --check pi_hmi\static\hmi.js` | PASS, exit 0 | JavaScript parse check only; no browser rendering, accessibility or latency assertion. |
| E04 | Local SHA-256 audit against `pi_hmi/environment/source-sha256.json` | 22 files, zero mismatches | Source manifest bytes match working-tree files. Deployed hash records match those same 22 values. |
| E05 | Read-only SSH `hostname`, UTC date, OS release and `systemctl show hmi.service` | Debian 13.7; active/running, User=germ, `/home/germ/hmi_flask`, PID 961, Restart=always, NRestarts=0 | Observed 2026-11-15 20:00:20 UTC; active since November 1. Point-in-time status only, no endurance inference. |
| E06 | Read-only deployed source hash and HTTP/paths audit | Seven screens HTTP 200; camera 503; data APIs not_configured; historical capture unindexed; default DB/models/exports absent | [Structured observation](pi-read-only-audit.json), [exact audit script](pi-read-only-audit.py). Python script does not import application/device modules or issue POSTs. |
| E07 | Read-only SSH `/api/state` | WARNING, no current sensors/controller/camera, unknown actuator feedback, DB/ML not_configured, estop not_connected, alerts active=null | Result observed in task transcript and summarized in README. Not a test of connected hardware. |
| E08 | Read-only journal tail, `df -h`, device-node listing, Python version and listener snapshot | Repeated camera 503; 23% disk usage/~43 GiB available; no USB/ACM device listing; Python 3.13.5; Flask binds all interfaces on 5000 | [Excerpt](pi-service-log-excerpt.txt); Pi address redacted. No root cause inferred from log excerpt. |
| E09 | GitHub connector metadata/trees/branches/main history/PRs | Current main 8789022; Phase 0 branch 4293db8; #2 draft open; #3 open | Pinned identifiers in [source register](source-register.json); no Git merges/pushes performed. |
| E10 | Gantt/official matrix/SO-2–5/task briefs/plan/inventory reads | Accessible; status and criterion snapshots recorded | [Source register](source-register.json) and links in README. Documentary content is not operational acceptance. |

Host environment: Python 3.12.14, Flask 3.1.3, pyserial 3.5, waitress 3.0.2. Installed host Flask differs from Pi requirements pin (3.1.1); this limits target reproducibility. `g++`, `clang++` and `arduino-cli` were not found by the current shell's command lookup. No compiler, new dependency or toolchain was installed.

### E01 test coverage

Control serial command mapping; invalid controls never reach device; write token required; USB port validation; mocked compile→release→upload order; compile failure prevents flash/disconnect; host-script upload rejected; reported flash/protocol incompatibility; fragmented serial response. Every test uses explicit fake state. The synthetic 22°C/55% fixture is not a hardware measurement.

### E02 test coverage

Both built-in lighting modes mock compile/upload/protocol confirmation; dashboard fan PWM report; fan off and fan speed acknowledgement routes; rejected script and invalid values; mode selector validation; preserved routes; upload token and build failure; USB release during update; matched acknowledgement; stale acknowledgement rejected. No actual compiler or upload process runs in this suite.

## Inspected historical evidence, not rerun

Existing [PR #2](https://github.com/turtle-robotics/GERM/pull/2) at `4293db8` contains `docs/phase0/BASELINE_TEST_REPORT.md`, `HOST_TEST_RESULTS.json`, host package/log records and fixture tests. Its report claims 10 existing integration checks and 24 new contract tests passed on 1 November on Windows/Python 3.12. It labels target Pi checks and local C++ execution incomplete. Those historical numbers are not added to this assessment's executed test count. The branch has not been checked out, merged, or rerun here.

PR #2 has useful tests for serial parsing, unavailable services, API catalog, invalid controls, sensor quality gaps, capture/index/storage failure, sample-schema constraints/WAL/concurrency/backup/reopen and in-process denied socket connections. Its sample database is a fixture, not a production repository or approved migration. Review against the SO-2 dictionary and chosen pin/PWM baseline before reuse.

## Not executed / no passing claim

- C++ compilation/execution or Arduino target compilation; actual firmware version or watchdog/pump electrical timings.
- Live OFF/ON actuator commands, firmware upload, controller reconnect, interlock actuation, calibration or physical safety tests.
- Service restart/power interruption, complete deployment, production DB migration, backup/restore, retention/pruning or historical-data deletion.
- Actual disconnected-network/end-to-end local DB/ML operation, >=8h offline SO-5 campaign, 72h endurance, full-storage hardware campaign.
- Browser screenshot/render/DOM freshness or touchscreen geometry acceptance, Lucidchart import, five-person novice test.
- ML artifact size/runtime, confidence behavior with real model, held-out metrics or biological grow acceptance.

## Task evidence ledger

| Task(s) | Current evidence | PR/commit | Remaining gate |
| --- | --- | --- | --- |
| 119 | E02–E10 plus discovery/traceability; earlier contracts/fixtures | Existing #2 / 4293db8; current application b84736f | Reconciled contract approval and target limitations/signals. |
| 12/120 | E02 serial/route subset, code review | Existing #3 covers pin/PWM, not state manager | M1/M3 plus physical power/interlock evidence. |
| 121 | Stub inspection; historical PR #2 schema fixture | #2 / 4293db8 is fixture only | Production migrations/repository and Data Design Review. |
| 122 | Accepted-control logging hook and unavailable DB observation | No production implementation PR | Durable event/logger/outbox integration. |
| 128 | Seven-screen source/API inspection and E06 delivery | No completed checklist PR in this assessment | Reviewed criterion-level checklist; M0. |
| 129/130/131/132 | UI source and limited E02/E06 coverage | Current local b84736f; no new PR | M4/M6/M8 plus user/latency trials. |
| 13/123 | Capture source and existing historical JPEG metadata | No new integration PR | Durable camera/index/ML chain; unavailable hardware/model remains open. |
| 124/125 | E05/E08 service/disk status; staging-helper inspection | No new implementation PR | Backup/restore, full supervision, startup and controlled recovery. |
| 126/133 | Development subsets only | No acceptance PR/results | Full backend/HMI gates; hardware, endurance, offline and novice evidence. |
| 127/134/135 | Planning scope from actual Gantt | No release/final acceptance evidence | Production release, HIL regression and final usability defect closure. |

## Per-task package convention after approval

Use `docs/evidence/task-<id>/README.md` with task/requirement IDs, implemented files and exact commit, PR URL, interface/configuration changes, command/environment/results, links/hashes for logs/screenshots/DB/export artifacts, simulation/Pi/physical labels, limitations/dependencies, reviewer checklist and actual review verdict. Do not populate commit/PR/hardware-result fields until they exist. Reference shared campaign artifacts without duplicating or relabeling results.

Reviewer checklist for this Phase 0 package:

- [ ] Confirm SR baseline release identity; preserve official partial/missing evidence statuses.
- [ ] Review reuse/reconciliation of existing #2/#3 and current main simulator.
- [ ] Confirm physical pin/signal/polarity map and missing interlocks separately from deployed-source hashes.
- [ ] Resolve storage policy conflict and approved logging/snapshot cadence.
- [ ] Approve or revise M0/M1 scope and the dependency sequence.
- [ ] Keep production changes, physical trials, data deletion and Gantt updates outside this discovery approval.
