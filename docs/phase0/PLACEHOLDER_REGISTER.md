# Placeholder and incomplete behavior register

Inventory scope is every tracked baseline text file, reviewed with a TODO/stub/bypass scan and caller inspection. Functional boundaries replace named assignments. No placeholder is converted to fake healthy data. Priorities reference PHASE0_ISSUES.md.

| ID | Path/symbol | Current behavior | Boundary and disposition | Issue |
| --- | --- | --- | --- | --- |
| PH01 | services/database_service.py DatabaseUnavailable | Empty/null reads; false/None writes; not_configured | Repository: retain until Phase 2 adapter, migrations and tests | P0-03 |
| PH02 | services/ml_service.py MLUnavailable | Null model/result; inference raises | ML adapter: retain until local model and indexed results | P0-09 |
| PH03 | dashboard.py derived system_state | NORMAL/WARNING/CRITICAL display only; no command inhibits | State manager: replace in Phase 1; preserve honest status | P0-01 |
| PH04 | dashboard.py estop | Hard-coded not_connected | Hardware adapter: keep unavailable until physical signal approved | P0-02 |
| PH05 | sensor_service water_temperature; firmware a0 | Not installed; null | Sensor adapter: keep unavailable; no fake calibration | P0-02 |
| PH06 | sensor_service.reading | Freshness only; impossible/future/nonfinite values accepted | Validation service: add bounds/quality/recovery | P0-05 |
| PH07 | dht11_reader.py import and read loop | GPIO constructed at import; RuntimeError ignored; other errors can stop reader | Hardware adapter: initialization/error isolation | P0-05 |
| PH08 | camera.py; camera_service.py | Fixed 640x480; no camera-worker recovery; latest file scan by mtime | Camera owner: monitor/recover and index; retain dimensions tied to current config | P0-08 |
| PH09 | app.py record_control_request; dashboard DB reads | Logging no-op; some exceptions become 500 | Repository/API: add failure isolation and visible storage status | P0-04 |
| PH10 | deploy_to_pi.py FILES and paths | Eight-file subset, hardcoded USB and install path, external build; no data backup | Deployment: retain as partial updater only; full installer/recovery downstream | P0-06 |
| PH11 | led_sender.py, fan_sender.py, templates/led,fan,pump.html | Legacy helpers/templates not active shared-shell callers | API/presentation: retain historical; remove only after caller audit | P0-10 |
| PH12 | Showcase LED Display.ino | Duplicated firmware variant | Controller: test parity or generate from common source | P0-10 |
| PH13 | app.py direct command routes | No state manager, profile/start/pause/maintenance confirmation | State/API: implement Phase 1/4 workflows | P0-01 |
| PH14 | No logging/schedule/backup/export modules | ~60 s persistence, hourly captures, 80% storage warning/pruning, remote alarm queue absent | Logging/recovery: Phase 3/5 with acceptance evidence | P0-07 |
| PH15 | hmi.js placeholder profile/history/ML/status displays | Honest unconfigured screens do not satisfy all SR-UI fields/workflows | Presentation: bind real APIs when implemented | P0-07 |
| PH16 | firmware_port STOP result | Upload proceeds even without STOP acknowledgement | Serial/update: define failure policy and recovery | P0-11 |
| PH17 | GERM-PCB headers and footprints | Board connectors present; load/interlock map absent | Electrical/controller: approve installed wiring and signal contract | P0-02 |

Tests' simulated sensors, images, schema and controller are explicitly fixture-only. They are not deployed assets or proof of installed sensors, migrations, field accuracy, electrical outputs or trained ML.
