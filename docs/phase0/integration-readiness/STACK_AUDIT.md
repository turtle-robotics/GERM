# Read-only PR stack audit

Snapshot UTC: 2026-11-16T22:27:06.803463+00:00. Exact source/objects/file changes and preserved-hash evidence: [STACK_AUDIT.json](STACK_AUDIT.json). No GitHub or Gantt status was changed. All ten PRs are open/unmerged; observed mergeability is informational, not merge permission. Main remains `8789022415ffb44aca8ff88c4d1ba31f4ef994be`.

| PR | Base ref / exact SHA | Head ref / exact SHA | Changed files | Review delta files |
| --- | --- | --- | --- | --- |
| [#5](https://github.com/turtle-robotics/GERM/pull/5) | main<br>`8789022415ffb44aca8ff88c4d1ba31f4ef994be` | codex/m0-contract-reconciliation<br>`d93b7bbdff5d5c319d1bd2a8b0f4e1425e22620c` | 76 (API 76) | 2 |
| [#6](https://github.com/turtle-robotics/GERM/pull/6) | codex/m0-contract-reconciliation<br>`d93b7bbdff5d5c319d1bd2a8b0f4e1425e22620c` | codex/m1-state-permissions<br>`3951173ca087c1ce3bfc18526bbec05f97021a05` | 54 (API 54) | 3 |
| [#7](https://github.com/turtle-robotics/GERM/pull/7) | codex/m1-state-permissions<br>`3951173ca087c1ce3bfc18526bbec05f97021a05` | codex/m2-sqlite-recovery<br>`07a367b52c10d940e757bb593ad9f1e6eae52e44` | 25 (API 24) | 0 |
| [#8](https://github.com/turtle-robotics/GERM/pull/8) | codex/m2-sqlite-recovery<br>`07a367b52c10d940e757bb593ad9f1e6eae52e44` | codex/m3-durable-events<br>`cc052957e8761cda3d848eed3cec4e5b0d60f38b` | 29 (API 29) | 1 |
| [#9](https://github.com/turtle-robotics/GERM/pull/9) | codex/m3-durable-events<br>`cc052957e8761cda3d848eed3cec4e5b0d60f38b` | codex/m4-grow-hmi<br>`1a7090d7c3cc5daf0ac002f74250dba5efdb66e4` | 43 (API 43) | 1 |
| [#10](https://github.com/turtle-robotics/GERM/pull/10) | codex/m4-grow-hmi<br>`1a7090d7c3cc5daf0ac002f74250dba5efdb66e4` | codex/m5-camera-ml<br>`2d73aebb88378ce46ac67859e91ad90b75593ad2` | 82 (API 82) | 0 |
| [#11](https://github.com/turtle-robotics/GERM/pull/11) | codex/m5-camera-ml<br>`2d73aebb88378ce46ac67859e91ad90b75593ad2` | codex/m6-history-export<br>`dc0abc8e2f2eb20029bd3e1f96009fd5902fdf43` | 48 (API 48) | 0 |
| [#12](https://github.com/turtle-robotics/GERM/pull/12) | codex/m6-history-export<br>`dc0abc8e2f2eb20029bd3e1f96009fd5902fdf43` | codex/m7-storage-backup<br>`55d69c558f5c134540299128aa23f4415550f9fa` | 50 (API 50) | 0 |
| [#13](https://github.com/turtle-robotics/GERM/pull/13) | codex/m7-storage-backup<br>`55d69c558f5c134540299128aa23f4415550f9fa` | codex/m8-offline-usability<br>`e1511c1fa39a155801e5c1855872747c9b78c8f8` | 52 (API 52) | 0 |
| [#14](https://github.com/turtle-robotics/GERM/pull/14) | codex/m8-offline-usability<br>`e1511c1fa39a155801e5c1855872747c9b78c8f8` | codex/m9-acceptance-hardening<br>`8027b9f5b424aa5fc226ea4c3897ee3e2fbfdab3` | 86 (API 86) | 0 |

Every adjacent base equals the preceding PR head, and every base is an ancestor of its head. Preserve dependency order #5 → #6 → #7 → #8 → #9 → #10 → #11 → #12 → #13 → #14. No cherry-picking, rebasing, squashing or branch retargeting is performed.
PR #7 has 25 path changes but 24 rename-aware changes: pi_hmi/tests/fixtures/schema_v1.sql becomes pi_hmi/migrations/001_baseline.sql unchanged (R100). The full JSON retains both views; this is source history, not database deletion.

## Reviewed SHA versus current branch head

Older branches can contain post-review records. The following deltas must be acknowledged in any exact-SHA merge authorization; host milestone acceptance is not automatic approval of a different head.

### PR #5

Reviewed `3b1d20b563af6836d0e3073f7748a5186c6b0af3`; observed head `d93b7bbdff5d5c319d1bd2a8b0f4e1425e22620c`.
- A docs/phase0/M0_REVIEW_VERDICT.md
- M docs/phase0/README.md

### PR #6

Reviewed `99a42a2d3fe9750d35cc309668944f7b5a43a5df`; observed head `3951173ca087c1ce3bfc18526bbec05f97021a05`.
- M docs/phase0/M1_IMPLEMENTATION.md
- A docs/phase0/M1_REVIEW_VERDICT.md
- A docs/phase0/M2_M3_PLAN.md

### PR #7

Reviewed `07a367b52c10d940e757bb593ad9f1e6eae52e44`; observed head `07a367b52c10d940e757bb593ad9f1e6eae52e44`.
No tree difference from the recorded reviewed head.

### PR #8

Reviewed `201a758c6e1c06fa45244ee751c57a4a04f2e6c6`; observed head `cc052957e8761cda3d848eed3cec4e5b0d60f38b`.
- A docs/phase0/M2_M3_REVIEW_VERDICT.md

### PR #9

Reviewed `b4ea9398a9c1b57fc1c7a19993ad2d0c24f28b38`; observed head `1a7090d7c3cc5daf0ac002f74250dba5efdb66e4`.
- A docs/phase0/M4_REVIEW_VERDICT.md

### PR #10

Reviewed `2d73aebb88378ce46ac67859e91ad90b75593ad2`; observed head `2d73aebb88378ce46ac67859e91ad90b75593ad2`.
No tree difference from the recorded reviewed head.

### PR #11

Reviewed `dc0abc8e2f2eb20029bd3e1f96009fd5902fdf43`; observed head `dc0abc8e2f2eb20029bd3e1f96009fd5902fdf43`.
No tree difference from the recorded reviewed head.

### PR #12

Reviewed `55d69c558f5c134540299128aa23f4415550f9fa`; observed head `55d69c558f5c134540299128aa23f4415550f9fa`.
No tree difference from the recorded reviewed head.

### PR #13

Reviewed `e1511c1fa39a155801e5c1855872747c9b78c8f8`; observed head `e1511c1fa39a155801e5c1855872747c9b78c8f8`.
No tree difference from the recorded reviewed head.

### PR #14

Reviewed `8027b9f5b424aa5fc226ea4c3897ee3e2fbfdab3`; observed head `8027b9f5b424aa5fc226ea4c3897ee3e2fbfdab3`.
No tree difference from the recorded reviewed head.

## Changes to original main files

The 15 preserved local/discovery files are a separate sentinel set: all raw working-file SHA-256 values match their original baseline. Root untracked files are not silently treated as release source. The JSON records which sentinels are tracked, their per-head Git blobs, and line-ending-normalized Git equivalence. Files originally tracked on main have intentional software changes, listed below with exact before/after blobs in the JSON. These are not claims of electrical correctness.

- M .gitattributes
- M README.md
- M Showcase LED Display.ino
- M pi_hmi/INTEGRATION.md
- M pi_hmi/README.md
- M pi_hmi/app.py
- M pi_hmi/arduino_program/arduino_program.ino
- M pi_hmi/arduino_serial.py
- M pi_hmi/camera.py
- M pi_hmi/check_integration.py
- M pi_hmi/dashboard.py
- M pi_hmi/deploy_to_pi.py
- M pi_hmi/dht11_reader.py
- M pi_hmi/environment/source-sha256.json
- M pi_hmi/fan_sender.py
- M pi_hmi/firmware_service.py
- M pi_hmi/led_sender.py
- M pi_hmi/requirements.txt
- M pi_hmi/services/camera_service.py
- M pi_hmi/services/ml_service.py
- M pi_hmi/services/sensor_service.py
- M pi_hmi/sim/run_sim.py
- M pi_hmi/static/hmi.css
- M pi_hmi/static/hmi.js
- M pi_hmi/templates/firmware.html
- M pi_hmi/templates/index.html
- M pi_hmi/tests/firmware_behavior.cpp
- M pi_hmi/verify_live.py

## Migration sequence

Current repository VERSION is 8. SQL version 6 is an M5 clock correction, not milestone M6. New empty host fixtures apply v1–v8; existing known schemas verify ledger/checksums, integrity and schema before transactional upgrades with exclusive pre-upgrade backups. Unknown/drifted/future schemas are refused. Current M7 isolated restore accepts only current schema. No live database has been inspected or migrated by this audit.

| Version | File | Introduced in PR | Ledger SHA-256 (normalized text) |
| --- | --- | --- | --- |
| 1 | [001_baseline.sql](../../../pi_hmi/migrations/001_baseline.sql) | #7 | `7a770f9abf31dbdccfe320a51ca2513adabd5dc44095e3d48a81def524daa883` |
| 2 | [002_repository_recovery.sql](../../../pi_hmi/migrations/002_repository_recovery.sql) | #7 | `7e160eecbb3e74e0a877d342225dc70dd9be9136b0bf48ab04167db68088eaed` |
| 3 | [003_event_receipts.sql](../../../pi_hmi/migrations/003_event_receipts.sql) | #8 | `24d294ce5b6c846c15147b822ee220f68c58174e9b4a381e7248f4af53c5ed13` |
| 4 | [004_grow_cycles.sql](../../../pi_hmi/migrations/004_grow_cycles.sql) | #9 | `1fe4b12e7155dd4a12d4237dc6474a9436a3127424728818c64b17a17bf6c459` |
| 5 | [005_camera_ml.sql](../../../pi_hmi/migrations/005_camera_ml.sql) | #10 | `afc83a022683acb2d0cfeeb2a86938db2fa9c1cdd07b6103628dd6491e58c7d3` |
| 6 | [006_camera_clock_guard.sql](../../../pi_hmi/migrations/006_camera_clock_guard.sql) | #10 | `2be0af1e8b90a152f42b1b03a2ebdf10cad29f8e9f602c6351b4e032f18da371` |
| 7 | [007_history_exports.sql](../../../pi_hmi/migrations/007_history_exports.sql) | #11 | `615c9587da69491dd428a1c0df4eee0c4b145e4104e4f17035b8874243e35640` |
| 8 | [008_storage_jobs.sql](../../../pi_hmi/migrations/008_storage_jobs.sql) | #12 | `532f0b436f3ddf2a12410b873b176c7b13a69c05265390ff43b97c25f73b234f` |

Migration statements and blob hashes are in the JSON. Backup completeness, model/image/schema compatibility and rollback data adoption require separate gates; a code rollback is not a database downgrade.
