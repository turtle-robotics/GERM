# Phase 0 interface contracts

Version: phase0-review-1. Existing pi_hmi/INTEGRATION.md remains the repository and ML method authority; this supplement freezes the observed serial/API baseline and proposes missing event/schema boundaries. Changes require producer/consumer review and updated fixtures. No production schema or state machine is introduced here.

## Serial protocol 2 observed baseline

One locked USB session; 9600 baud, pyserial default 8N1, read timeout 0.2 s and write timeout 2 s. GERM_SERIAL_PORT overrides discovery. Opening waits 2 s. Pi sends ASCII `CMD:<id>:<command>
`, IDs 1–60000 wrapping; CR/LF inside caller commands is rejected. Firmware also accepts legacy unprefixed commands with id 0. Input buffer holds 79 bytes; overflow replies id 0 with an error. Do not use legacy commands for acknowledged application control.

Commands: STATUS, STOP, FAN_ON/OFF, FAN_SPEED:0 or 255, PUMP_ON/OFF/5S, LED:r,g,b,0, LED_ON/OFF, MODE:normal/rainbow. RGB integers are 0–255; white must be 0; fan D2 is digital only. STOP disables rainbow and all output states. MODE:normal clears RGB. Firmware replies newline-delimited JSON with protocol=2, id, fan/pump booleans, three integer rgb channels, a0=null, fan_pwm=false, white_channel=false, lighting_mode and optional error string.

Pi success requires a valid protocol/state packet with matching ID within 3 s and no nonempty error. Other IDs cannot acknowledge the request. Reported state expires only when age >6 s. STATUS polling waits 0.5 s connected or 2 s disconnected after each request; it is not a fixed-frequency heartbeat. Firmware stops all outputs at >=10 s since the last successful command. PUMP_5S limits duration to 5 s; PUMP_ON to 30 s; repeated ON does not reset start time. A shorter duration can shorten an existing run. Successful STATUS refreshes watchdog but never extends the pump timer. These are software behaviors, not measured electrical timing.

Current pins: fan D2 HIGH on, pump D8 HIGH on, inverted RGB D3/D6/D9 (255 means electrically off in analogWrite). Pi DHT11 is GPIO4, physical 7. Board header labels /2, /8, /*3, /*6, /*9 exist in GERM-PCB; assignment to actual loads and protection/interlocks is NOT established. A0 stays null; do not invent calibration or connect it to water level.

Known gaps: no session nonce/deduplication across reconnect, IDs can wrap, no independent output-current/position feedback, STOP failure does not block the firmware upload context, no physical interlock packet. See prioritized issues.

## API baseline

API_ENDPOINTS.json enumerates methods, paths, request constraints, success/error forms and caller. Control success means firmware acknowledgement with firmware_confirmed=true, verified=false and logged indicating durable logging; last_request remains separate from reported_state. No feedback or database readiness may be inferred from HTTP 200. HTTP 400 validates input; 503 signals unavailable control/camera/ack/backend; capture disk error is 500. Unknown routes are 404. Database read endpoints expose state alongside arrays; empty arrays with not_configured are unavailable, not zero alarms. /api/state exposes active=null when database is unavailable/error. Current exception handling is incomplete on several read routes; see P0-04.

The existing control routes lack a state manager and interlock authorization. Freezing their observed shape does not approve unrestricted deployment. Firmware POST has an X-GERM-Token, compile/upload locking and 1 MiB request cap; ordinary controls have no equivalent authentication.

## Sensor and event contract

Observed reading: value, unit, timestamp_utc, state, source; valid samples add age_seconds. Missing value/time produces null value/time and unavailable. Fresh means <=10 s; older samples are stale and retained as context. Units: air/water temperature °C, humidity %RH, A0 raw. Current implementation does not reject implausible values, NaN, infinity or future timestamps; the fixture records this gap rather than faking safe behavior.

Proposed persisted quality_flag vocabulary: good, stale, suspect, invalid, missing. Map fresh→good only after validation; unavailable→missing; never automatically accept implausible readings. Each installed sensor needs expected period, physical bounds, rate limits, installed location, recovery rule and affected-actuator policy reviewed before automatic control. SR-SAF-10 requires detection within two expected update periods. Missing interlocks inhibit pump in the target state manager; current implementation does not enforce this.

Proposed event v1 envelope: schema_version=1, event_id (unique string), timestamp_utc (UTC ISO-8601 with timezone), event_type, source, experiment_id nullable, software_version, payload. State transitions add prior_state, new_state, cause, inhibits and controller_feedback; actuator events retain requested_state and reported_state separately. Rejected commands are diagnostic events, never accepted actuator events. Alert acknowledgement only sets ack_time_utc; condition recovery alone sets clear_time_utc. Retry policy must preserve event_id to avoid duplicate durable records. No logger currently emits this envelope; fixture-only proposal.

## Storage, camera and ML

SCHEMA_CONTRACT.md defines the proposed review schema, migration authority and field audit. Existing repository signatures remain unchanged. JPEG paths are relative YYYY/MM/DD/manual_<UTC>_<suffix>.jpg beneath GERM_IMAGE_ROOT (default /var/lib/germ/images), with SHA-256, UTC capture timestamp, reason and dimensions. SQL stores metadata, never image bytes. A saved JPEG survives SQL indexing failure; response stays 201 with indexed=false and image_id=null. Startup scan recovers latest manual JPEG by filesystem mtime, not verified capture provenance. No scheduled capture or pruning exists.

MLUnavailable keeps status=not_configured, null model/result and raises on analyze_image. Proposed review result follows INTEGRATION.md: image_id, timestamp_utc, predicted_class, confidence [0,1], model_version, review_required and inference_ms. SR-ML-03 requires confidence <0.70 shown Uncertain, two consecutive abnormal results before an abnormal alert except separately documented severe conditions. These rules are downstream acceptance obligations, not implemented ML evidence. Saved images and models remain local; no boot download; one camera owner.
