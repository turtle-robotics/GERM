# GERM Phase 0 discovery and proposed implementation baseline

Assessment: 15 November 2026, America/Chicago. Pi observations began at 20:00 UTC (14:00 Central). This is a review package, not a released baseline or a claim of system acceptance. Only discovery documents were added locally. Application code, firmware, deployed files, services, historical data and Gantt statuses were not changed. No actuator command, flash, deployment, restart, network outage or physical fault injection was performed.

## Review package

- [Task traceability matrix](TRACEABILITY.md): every requested task plus software tasks 127, 134 and 135 found in the actual Gantt.
- [Dependency-aware milestone proposal](IMPLEMENTATION_PLAN.md): exact task IDs, affected files, tests, exit gates and hardware dependencies.
- [Evidence index and baseline results](EVIDENCE_INDEX.md).
- [Source register](source-register.json): read-time Gantt rows, official requirement/evidence rows and source references.
- [Read-only Pi observations](pi-read-only-audit.json), [audit script](pi-read-only-audit.py), and [service/disk excerpt](pi-service-log-excerpt.txt).

## Resource access

| Resource | Access and scope |
| --- | --- |
| Local workspace | Readable, including all tracked source paths, untracked root app/tests/deployment scripts, Git branches/history and dependency inventories. Existing untracked files preserved. No applicable AGENTS.md found in workspace or checked parent locations. |
| GitHub GERM | Accessible through connector: repository metadata, branches, recent main commits, recursive trees, source and open PRs. Local remote-tracking refs are stale. |
| User-linked Gantt | Accessible. `GERM Gantt` A1:N150 read; authoritative software IDs include 119–135, plus parent tasks 12/13. Task 119 is In progress; remaining software rows inspected are Planned and Not Reviewed. |
| Development plan and Phase 0 inventory | Both accessible, as are task briefs 12, 13, 119, 120, 121 and 128. Other software rows do not provide separate brief links in the inspected Gantt; use their notes plus governing SO/SR sources. |
| TURTLE GERM shared drive | Accessible. Software, PIP, project-management and verification-evidence folders inspected. The verification-evidence folder returned no direct children; that alone does not prove evidence is absent elsewhere. |
| Software PIP / requirements | SO-2/3/4/5 content accessible, including table text. Official PO-SR matrix and verification planning matrix accessible. SRS DOCX text accessible; its label remains Proposed. Editable SO-4 diagram located, but Lucidchart import not exercised. |
| Running Pi | SSH accessible after network sandbox escalation; Debian 13.7, Python 3.13.5. Existing SSH config used without changing credentials or terminal state. Read-only service/HTTP/filesystem inspection completed. |
| Controller, sensors, camera, ML hardware | No working readings or controller connection demonstrated. Pi API reports unavailable hardware and unconfigured DB/ML. Physical interlock wiring, electrical timing, model artifacts, calibrated sensors and power recovery remain unverified. |

## Actual source baselines

