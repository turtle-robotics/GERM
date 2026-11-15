# Uploaded asset inventory transcription

Retained source inventory. Historical claims below are not new test evidence; current corrections and the complete file manifest are in ../../ASSET_INVENTORY.md.

Commit key

| Hash | Date | Message |

| --- | --- | --- |

| afce9d1 | 2026-10-11 | README.md installation change |

| ba38df7 | 2026-10-03 | Move red LED PWM from D5 to D3 in both lighting modes |

| 75c62b4 | 2026-10-03 | Add HMI lighting mode uploads with shared Uno wiring |

| 37999dd | 2026-09-30 | Export live Pi HMI with reproducible setup and credential exclusions |

| 2a8553a | 2026-02-13 | Add files via upload |

Directory map

GERM/

├── README.md, .gitignore, .gitattributes

├── Showcase LED Display.ino          (rainbow firmware variant)

└── pi_hmi/

    ├── app.py, dashboard.py, firmware_service.py     Flask app + blueprints

    ├── arduino_serial.py                              sole serial owner

    ├── camera.py, dht11_reader.py, sensor_reader.py   device readers

    ├── led_sender.py, fan_sender.py                   legacy command helpers

    ├── services/                                      backend contracts (stubs + sensor/camera)

    ├── templates/, static/                            HMI UI

    ├── arduino_program/arduino_program.ino            Uno firmware (default)

    ├── deploy/                                        systemd + kiosk

    ├── deploy_to_pi.py, verify_live.py, check_integration.py, tests/

    ├── environment/                                   Pi package inventories + hashes

    └── docs/, README.md, INTEGRATION.md, SECURITY.md

Master table

Flask application

| File / Asset Path | Commit | Purpose / Description | Runtime Owner | Current Status |

| --- | --- | --- | --- | --- |

| pi_hmi/app.py | 37999dd | Flask entry point (port 5000). Starts the DHT and serial reader threads, and serves /, /led, /fan, /pump, /sensor, /video_feed, /camera.jpg. Validates and forwards /api/led, /api/fan, /api/fan/speed, /api/pump to the Uno through arduino_serial. Logs accepted requests via repository.record_actuator_event. Registers the dashboard and firmware blueprints. | Backend Core | Reviewed; Pi: unverified. Control APIs work only with the Uno attached; logging is a no-op until the DB exists. |

| pi_hmi/dashboard.py | 75c62b4 | Blueprint for the screens /plant /trends /controls /alerts /maintenance /settings and the read APIs /api/state, /api/trends, /api/alerts, /api/alerts/<id>/ack, /api/experiments, /api/captures, /api/camera/capture, /captures/<path>. | Backend Core | Reviewed; Pi: unverified. DB-backed endpoints return empty data (stub). |

| pi_hmi/firmware_service.py | 75c62b4 | /firmware page and POST /api/firmware. Builds the bundled sketch (normal or rainbow) or an uploaded .ino with arduino-cli, releases USB, flashes the Uno, then checks the protocol. Protected by a per-process token and a 1 MB limit. | Backend Core (Firmware Lead for sketches) | Reviewed; Pi: unverified (needs arduino-cli 1.4.1 + AVR core 1.8.7). |

| pi_hmi/arduino_serial.py | 37999dd | The single locked USB serial bridge (9600 baud). Sends CMD:<id>:<cmd>; returns True only when the firmware acknowledges the same id. Caches the firmware state packet (6 s freshness). Provides firmware_port() for uploads. | Backend Core | Reviewed; unit-tested through check_integration.py (could not run locally). |

| pi_hmi/requirements.txt | 37999dd | Pinned direct dependencies: Flask 3.1.1, pyserial 3.5, Blinka 9.0.4, adafruit-dht 4.0.11, opencv 4.13.0.92. | Backend Core | Reviewed. |

HMI (touchscreen UI)

| File / Asset Path | Commit | Purpose / Description | Runtime Owner | Current Status |

