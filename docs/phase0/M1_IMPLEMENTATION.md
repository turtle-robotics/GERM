# M1 host implementation and review guide

Review outcome: [accepted with restrictions at 99a42a2](M1_REVIEW_VERDICT.md), host-only. PR #5 → #6 remain unmerged; M2/M3 host development is authorized.

Version `m1-review-1`, 2026-11-15. Implements the host portion of approved [M1 contract m0-review-2](M1_CONTRACT.md). M0 was accepted with restrictions at `3b1d20b563af6836d0e3073f7748a5186c6b0af3`; [verdict](M0_REVIEW_VERDICT.md). This branch starts at that baseline plus its review-record commit `d93b7bb`. PR #5 remains unmerged. The separate M1 PR targets `codex/m0-contract-reconciliation` so reviewers see only M1 changes; rebase/retarget onto main follows an authorized M0 merge.

## Operational boundary

This is a host simulation implementation, not a deployable controller or physical safety certification. Default startup opens no camera, GPIO, serial port or worker. All POST routes return 403 until trusted host code installs a synthetic adapter, explicitly enables simulation, supplies a callable authorizer and sends the process token. The page token is CSRF protection, not authentication. No environment variable or HTTP body enables control. Physical serial creation, deployment/live verification entry points and real firmware compilation/upload are disabled. Do not deploy this branch to the Pi.

`services/control_runtime.py` supplies a default unavailable adapter. `tests/m1_http_harness.py` and `tests/browser_host.py` install synthetic fixtures. `sim/run_sim.py` preserves the fake-device launcher, but leaves unreviewed policies/interlocks unconfigured and controls inhibited. Only the test harness seeds healthy normalized synthetic interlocks and an explicit synthetic profile. No fixture is an electrical configuration.

## Permission and state behavior

`StateManager` owns revisioned snapshots under an RLock. `CommandGateway` holds that same lock through permission recheck, confirmation consumption and adapter dispatch. Intent payloads are canonical immutable JSON; authority is a trusted object identity, never a caller-supplied role string. The transport also requires a scoped gateway dispatch capability. Source/schema/time/payload validation, state revision, single-use 30-second nonce and bounded request replay protection are checked at dispatch. STATUS does not invalidate a pending confirmation or overwrite the last operator outcome.

| State | Host behavior | Recovery |
| --- | --- | --- |
| STARTUP CHECK | Hazardous commands denied | Valid configured checks, profile and separate confirmed start |
| NORMAL / WARNING | Authorized synthetic actions only; warning does not invent a fallback | New fault immediately inhibits |
| DEGRADED | Missing/invalid sensor data inhibits all hazardous outputs | Valid recovery samples and separate confirmed start |
| MAINTENANCE | Automatic energization denied; persistent banner on seven screens | Confirmed exit leaves SAFE STOP; separate confirmed start |
| SAFE STOP | Hazardous actions denied; reviewed synthetic safe-off/status only | Checks valid and confirmed start |
| E STOP | Asserted input latches; no energization or maintenance test | Physical-reset observation, valid checks, separate confirmed start |

Door, water level, leak and E-stop require explicit normalized safe booleans; air temperature and humidity require reviewed policies. Missing policies, invalid/missing samples and controller loss are active inhibits. Every required sensor fault conservatively inhibits every hazardous action. `affected_actions` is retained in policy metadata for future reviewed per-actuator continuation; this implementation grants no such continuation. Default safe-command and maintenance-test lists are empty. Only synthetic fixtures approve STOP/OFF and a bounded pump pulse; no physical safe-output policy is inferred.

Acquisition enters `gateway.observe_sensor`, commits quality and requests the reviewed symbolic safe state on fault. STATUS polling reevaluates expiry and requests STOP before a heartbeat can renew the controller watchdog; failed/contradictory STOP prevents STATUS. The raw protocol requires the matching command ID within its deadline. A failed ACK invalidates controller health. Requested action, backend acceptance, firmware ACK and physical verification remain separate. `physically_verified` and compatibility alias `verified` remain false for all simulation outcomes; STOP ACK is reported output state, not proof of power removal.

Sensor policies require explicit finite physical bounds for numeric values, expected period, maximum age no greater than two periods, UTC timestamp, recovery and intermittency/rate settings. Validation rejects missing, nonfinite, impossible, future, replayed/out-of-order and adapter-fault samples. Maximum-age decisions use a monotonic deadline including initial sample age. Two good recovery samples are the synthetic default. Actual signal periods, location, polarity, calibration and thresholds remain unconfigured. Raw legacy DHT context is diagnostic and cannot satisfy the authoritative interlocks.

## Entry paths and compatibility

| Path | Current dispatch / evidence |
| --- | --- |
| POST /api/led, /api/fan, /api/fan/speed, /api/pump | Normalized gateway intent; route validation and confirmation before energization |
| fan_sender, led_sender, app.send_command, arduino_serial.send | Compatibility functions preserved; no implicit authority, all call gateway |
| MODE normal/rainbow | Parsed as output-affecting intents; rainbow requires energizing permission/confirmation |
| sensor_reader STATUS / read_line | Gateway safe-state lifecycle before heartbeat |
| raw _exchange | Requires scoped synthetic dispatch, rejects physical serial objects and late/unmatched ACKs |
| POST /api/firmware and firmware_port | Custom denied; built-in denied by default; only reviewed synthetic normal updater can run after maintenance, confirmation and ACK reporting all outputs off |
| firmware reset / post-update MODE | No automatic rainbow or restart; synthetic post-update state must report off |
| verify_live.py / deploy_to_pi.py | Direct execution fails before network/subprocess/service/flash side effects |
| Future automation / maintenance tests | Same gateway and authorities; no separate hardware writer |