| Baseline | Revision / disposition |
| --- | --- |
| Current checkout | `codex/restore-normal-pins`, `b84736f7604abf6c2089a7f361b0bf2a795b5613`; two pin/PWM commits after local main. |
| Local main and origin/main | `ba38df7f8fa77c5ea8e947ee46ad179645a32388`; not current GitHub main. No checkout/reset/merge performed. |
| GitHub main | `8789022415ffb44aca8ff88c4d1ba31f4ef994be`, merged PC simulator PR #4 on 14 November UTC. Parent simulator commit `4632ae1`. |
| Existing Phase 0 work | `phase0/contracts-assets-fixtures`, `4293db86efcebe92f707230ee778dd8d6ca8a3cc`; draft [PR #2](https://github.com/turtle-robotics/GERM/pull/2), still open. Includes contracts, manifests, fixtures, sample schema, 24-test contract suite and host CI. Review/reuse it before creating replacements. |
| Pin/PWM changes | Open [PR #3](https://github.com/turtle-robotics/GERM/pull/3), head `b84736f`. It is not merged into current main. |
| Deployed Pi | All 22 files listed in local `pi_hmi/environment/source-sha256.json` match the read-only deployed hashes. This establishes those files' contents, not an installed Git commit or the flashed Uno revision. Extra deployed `check_integration.py` was hashed separately. |
| Untracked root app | `app.py`, `templates/index.html`, root requirements/boot/service files and `tests/test_hmi.py`. Independent control-only application expecting protocol 1; must not become the production entry point by accident. |

GitHub main/Phase 0 share the older fan D2, RGB D3/D6/D9 firmware; the local/deployed manifest baseline uses fan PWM D3 and RGB D5/D6/D9. Pump remains D8. Pin selection requires explicit as-built reconciliation; neither branch names nor documentation establish actual attached wiring.

## Existing architecture and functionality

The production baseline is `pi_hmi/app.py`, copied to `/home/germ/hmi_flask/app.py` on the Pi. systemd starts it as user `germ`; Chromium/labwc consumes local Flask HTML/CSS/JS. It is a single process with daemon readers, not a supervised collection of separately restartable services. Imports initialize the DHT device and load camera dependencies; worker startup occurs at import. Missing Pi dependencies can therefore prevent startup before route-level degradation handling runs.

`arduino_serial.py` owns a locked USB connection at 9600 baud. It wraps commands as `CMD:<id>:<command>`, accepts protocol-2 JSON acknowledgements with a matching ID and no error, waits up to three seconds, and expires reported state after six seconds. `sensor_reader.py` sends STATUS heartbeats. The firmware implements a ten-second communications watchdog, 30-second pump maximum and five-second pulse. These are software rules; firmware acknowledgements represent output settings, not measured actuation. Request IDs wrap and have no session nonce.

Flask control routes validate values, call serial directly and attempt a repository write after acknowledgement. `requested_states` is memory-only and updated on success; complete request/reject/ack/physical verification history is absent. `dashboard.py` computes a display-only NORMAL/WARNING/CRITICAL summary. There is no authoritative state manager, command permission policy, maintenance mode, controlled resume, schedule engine or startup interlock validation. Firmware updating can turn on rainbow lighting and currently proceeds through its USB-release context even if STOP acknowledgement fails; that path also needs the future permission boundary.

`services/sensor_service.py` supplies unit/time/age and fresh/stale/unavailable states. DHT is polled about every two seconds while freshness is fixed at ten seconds: this does not establish fault detection within two expected update periods. There are no physical/rate/nonfinite/future-time checks, persistence or conservative-output policies. Water temperature is explicitly not installed, A0 remains unavailable, and door/leak/water-level/E-stop/electronics-temperature sources are missing.

The seven screens and legacy `/led`, `/fan`, `/pump` routes exist. State polling is every two seconds, images refresh independently, control actions have browser confirmation, and trend rendering distinguishes some quality flags. This is not proof of the two-second backend-to-visible deadline. Home lacks several SR-UI-02 fields; profiles, grow-cycle controls, actual maintenance workflow, exports/storage and production history are absent. Ordinary control APIs do not enforce browser confirmation or safety context. CSS includes controls below the SO-4 approximate 48-pixel touch target. ML rendering trusts `review_required`/class without independently enforcing confidence <0.70; it displays Review Required rather than the exact required Uncertain behavior.

`DatabaseUnavailable` and `MLUnavailable` honestly expose `not_configured`. Production migrations, SQLite writes/queries, alerts, sensor/event logging and ML inference do not exist. Some repository exceptions are isolated in `/api/state`, but history/capture/experiment routes lack consistent error mapping. No remote alarm queue/delivery exists. Browser code does not directly access SQLite/GPIO.

One Picamera2 owner generates cached JPEGs. Manual capture writes a dated UUID JPEG plus hash/dimensions and attempts indexing; failed indexing retains the file with `indexed:false`. Latest manual capture recovery uses filesystem mtime. Scheduling, durable index/reconciliation, image size verification, camera frame freshness/recovery and ML provenance remain incomplete. A worker failure can leave a cached frame without a freshness signal.

Deployment has a systemd restart rule, kiosk script and a staging helper. The helper copies only eight enumerated files, omits services/CSS/readers, flashes firmware, and only rolls back copied application files on failure. It is not a complete deployment/data recovery mechanism. No storage policy, consistent database backup, archive/export/restore, rotation policy or startup recovery coordinator is implemented.

Legacy helper modules and standalone templates have no current application caller; preserve until retirement is reviewed. Root showcase firmware duplicates the controller sketch with a rainbow default. Historical source exports and private deployment files exist locally but are not accepted deployment evidence or published in this package. No credentials were read or copied into these documents.

## Live Pi observations

- `hmi.service`: active/running, user germ, working directory `/home/germ/hmi_flask`, `Restart=always`, reported `NRestarts=0`, active since 1 November. This is one observation, not endurance acceptance.
- Flask PID 961 listens on `0.0.0.0:5000`. All seven screen GETs return 200. HTTP success proves page delivery, not complete workflows or a rendered kiosk screenshot.
- `/api/state`: WARNING; controller, camera, air temperature, humidity and A0 unavailable; water temperature not installed; E-stop `not_connected`; database/ML `not_configured`; active alert count unknown (`null`), actuator feedback unknown.
- `/camera.jpg`: 503; recent service log excerpt shows repeated camera 503s. Root cause not established by that excerpt.
- No `/dev/ttyUSB*` or `/dev/ttyACM*` nodes were listed. This supports absent USB serial availability; it is not a diagnosis of cabling or controller power.
- `/var/lib/germ/images` exists and is writable by germ. Default `/var/lib/germ/germ.db`, models, exports and `/etc/germ` paths do not exist. Log directory exists. Root filesystem is 23% used, with about 43 GiB available according to `df -h`.
- `/api/captures` exposes an old, unindexed manual JPEG from September. Historical images were neither changed nor deleted.
- Sensing, camera, control, offline runtime, interlock response and power recovery acceptance remain open. No POST endpoints were called on the Pi.

## Conflicts and decisions to resolve

| Decision | Source conflict / consequence | Proposed disposition |
| --- | --- | --- |
| D1 Source baseline | Current main has simulator; draft PR #2 has Phase 0 fixtures; open PR #3 and Pi contain different pin/PWM changes. Local origin/main is stale. | Start M0 from current main and review both PRs; preserve user work. Integrate intentionally on a feature branch after approval; do not silently choose a wiring map. |
| D2 Storage deletion | SR-DAT-02 requires 80% warning and oldest-image deletion while preserving >=30 days; SO-5 says not to automatically delete active-experiment images and asks for archive/export. User also forbids deleting historical data without explicit authorization. | Record policy conflict. Implement warning/export/dry-run and non-destructive fixtures first. Resolve retention precedence and obtain explicit data-deletion authorization before operating a real prune job. |
| D3 Logging cadence | SO-5 recommends 60-second readings and 30-minute images; SR-DAT-02 requires 90 days of five-minute operating records and at least hourly images. | Preserve both: proposed 60-second validated per-sensor persistence plus complete five-minute operating snapshots and 30-minute routine images. Review storage budget. Cadences remain separate from HMI refresh. |
| D4 Required Home fields | SO-4 emphasizes water temperature; SR-UI-02 additionally requires electronics temperature, reservoir, schedule, profile, grow day, maintenance date. Current shell is incomplete. | Use the union with honest unavailable values; prioritize official SR fields, never fabricate readings. |
| D5 Approval baseline | Gantt task 4 is Completed/Reviewed, task-4 brief still says Planned, SRS is Proposed, planning matrix procedures say approval required. No signed release record was established. | Pin exact SR wording/versions provisionally; request actual controlled release reference at review. Do not infer satisfied requirements or alter Gantt. |
| D6 Sensor policies | Fixed ten-second freshness versus two-second DHT sampling; absent interlock signals; ten-second watchdog versus <=0.5/1/2-second physical requirements. | Per-sensor periods and conservative policies reviewed with electrical. Hardware interlocks remain independent and must meet their own timed tests. |
| D7 Fixture schema | PR #2 schema is explicitly a review fixture and differs from SO-2 (IDs, fields, capture reasons; absent maintenance index/model-version index and some provenance fields). | Field-by-field audit before production migrations. Do not promote fixture SQL unchanged or count it as task 121 completion. |
| D8 Network obligations | Local assets support offline intent, but SR-NET-01 also requires critical alarm delivery within five minutes when configured and queued unsent alarms offline. | Include durable outbox and delivery fault tests in logging/recovery milestones; define actual remote channel with operator configuration. Local control remains independent. |

## Recommendation

First milestone: M0, reconcile and review task 119 plus task 128 contracts using existing PR #2, current main simulator and PR #3/deployed source evidence. No new state/database architecture should bypass that review. First functional implementation after this baseline review: M1, authoritative state/permissions and sensor-fault handling (tasks 12/120), including all control and firmware-mode entry paths. SQLite foundation follows against stable contracts, then durable event integration and dependent HMI work. See the milestone plan for the complete sequence.

Review requested: approve or revise M0/M1 scope and the proposed sequence; supply the controlled SR release reference and decide source/pin reconciliation. Physical tests, deployed changes, historical-data deletion and Gantt updates remain separately authorized actions.

## Principal sources

- [Repository](https://github.com/turtle-robotics/GERM), [existing Phase 0 PR](https://github.com/turtle-robotics/GERM/pull/2), [pin/PWM PR](https://github.com/turtle-robotics/GERM/pull/3).
- [User-specified Gantt](https://docs.google.com/spreadsheets/d/12wLfEu0dKK7DmKDDK8iFsJJ7ZDjyGzQx3rOSYZcZFks/edit).
- [Development plan](https://docs.google.com/document/d/1HWWs3aOOxa-U-6QNz4Og_R-yiyF0FZIS3lz29prAmhQ/edit), [asset inventory](https://docs.google.com/document/d/1FXdhm2VaAr-46mHluzN7bWLcn8jClIi43qnnATsbC0w/edit).
- [Official PO-SR matrix](https://docs.google.com/spreadsheets/d/1kSyYpYcDUr8cOaF3OiD30v9o_b0VQY4fkpBZvLmSCYU/edit), [verification planning matrix](https://docs.google.com/spreadsheets/d/1r-T_8f3iKZoRUbUuZ4BhbWD5mdXUHlt10DwLBhNOBMk/edit), [SRS](https://docs.google.com/document/d/1lAPZWoPScAPcV_cnvQ5dfAYOZT2jQjR1/edit).
- [SO-2](https://docs.google.com/document/d/1BYqpePrA7GVw6m5lS_Im-uvxjNZ21uw_/edit), [SO-3](https://docs.google.com/document/d/1NmsbTrIEN8ABuB3RRhkdGN3bonmMMyR3/edit), [SO-4](https://docs.google.com/document/d/1PiAVi72BTXKkeYlc8-MMnK3NDEjJBUZF/edit), [SO-5](https://docs.google.com/document/d/15Ik_vQLBqKYKxX7O40gjB72OzfYHPdHf/edit).