| --- | --- | --- | --- | --- |

| pi_hmi/templates/index.html | ba38df7 | Single-page shell for Home, Plant, Trends, Controls (lighting/fan/pump tabs), Alerts, Maintenance and Settings. | HMI Lead | Reviewed; Pi: unverified. |

| pi_hmi/static/hmi.js | 75c62b4 | Client logic (351 lines): polling /api/state, control calls, freshness display, firmware mode upload. | HMI Lead | Reviewed; Pi: unverified. |

| pi_hmi/static/hmi.css | 75c62b4 | HMI styling (10 lines). | HMI Lead | Reviewed. |

| pi_hmi/templates/firmware.html | ba38df7 | Firmware upload page. | HMI Lead | Reviewed. |

| pi_hmi/templates/led.html | 37999dd | Original standalone lighting page. No route renders it (/led renders index.html) and no file references it. Orphaned in the repo. | HMI Lead | Dead code in repo. |

| pi_hmi/templates/fan.html | 37999dd | Same as led.html, for the fan. Orphaned in the repo. | HMI Lead | Dead code in repo. |

| pi_hmi/templates/pump.html | 37999dd | Same as led.html, for the pump. Orphaned in the repo. | HMI Lead | Dead code in repo. |

Device readers and adapters

| File / Asset Path | Commit | Purpose / Description | Runtime Owner | Current Status |

| --- | --- | --- | --- | --- |

| pi_hmi/dht11_reader.py | 37999dd | DHT11 on Pi GPIO4 (pin 7), polled every 2 s into latest_dht with timestamps. Instantiates the device at import time. | Backend Core | Draft: no validation beyond swallowing RuntimeError. Export notes say no readings were available at verification. Pi: unverified. |

| pi_hmi/sensor_reader.py | 37999dd | Thread that sends STATUS heartbeats and stores Arduino A0 in latest_data. Also keeps the Uno's output watchdog alive. | Backend Core | Reviewed; Pi: unverified. |

| pi_hmi/camera.py | 37999dd | Camera class: Picamera2 640x480 capture thread producing JPEG frames (IMX500 camera). | Backend Core | Reviewed. Hardware was unavailable at export verification. |

| pi_hmi/services/sensor_service.py | 37999dd | Builds readings with value, unit, UTC time, age and fresh/stale/unavailable state (fresh ≤ 10 s). Water temperature is hard-coded "Not installed". | Backend Core | Reviewed. |

| pi_hmi/services/camera_service.py | 37999dd | Saves manual JPEGs under /var/lib/germ/images/YYYY/MM/DD/ and returns metadata. | Backend Core | Reviewed. /var/lib/germ does not exist on the inventory workstation; the Pi install guide creates it. |

| pi_hmi/services/database_service.py | 37999dd | Repository contract (DatabaseUnavailable stub). Documents that the HMI never opens SQLite. | Backend Core / Database team | Stub. No SQLite implementation or migrations. |

| pi_hmi/services/ml_service.py | 37999dd | ML contract (MLUnavailable stub). | ML team | Stub. |

| pi_hmi/services/__init__.py | 37999dd | Package docstring. | Backend Core | n/a |

| pi_hmi/led_sender.py | 37999dd | Legacy helper sending LED: and LED_OFF. Nothing imports it. Orphaned in the repo. | Backend Core | Dead code in repo. |

| pi_hmi/fan_sender.py | 37999dd | Legacy helper sending fan commands. Nothing imports it. Orphaned in the repo. | Backend Core | Dead code in repo. |

Firmware (Arduino Uno)

| File / Asset Path | Commit | Purpose / Description | Runtime Owner | Current Status |

| --- | --- | --- | --- | --- |

