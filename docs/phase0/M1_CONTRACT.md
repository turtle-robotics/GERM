# M1 proposed state and permission contract

Version `m0-review-2`, provisional requirements [snapshot](REQUIREMENTS_BASELINE.json). This is a reviewable target contract, not runtime code or a claim that M0 already enforces safety. M1 development begins only after the explicit M0 contract review passes. Physical/deployment gates remain separate.

## One command boundary

Introduce `CommandGateway.execute(intent)` as the only application-level actuator-affecting dispatcher. It validates an immutable intent, reevaluates current authoritative state under a shared lock, consumes any required confirmation once, emits a decision, then calls the single hardware adapter. A prior browser decision or cached permission never authorizes dispatch. `StateManager.snapshot()` is read-only. Consumers do not mutate its internal dictionaries.

Intent fields: schema_version, request_id, action, target, payload, source (touchscreen/automatic/safety/service), requested_at_utc, expected_state_revision, and optional confirmation_id. Decision fields: request_id, allowed, reason_codes, state_revision, inhibits, requested_state, accepted_at_utc nullable, acknowledged_at_utc nullable, reported_state nullable, firmware_confirmed, physically_verified, and logging_status. `physically_verified` defaults false; ACK never sets it true. Rejection issues no energizing hardware command. Transport failure cannot become success.

Confirmation is backend-issued, single-use, expiring, and bound to the normalized action/payload and state revision. A changed interlock/state/profile revokes it. Pump energization after stop/maintenance requires a new explicit confirmation. The same checks apply to ordinary HTTP calls, legacy helpers and automation. Existing route success/error fields remain; new state/rejection fields are additive. 400 remains validation, 503 remains unavailable transport/service; propose 409 for changed state and 423 for an active inhibit. These new rejection statuses require consumer tests before implementation.

## Exhaustive entry-path inventory

| Entry path | Required action | Current bypass to remove in M1 |
| --- | --- | --- |
| app.py /api/led | set_lighting / off | send_command→serial.send |
| app.py /api/fan and /api/fan/speed | set_fan / off | direct serial commands |
| app.py /api/pump | set_pump / pulse / off | direct serial commands |
| led_sender.py / fan_sender.py | Same lighting/fan actions | legacy send imports; preserve callable compatibility while routing gateway |
| firmware_service.py /api/firmware built-in or custom | begin_firmware_update | token and upload mutex are not state authorization |
| firmware_port() STOP, release and reconnect | controlled safe-off and update-session capability | STOP failure currently ignored; require acknowledged stop and reviewed update policy |
| firmware_service.send('MODE:...') | set_lighting_mode | normal/rainbow both affect output state; rainbow can energize lighting |
| Firmware upload itself / reset defaults | firmware update session | custom/bundled firmware can change outputs on boot; protocol success is not safety certification |
| sensor_reader.py STATUS heartbeat | read_status under gateway lifecycle | STATUS renews watchdog; it must not mask a missing safe-stop decision |
| Future automatic schedules and maintenance tests | Same normalized intent actions | never introduce a scheduler/service-specific hardware writer |
| verify_live.py and external callers | Existing HTTP routes | no privileged route or testing bypass; live tool remains unauthorized here |

Custom firmware update defaults denied until its safety behavior is explicitly reviewed. A firmware_update capability must cover compile→safe-off acknowledgement→USB release→upload→reconnect→status; completion does not authorize MODE:rainbow or restart. M0 does not change the firmware updater. M1 tests mock all compiler/USB/upload operations. The controller's own physical protection remains independent of Python.

## State and permission model

| State | Entry | Energizing permissions | Exit |
| --- | --- | --- | --- |
| STARTUP CHECK | Boot/recovery | Denied; diagnostic/status and reviewed safe-off only | Checks valid and separate start; uncertainty becomes DEGRADED/SAFE STOP |
| NORMAL | Valid required health/interlocks and authorized start | Only approved profile/manual actions | Warning, service request, fault, stop or E-stop |
| WARNING | Noncritical reviewed condition | Only unaffected documented actions | Reevaluate valid health or escalate |
| DEGRADED | Unavailable service/sensor with documented conservative policy | Deny affected outputs; no guessed fallback | Valid recovery plus required explicit resume |
| MAINTENANCE | Confirmed request | Hazardous automatic actions denied; scoped manual test only if reviewed and confirmed | Confirm exit, all interlocks valid, then separate restart permission |
| SAFE STOP | Unsafe/unclassifiable fault, stop, controller loss or failed recovery | Denied; reviewed safe-off/status only | Fault recovery plus explicit start and checks |
| E STOP | Physical asserted/reported | Denied; hardware remains safety authority | Physical reset, safe checks, separate user start |

