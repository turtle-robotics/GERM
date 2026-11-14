# Architecture and contract boundaries

These are functional runtime authorities and review boundaries, with no named people or subteam assignments. Current code has no central state manager; the target boundary below is a Phase 1 obligation.

`Chromium → Flask → service adapters → serial/controller, camera or repository → local files`

| Contract | Single authority | Consumer/review boundary | Current caller/files |
| --- | --- | --- | --- |
| Operating state and command inhibits | State manager (planned) | API and controller adapters | app.py currently sends directly; dashboard.py derives display state |
| Serial session and request IDs | arduino_serial.py | sensor_reader.py, app.py, firmware_service.py and controller firmware | One RLock and USB connection; no separate reader |
| Fast outputs, communications watchdog and pump timer | Uno firmware | Serial adapter and electrical signal review | arduino_program.ino; root showcase variant retained |
| Sensor samples and freshness | sensor_service | API/logger and sensor validation review | dht11_reader.py, sensor_reader.py → dashboard.py/app.py |
| Storage schema, migrations and writes | Repository adapter (planned) | Dashboard, camera, logger and query review | services/database_service.py; method callers in app.py/dashboard.py |
| Camera device lifetime | Camera instance | Capture service and ML adapter review | app.py → camera.py; no second Picamera2 process |
| Image metadata and inference | Camera service/repository; ML adapter for results | HMI and traceability review | services/camera_service.py, services/ml_service.py |
| HTTP validation and response shapes | Flask app/blueprints | Browser and contract test review | app.py, dashboard.py, firmware_service.py |
| Presentation | Local HMI | API and accessibility review | index.html, hmi.js, hmi.css; legacy templates/helpers retained but unused |
| Install, backup, recovery and exports | Deployment/recovery service (partial/planned) | Runtime and restore review | deploy/*, deploy_to_pi.py, README.md |
| Board nets and electrical safety | PCB/electrical design authority | Controller pin mapping review | GERM-PCB KiCad assets; actuator mapping unapproved |

Every baseline file is assigned a functional boundary/disposition in ASSET_MANIFEST.csv. All new docs/tests belong to the contract review and test evidence boundary. Browser code must never open hardware, inference engines or SQLite. Optional logging failure cannot turn an accepted command into a physically verified command, and optional ML/network failure must remain isolated.

Target state vocabulary from the development plan: STARTUP CHECK, NORMAL, WARNING, DEGRADED, MAINTENANCE, SAFE STOP, E STOP. The current API only derives NORMAL/WARNING/CRITICAL for display; it is not authoritative safety state. Physical E-stop remains independent authority. Review approval is pending; the user waived named assignments, not hardware acceptance.
