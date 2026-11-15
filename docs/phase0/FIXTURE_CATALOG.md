# Fixture catalog

All fixtures are synthetic and local. Run each suite in its own Python process from pi_hmi. No physical adapter imports, serial opens, firmware flashes, external sockets or production data changes occur in the new suite. Minimal dependencies: pip install -r tests/requirements-host.txt. camera.jpg is a committed 640x480 solid-color JPEG, not a plant image or ML training/validation asset.

| Fixture | Executable consumer | Purpose and limit |
| --- | --- | --- |
| tests/fixtures/serial.json; ReplaySerial in test_phase0.py | SerialContractTests | Partial/malformed/overflow packets, valid/rejected state, mismatched IDs, error ACK, timeout, expiry, STOP; software protocol only |
| tests/fixtures/sensors.json | SensorTests | Normal, missing, boundary/stale, implausible and future samples; records current validation gaps rather than claiming target quality |
| tests/fixtures/schema_v1.sql + seed.sql | StorageFixtureTests | Build sample SQLite from empty, seed all data classes, FK/quality/dedup, WAL concurrent reader, ack versus clear, backup/reopen/integrity; fixture schema only |
| tests/fixtures/camera.jpg + camera_metadata.json | CameraAndPlaceholderTests, StorageFixtureTests | Local capture/hash, image→inference FK, module restart scan; no Picamera2/device test |
| tests/fixtures/api_requests.json | APIContractTests | Safe-off request examples and response assertions: firmware_confirmed true, verified false, logged false with real unavailable adapter |
| API_ENDPOINTS.json | APIContractTests | Exact current route/method inventory plus request/response/error examples; endpoint set checked against Flask |
| tests/fixtures/scenarios.json | Scenario references and test assertions | Offline socket denial, restart scan, safe-off and expected error log messages; target procedure in PI_VALIDATION.md |
| tests/fixtures/scenarios.json state_event | SQL system_events seed / contract review | Proposed event envelope, not a runtime logger |
| Existing check_integration.py | 10 existing unittest cases | Stubbed API/firmware compile/upload and serial behavior; subprocess calls are mocked |
| Existing tests/firmware_behavior.cpp | g++ executable | Real sketch included with stub Arduino APIs; software timers/output settings, not voltages/current |
| Existing verify_live.py | Target Pi only | Sends OFF-only HTTP commands to actual running service; not run here |

Generate a sample database without touching production: `python tests/build_sample_db.py /tmp/phase0-sample.sqlite3`. Builder refuses an existing path and adds image/inference rows using fixture metadata. The new suite creates disposable databases automatically; no runtime SQLite files need to be committed.

Expected logs exercised by fault tests: Alert read failed; ML status read failed; Capture saved but SQL indexing failed; Could not save camera image. Accepted control request could not be logged is an existing logger path requiring an injected repository exception (covered separately in tests). Offline checks deny socket.connect in-process; they do not claim a browser network audit, working ML/database, real unplug/replug or target endurance.