Unknown E-stop/door/water-level/leak are active inhibits for hazardous energization. Unknown inputs never become false/healthy. Reset/acknowledgement/recovered readings do not imply restart. A signal disappearing while running forces reevaluation and a conservative safe-state request; no software record claims power removal without evidence. Exactly which cooling/supply loads must stay enabled/disabled is an electrical decision: M1 simulation can model symbolic approved policies, but no physical output map is selected.

Maintenance intent, active profile and restart inhibit must survive restart through the future repository. Until durable repository support exists, boot is conservative and the recovery portion of SR-AUT-02 remains incomplete. Event sinks may report persistence failure but cannot grant permissions or block urgent safe-state decisions.

## Sensor input and event model

Sensor sample: sensor_id, source, value nullable, unit, sample_time_utc, received_monotonic, sequence nullable and adapter_status. Policy: expected_period_s, maximum_age_s <=2 expected periods for required fault detection, physical bounds, rate/intermittency policy, recovery criterion, installed location and affected actions. Values failing validation keep raw input in diagnostic payloads while decision values become invalid/missing. Reject NaN/infinity, impossible/future samples and stale/disconnected data. Threshold excursion timers (ENV-01/02) are distinct from sensor failure detection.

No electrical sensor periods/polarities are invented. Initial simulation fixtures use explicitly synthetic policies; production policies require electrical/requirements review. Existing fresh/stale/unavailable fields remain backward compatible; add quality_flag, fault_reason, expected_period_s and inhibits.

Reuse event v1 from CONTRACTS.md: stable event_id, UTC time, source, software_version, experiment_id nullable, schema_version and payload. State events add prior/new state, cause, inhibits and controller feedback. Command events distinguish requested, rejected, accepted, acknowledged and transport failure. Ack/clear/restart authorization are separate events. Rejected commands must not be recorded as accepted actuator events.

## M1 readiness and exact implementation increments

1. After contract review, create `codex/m1-state-permissions` from reviewed M0 SHA. Implement pure state/policy models and deterministic clocks in `services/state_service.py`, `sensor_policy.py`; test all transitions, invalid samples and <=two-period deadlines without device imports.
2. Add gateway/intent/confirmation models in `services/command_service.py`; tests prove no write on reject, revision/nonce freshness, bounded concurrent dispatch and safe-off behavior under unavailable storage/controller.
3. Integrate all listed routes/helpers/firmware sessions and STATUS lifecycle via injected gateway. Preserve old URLs/request formats, unavailable DB/ML and requested/reported/physical distinctions. Add tests that every entry path rejects inhibited commands and compiler/USB operations remain mocked.
4. Add state snapshot/inhibit/sensor-health fields and persistent maintenance banner across all screens, backend-confirmed maintenance entry/exit and controlled resume. Add only reviewed workflow endpoints, update API catalog and checklist together.
5. Publish transition/permission tables, fixture results and PR. M2/M3 complete durable restart/logging; physical output policies, signal mapping and measured timing remain explicit unresolved dependencies.

Required tests: missing/stale/implausible/nonfinite/future/intermittent sensors; controller loss/timeout/late ACK; door/leak/low water; E-stop unknown/assert/reset; maintenance confirmation; SAFE STOP/restart; upload STOP failure/mode rejection/custom deny; simultaneous requests; no-network/no-DB; frontend rejected-command feedback. Reuse existing serial, camera, sensor and SQLite fixtures; no simulated result closes physical requirements.

Readiness: M0 contract review pending. Pure host-side M1 is prepared and independent of pin numbers; hardware adapters/deployment/physical testing are blocked by separate electrical and user authorization gates.
