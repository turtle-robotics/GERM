# HMI integration contracts for the SQL and ML teams

The SO-4 architecture is a local Chromium page → Flask route → backend service
→ hardware or local storage. Browser JavaScript never opens SQLite, talks to
GPIO, or runs inference. Normal operation has no internet dependency.

## Data flow

```text
Pi DHT11 / Arduino ──> sensor_service ──> /api/state ──> Home / Maintenance
                              │
                              └──> SQL repository (future validated logging)
AI Camera ──> single Picamera2 owner ──> /camera.jpg ──> Home / Plant
                    │
                    └──> manual/scheduled JPEG ──> image file + SQL images row
                                                       │
                                                       └──> ML inference
                                                               │
                                      SQL ml_inferences row <───┘
                                                               │
                           /api/state latest_result <─────────┘
Controls ──> Flask command routes ──> shared serial connection ──> Arduino
```

## SQL team: implement `services/database_service.py`

The current `repository` is `DatabaseUnavailable`. Replace that object with a
thread-safe adapter; keep the method signatures consumed by `dashboard.py` and
`app.py`. Its `status` is `ready`, `not_configured`, or `error`. A disconnected
or broken database must not turn empty results into a false “0 alerts” claim.

| Method | Input | Return used by HMI |
| --- | --- | --- |
| `get_latest_sensor_values()` | none | keyed reading objects for future persisted/current reconciliation |
| `get_sensor_history(sensor, start_time, end_time, experiment_id)` | sensor key and UTC ISO times | ordered points `{timestamp_utc, value, unit, quality_flag}`; retain missing/stale flags, cap/downsample large results |
| `get_active_alerts()` | none | rows with `alert_id`, `severity`, `source_type`, `message`, `timestamp_utc`, `ack_time_utc`, `clear_time_utc` |
| `get_alert_history(limit)` | count | same alert rows, recent first |
| `acknowledge_alert(alert_id)` | ID | boolean; set `ack_time_utc`, never set `clear_time_utc` unless the condition has actually cleared |
| `get_experiments()` | none | `{experiment_id, name, status, start_time_utc, end_time_utc}` rows |
| `get_experiment_data(experiment_id)` | ID | experiment and linked plant/reading summary |
| `get_recent_images(limit)` | count | image rows including relative `file_path`, `timestamp_utc`, `capture_reason`, and `image_id` |
| `record_image(image)` | capture metadata from `camera_service` | new `image_id`, or raise on write failure |
| `record_actuator_event(event)` | accepted request with UTC time, actuator, requested state, source | boolean indicating durable write |
| `log_sensor_reading(reading)`, `log_event(event)` | validated payload | boolean indicating durable write |

The SO-2 entities are `experiments`, `plants`, `sensors`, `sensor_readings`,
`actuators`, `actuator_events`, `images`, `ml_inferences`, `alerts`,
`maintenance_events`, and `system_events`. Use UTC ISO-8601 timestamps;
identify sensors and their engineering units in `sensors`; store reading
`quality_flag` and experiment linkage. Images belong in
`/var/lib/germ/images/YYYY/MM/DD/`; SQLite stores relative file paths, SHA-256
and metadata, never JPEG BLOBs. `camera_service.save_manual_capture` already
saves a JPEG there and passes metadata to `record_image`. Until that method is
implemented, the Plant screen says “saved locally, awaiting SQL image index.”
It can recover the latest manual JPEG from the image tree after a service
restart; full capture history still comes from the SQL repository.

SO-3 and SO-5 call for SQLite on local storage with WAL, `synchronous=FULL`, a
busy timeout, short writes, migrations, consistent backups, and an export
path. The SQL team owns those details and the ~60 s persisted sensor cadence,
plus event-driven fault records. The HMI's 2 s polling rate is for display;
it must not imply 2 s database writes. Wire current sensor values to the
repository through the backend logger, not browser JavaScript. Populate
`/api/trends`, `/api/alerts`, `/api/experiments`, and `/api/captures` through
the repository. The chart uses `quality_flag` to draw good data as a line,
stale/suspect points with distinct markers, and invalid/missing data as gaps.

## ML team: implement `services/ml_service.py`

The current `ml_service` is `MLUnavailable`. Keep `status`,
`get_latest_result()`, `get_model_info()`, and
`analyze_image(image_id, image_path)`. The HMI reads the latest result from
`/api/state`; it never runs model code in JavaScript. Return a result such as:

```json
{
  "image_id": 42,
  "timestamp_utc": "2026-09-26T05:00:00+00:00",
  "predicted_class": "healthy",
  "confidence": 0.92,
  "model_version": "germ-v1.0.0",
  "review_required": false,
  "inference_ms": 84
}
```

The SO-1 operational labels are `healthy`, `visually abnormal`, and
`uncertain / out-of-scope`. Map stored class values consistently and mark
low-confidence or out-of-scope results `review_required: true`; the UI then
shows **Review Required**, not a confident disease diagnosis. Store every
result in SO-2 `ml_inferences` linked to an `images.image_id`, with class,
confidence, model version, and timing. The latest-result query should join
the image so capture time and thumbnail path can be shown. A model failure
must change the ML status without stopping sensing, control, or image capture.

SO-6 selects TensorFlow/Keras training off the Pi, Edge-MDT conversion and
IMX500 packaging for local runtime. Keep the `.rpk` package, label map,
preprocessing configuration, `model_manifest.json`, and versioned assets in
`/var/lib/germ/models/`. A TFLite artifact may serve as an optional CPU
fallback. No boot-time model download is allowed. The ML worker must share
the **existing** Picamera2 owner or consume a saved image; it must not open a
second camera while Flask owns the IMX500. An inference should begin only
after image metadata has an ID so the database can trace it. A future ML
worker may be asynchronous; expose `running`, `unavailable`, `error`, and
successful states rather than blocking the HMI request.
An adapter exception is reported as an ML error in `/api/state` while the
camera and sensor values remain available. If SQL indexing fails after a JPEG
is saved, the capture response keeps the saved URL and sets `indexed: false`.

## UI team and current endpoints

`templates/index.html` is the shared seven-screen shell. `static/hmi.css`
contains the design tokens and 739 × 447 compact layout; `static/hmi.js`
polls `/api/state` and refreshes `/camera.jpg`. Both are bundled locally.
The Home screen shows live camera, current sensors, ML state, requested
actuator states, and alert availability. `/plant`, `/trends`, `/controls`,
`/alerts`, `/maintenance`, and `/settings` use the same shell. The old
`/led`, `/fan`, and `/pump` URLs still open Controls. Original serial command
formats are unchanged. Accepted requests are **unverified** until an Arduino
feedback/status protocol is built. A disconnected Arduino returns HTTP 503.

Manual captures use `POST /api/camera/capture`. The response includes the
saved image URL, UTC time, SHA-256, `image_id` if indexed, and an `indexed`
boolean. `/captures/<relative path>` serves saved images. The live camera
uses `/camera.jpg`; `/video_feed` remains for clients that support MJPEG.

The Pi currently has no Arduino connection, valid DHT reading, water
temperature sensor, database adapter, deployed ML model, or E-STOP state
signal. Their HMI states are explicit and must stay so until the responsible
hardware or team implementation exists. A physical E-STOP remains the safety
authority, regardless of any displayed software state.