| pi_hmi/arduino_program/arduino_program.ino | ba38df7 | Default Uno firmware (protocol 2): fan D2, pump D8, RGB D3/D6/D9 (inverted PWM). Acknowledges CMD:<id>:... with JSON state. 10 s output watchdog; pump limited to 30 s (PUMP_5S = 5 s). Has a GERM_DEFAULT_RAINBOW switch. | Firmware Lead | Host behavior test passed locally. Not compiled with arduino-cli or flashed in this inventory. Pi/Uno: unverified. |

| Showcase LED Display.ino | ba38df7 | Root-level copy with GERM_DEFAULT_RAINBOW 1 (rainbow variant). Duplicates the main sketch; the two can drift. | Firmware Lead | Reviewed. |

| pi_hmi/tests/firmware_behavior.cpp | ba38df7 | Host-side C++ test (stubs Arduino APIs, includes the sketch) for command handling and timing. | Firmware Lead | Passed (g++ -std=c++11, 2026-10-11). |

Deployment, boot and backup

| File / Asset Path | Commit | Purpose / Description | Runtime Owner | Current Status |

| --- | --- | --- | --- | --- |

| pi_hmi/deploy/hmi.service | 37999dd | systemd unit for the Flask HMI (installed at /etc/systemd/system/hmi.service). Runs as user germ from /home/germ/hmi_flask, Restart=always. | Backend Core | Reviewed; Pi: unverified (installed state and systemctl status not checked). |

| pi_hmi/deploy/start_hmi_browser.sh | 37999dd | Waits up to 30 s for Flask, then starts Chromium in kiosk mode on Wayland. | HMI Lead | Reviewed; Pi: unverified. |

| pi_hmi/deploy/labwc-autostart | 37999dd | labwc autostart: launches the kiosk script and rotates display DSI-1 by 180°. | HMI Lead | Reviewed; Pi: unverified. |

| pi_hmi/deploy_to_pi.py | 37999dd | Run on the Pi from a staging dir. Backs up 8 listed files to /home/germ/hmi-backups/controls-<UTC>/, stops hmi.service, copies the new files. The only backup routine; it covers file copies, not the database or images. The file list is hard-coded and omits e.g. services/. | Backend Core | Reviewed. |

| pi_hmi/verify_live.py | 37999dd | Post-deploy HTTP smoke test against 127.0.0.1:5000; sends only OFF commands. | Backend Core | Reviewed; needs the live Pi. |

| pi_hmi/check_integration.py | 75c62b4 | Unit tests with stubbed hardware (3 tests). | Backend Core | Could not run locally (Flask missing). Run on the Pi or in a venv. |

Environment, docs and repo config

| File / Asset Path | Commit | Purpose / Description | Runtime Owner | Current Status |

| --- | --- | --- | --- | --- |

| pi_hmi/environment/pi-packages.freeze.txt | 37999dd | pip freeze of the original Pi, including system packages. Not a requirements file. | Backend Core | Reference; reflects the original export. |

| pi_hmi/environment/pi-system-packages.txt | 37999dd | apt package versions on the Pi. | Backend Core | Reference. |

| pi_hmi/environment/source-sha256.json | ba38df7 | SHA-256 of deployed application files, for drift detection. | Backend Core | Reference. Not re-verified against the Pi. |

| pi_hmi/README.md | afce9d1 | Pi reproduction guide: wiring, install, boot and kiosk. Has an uncommitted local edit. | Backend Core | Current. |

| pi_hmi/INTEGRATION.md | 37999dd | Integration notes for the database, ML and camera teams. | Backend Core | Reviewed. |

| pi_hmi/SECURITY.md | 37999dd | Publication security review and exclusions. | Backend Core | Reviewed. |

| pi_hmi/docs/PI_README_ORIGINAL.md | 37999dd | Original Pi README, kept for history. | Backend Core | Historical. |

| README.md | ba38df7 | Repo overview. | Backend Core | Current. |

| .gitignore | 37999dd | Excludes secrets, *.db/*.sqlite*, logs, images, venvs. | Backend Core | Current. |

| .gitattributes | 37999dd | Line-ending config. | Backend Core | n/a |
