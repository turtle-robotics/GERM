# Configuration and deployment inventory

M0 update (2026-11-15): read-only SSH in the discovery phase independently observed Debian 13.7, Python 3.13.5 and active hmi.service as germ from /home/germ/hmi_flask. All seven screen GETs returned 200, camera 503 and current sensor/controller data unavailable. DB/ML were not_configured. The 22 application files in the local source-hash manifest matched deployed bytes; this is not a flashed-controller identity. No deployed software, service or data was changed. Earlier unverified entries below remain open unless explicitly superseded by those bounded observations. Picamera2/libcamera operation and physical hardware are not established by an OS version.

| Location/key | Baseline value/use | Verification/disposition |
| --- | --- | --- |
| app.py | 0.0.0.0:5000 Flask server; threads started on import | Single process; no production multiworker camera sharing |
| GERM_SERIAL_PORT | Optional explicit serial path; discovery ttyUSB/ttyACM | Confirm /dev/serial/by-id and germ dialout access on Pi |
| GERM_IMAGE_ROOT | /var/lib/germ/images | germ needs write/traverse; tests use temporary directory |
| GERM_ARDUINO_CLI | /usr/local/bin/arduino-cli | Installed AVR core/toolchain and executable permissions unverified |
| firmware_service.py | arduino:avr:uno; 180 s compile/upload timeout | Uploads are destructive to controller program; not run here |
| /home/germ/hmi_flask | Application/service working directory and venv | Match actual target install |
| /etc/systemd/system/hmi.service | User germ; Restart=always; RestartSec=3; journal logs | Unit file reviewed; installed/enabled state unverified |
| deploy/start_hmi_browser.sh, labwc-autostart | Local Chromium kiosk, Wayland and rotation | Display/session availability and Chromium executable unverified |
| environment/* | Exported pip/apt versions and source hashes | Historical snapshot, not proof of live drift or Debian compatibility |
| requirements.txt | Pinned direct Python dependencies | Host test requirements deliberately exclude physical adapters |
| /home/germ/hmi-backups/controls-<UTC> | deploy_to_pi.py backup of eight application files | No database/images; no full-install or firmware rollback guarantee |
| /var/lib/germ/models | Integration contract model packages/manifest | Planned; no deployed model verified |
| SQLite path, rotation, retention, archive and backup target | No runtime config exists | Proposed SO-5 /var/lib/germ/germ.db; implementation and retention-policy decision pending |

One camera process and one serial owner are required. Check GPIO/video/dialout access as germ; do not grant blanket privileges. Secrets are not supplied in this package. No ports were opened on this host; HTTP tests use Flask's in-process client. Expected target listener is TCP 5000; verify actual listeners and network exposure. INTEGRATION.md requires local/offline operation; after=network.target in systemd does not itself prove a network dependency.

Use staging and host checks before target deployment. Do not use the partial deploy helper as a clean installer. Capture source versions, file ownership, installed dependencies, unit status, camera acquisition, USB identity and writable image/data paths; preserve data using a SQLite backup API and image manifest when those services exist. Recovery must verify restored records/hashes on a clean path. Target procedure and remaining acceptance checks are in PI_VALIDATION.md.
