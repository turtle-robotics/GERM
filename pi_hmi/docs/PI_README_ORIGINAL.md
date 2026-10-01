# GERM Raspberry Pi HMI

This is the Flask application that boots on the GERM Pi from
`/home/germ/hmi_flask`. The installed `hmi.service` starts
`/home/germ/hmi_flask/venv/bin/python app.py`; labwc opens Chromium at
`http://127.0.0.1:5000`. The Pi's current kiosk viewport is 739 × 447.

## Existing system and redesign

The original app owned the IMX500 with Picamera2, read a Pi DHT11 on GPIO4,
read Arduino serial lines, and sent RGBW, fan and pump commands. The redesign
keeps the camera module, Arduino firmware protocol, `/sensor`, `/video_feed`,
`/camera.jpg`, `/api/led`, `/api/fan`, `/api/fan/speed`, `/api/pump`, and the
old `/led`, `/fan`, `/pump` URLs. The old control URLs now open the common
Controls screen. The Pi kiosk displays repeated ordinary JPEG snapshots
because its Chromium/Wayland session displayed the original MJPEG image black.

`templates/index.html`, `static/hmi.css`, and `static/hmi.js` provide the
seven SO-4 screens. `dashboard.py` exposes read APIs and manual capture.
`services/` defines sensor freshness, image storage, and the SQL/ML handoff.
See [INTEGRATION.md](INTEGRATION.md) for the full data contracts.

## Current hardware and service limits

- The IMX500 live camera is operational and owned by this Flask process.
- The Arduino is currently disconnected. Commands return HTTP 503 and no
  displayed command request is presented as a confirmed actuator state.
- The DHT11 values are unavailable at present. The UI distinguishes missing
  readings from fresh and stale readings; the Arduino A0 value is raw and is
  **not** mislabeled as water temperature.
- SQL and ML adapters are not installed yet. The HMI displays explicit
  awaiting-service states and does not invent measurements, alerts or diagnoses.
- The physical E-STOP is authoritative. Its state is not wired into the Pi;
  the HMI labels monitoring as not connected and cannot substitute for it.

## Run and verify on the Pi

```sh
sudo systemctl status hmi.service
curl http://127.0.0.1:5000/api/state
curl -o /tmp/germ-frame.jpg http://127.0.0.1:5000/camera.jpg
```

Manual startup from this folder (after stopping the service so the camera is
free):

```sh
sudo systemctl stop hmi.service
./venv/bin/python app.py
# In another terminal after testing:
sudo systemctl start hmi.service
```

Running `rpicam-hello` while the HMI is active fails because Picamera2 already
owns the camera. An SSH shell also has no local preview window. To test the
camera CLI independently, stop the service and use a no-preview still capture:
`rpicam-still -n -o /tmp/camera-test.jpg`, then start the service again.

The pre-redesign rollback archive is
`/home/germ/archive/hmi-before-redesign-20260926.tgz`. Restoring it requires
stopping `hmi.service`, extracting it into `/home/germ/hmi_flask`, and starting
the service. The boot service path itself was not changed.