Existing page URLs, GET data and actuator POST payload formats remain. Production POST restriction and mandatory confirmations are intentional behavioral restrictions. New `/api/confirmations` prepares a grant without executing; `/api/workflow` supports start, pause, maintenance entry/exit and reviewed manual test. Final actuator/workflow POST includes `confirmation_id` and `expected_state_revision`; request_id is optional. See [API catalog](API_ENDPOINTS.json). HTTP 400 is invalid input, 403 authorization/restricted custom upload, 409 stale/replayed/missing confirmation, 423 inhibit/policy restriction and 503 unavailable transport/service. HMI consumers display rejection reasons and accepted/ACK/physical distinction. Firmware controls remain disabled.

## Evidence and traceability

The official provisional requirement snapshot remains [M0-provisional-2026-11-15](REQUIREMENTS_BASELINE.json), sourced from the current official 40-SR PO/SR matrix modified 2026-10-02. Its unresolved approval status is unchanged. Task 119/128 M0 acceptance remains scoped to the recorded verdict; [45-row current checklist](HMI_API_CHECKLIST.md) adds the M1 confirmation/workflow contracts without claiming missing product features are complete.

| Contract / requirement concern | Implementation | Automated evidence |
| --- | --- | --- |
| One permission boundary; all paths | command_service, control_runtime, arduino_serial, route/helper integration | test_m1_http route/helper/raw/MODE/firmware/deployment cases |
| Sensor failure <= two expected periods | sensor_policy + state_service | test_m1 isolated deadline for each of six sensors; invalid/future/rate/replay/intermittency/recovery cases |
| Fault acquisition / controller loss / late ACK | observe_sensor, poll_status, protocol deadline | immediate safe-state/no browser, failed STOP blocks heartbeat, late matching ACK rejected; reused protocol fixture tests |
| Maintenance / E-stop / controlled restart | state_service + workflow gateway | each unsafe interlock, reset cannot restart, maintenance/manual-test restrictions, conservative reboot |
| Confirmation / source / concurrency | gateway lock, immutable intents, nonce and revision | eight concurrent nonce replays yield at most one dispatch; twelve inhibited concurrent workers yield zero writes; forged authority/payload/TTL tests |
| SR-AUT-02 restart behavior (partial) | boot inhibits; profile/maintenance are volatile | reboot cannot authorize control; durable recovery explicitly incomplete |
| Event v1 and persistence failure isolation (partial) | bounded event buffer; sink flush outside control lock | slow/failing storage cannot grant permission or block control; no durable logging claim |
| HMI rejected feedback / persistent maintenance | shared template/JS, API additions | real browser cancel, confirmed pump, all seven screens, inhibited action, firmware disabled, exit/start; no page errors |
| Existing protocol/HMI/data compatibility | reused tests and FakeUno/fixtures | existing integration, Phase0, M0 suites; actual sketch C++ host harness |

Run `.venv/Scripts/python.exe pi_hmi/tests/run_host_checks.py --root-app` locally (omit --root-app when the preserved untracked application is absent). Reports default to `build/m1-evidence`; root legacy checks are separate from the selected Pi application. CI runs the five tracked Python suites and actual-sketch C++ harness on Linux. Browser check: install Playwright 1.62.1 and Chromium in a disposable environment, then `node pi_hmi/tests/browser_checks.cjs`; optional `GERM_PLAYWRIGHT_MODULE`, `GERM_TEST_BROWSER`, `GERM_TEST_PYTHON` select local runtimes. It starts a disposable loopback server and browser with synthetic adapters only. CI uploads browser evidence. Committed test logs and browser results are under `docs/evidence/m1/`.

## Open dependencies and next milestone readiness

M1 host behavior is ready for code/contract review. Physical integration and deployment are not ready. Electrical review must reconcile the Lucidchart/screenshot load mapping against both code candidates, including shared supply DIM+, PWM capability, pins/polarities, safe outputs and independent physical protection. Sensor interfaces, locations, normalized safe values, periods and fault thresholds need approval. No pin map was changed here.

Production needs an approved authentication/network boundary before any control endpoint is enabled; the simulation authorizer is not that boundary. Custom firmware and all real upload/reset behavior require a separate safety review. No compiler, uploader or Pi operation was performed.

M2/M3 must add durable profile/maintenance/restart recovery and event persistence with idempotency, migration/retention review and recovery tests. Current in-memory event buffering reports dropped events and `buffered_not_durable`; HTTP legacy actuator logging is optional and cannot confer permission. Boot always inhibits, but cannot reconstruct active maintenance/profile after a process restart. This remains partial SR-AUT-02, not an accepted durable implementation.

The storage-retention conflict remains unresolved: reconcile the official requirement's experiment/history retention obligation with earlier automatic image/record deletion proposals before implementing deletion. No historical files or records were deleted. No Gantt status was changed. Physical timing, actual actuation, E-stop performance, controller power behavior and safety certification require separately authorized hardware tests. M1 review is the next gate; no M2/M3 implementation, merge or deployment is implied by these host results.
