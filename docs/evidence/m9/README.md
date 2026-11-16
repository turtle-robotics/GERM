# M9 acceptance, endurance and hardening host evidence

Tested implementation: `8c45f0d6736a5294067c9441b29c25e9e5a2532d`, stacked directly above accepted M8 `e1511c1fa39a155801e5c1855872747c9b78c8f8`. [PR #14](https://github.com/turtle-robotics/GERM/pull/14) targets `codex/m8-offline-usability`. [Recorded M8 verdict](../../phase0/M8_REVIEW_VERDICT.md), [M9 implementation/readiness](../../phase0/M9_IMPLEMENTATION.md), [reliability findings](../../phase0/M9_RELIABILITY_FINDINGS.md), [security review](../../phase0/M9_SECURITY_REVIEW.md), [six-objective/40-SR acceptance matrix](../../phase0/M9_ACCEPTANCE_MATRIX.md), [operator checklist—not executed](../../phase0/M9_OPERATOR_ACCEPTANCE.md). M9 awaits human review; physical and production readiness are not established.

## Exact campaign

All 248 earlier tracked Python checks are retained, with 16 M9 checks for 264 total. Local Windows results explicitly retain two unchanged symlink-privilege skips (M6/M7); POSIX CI runs those checks. Nine preserved untracked root-app checks pass separately locally and are not in GitHub CI. Local g++ is unavailable; CI compiles/runs the actual-sketch C++ harness. CI_RESULTS.json records complete source-head push/PR steps, including the accelerated endurance runner and all seven M1/M4/M5/M6/M7/M8/M9 Chromium workflows. Existing assertions, query/busy/browser limits and the M1 gateway source are unchanged; writer coordination shares the existing busy budget.

HOST_TEST_RESULTS.json records source SHA, exact commands, UTC/platform/Python/packages and source/log SHA-256. The collector recomputes every source hash before copying evidence. All 15 original hashes are independently rechecked unchanged. SOURCE_SECRET_SCAN.json is the empty redacted source-range scan `e1511c1..8c45f0d`. The HTTP/gateway audit also records normalized hashes of unchanged gateway/state/serial/firmware sources.

From the root, run the following sequentially (locally installed dependencies required):

```powershell
.venv/Scripts/python.exe -X utf8 pi_hmi/tests/run_host_checks.py --root-app --output build/m9-complete-evidence
.venv/Scripts/python.exe -X utf8 pi_hmi/tests/m9_endurance.py --hours 72 --output build/m9-complete-endurance/RESULTS.json
```

Then run each of the seven Chromium scripts as in CI, with the existing `GERM_PLAYWRIGHT_MODULE`, optional installed `GERM_TEST_BROWSER` and virtual-environment `GERM_TEST_PYTHON`. Run `browser_m9.cjs` three times with different `GERM_BROWSER_OUTPUT` build subdirectories to reproduce the local repeated campaign. Earlier overlapping development runs remain exploratory artifacts, not final-head pass evidence.

## Accelerated endurance and durability

ENDURANCE_RESULTS.json separates **259,200 simulated seconds (72 hours)** from actual elapsed seconds and explicitly states this was not 72 real elapsed hours or physical endurance. One-second synthetic input/status heartbeats keep the unchanged M1 sensor/controller freshness rules active; deliberately configured hourly synthetic pump pulses and lighting edges still require gateway grants. Exactly 72 saved JPEGs and 72 synthetic inference results are indexed, with duplicate scheduled ticks returning the same image identity. The runner adds exactly 864 five-minute fixture sensor rows; other sensor-quality event rows are counted separately. `good` is fixture quality, with SYNTHETIC sensor dictionary provenance, not a real measurement.

Mid/end strict CSV/JPEG exports and backups verify archive/member hashes, CSV/raw row counts and snapshot provenance. Isolated restores verify SQLite schema/migration/FK/integrity and never attach to runtime or restore permission. Queued media receipts must become committed, every non-STATUS synthetic adapter transition must have gateway dispatch context, and no actuator record may claim physical verification. Artifact count/size are asserted below 1000 files/64 MiB without deletion. Final counts, checks at each hour, artifact hashes, dispatches and actual byte/time observations are retained in the result. Test workspaces are disposable fixtures; no project historical data is involved.

Fault campaigns are separate from the uninterrupted synthetic run: camera/sensor/model loss, slow/failed inference (retained M5 tests), actual disposable DB corruption, ENOSPC/quotas, clock rollback, worker failure, partial/interrupted files and repeated restart remain covered. M9 additionally forcibly terminates a real disposable process after durable running-job claim/partial stage; startup releases/reacquires ownership, preserves the stage/cycle, reports interruption and keeps permissions/schedules off. This is not physical power-loss or filesystem endurance certification.

## Browser and reproducible reliability evidence

Three final-head `browser-run-*` packages each repeat all seven screens four times (84 complete screen visits across three runs), three start/pause cycles (nine total), keyboard/skip/focus/touch/layout, Cancel/Escape, external-origin blocking, localhost loss/no POST replay, DB/core-worker recovery and stale-image hiding. Each also forces an older running response to arrive after paused state and supplies an old Pause preparation revision. Corrected DOM must stay paused and unconfirmed Pause must reach the unchanged safe-stop gateway contract; confirmed Start remains nonce/revision bound. Per-run records include exact source SHA, bounded API/DOM/SQLite/worker timing trace and server output. Three screenshots from the first final run are included.

Development probes are deliberately retained separately:

- BASELINE_REPEATS.json: five accepted-client M8 browser passes before M9 fixes; passing repetition alone did not establish reliability.
- `ordering-before/`: a delayed running response overwrote paused DOM while API remained paused. Corrected poll revisions prevent that ordering defect.
- `pause-revision-before/`: a concurrent worker transition caused supplied Pause revision to be rejected, followed by the 30-second paused wait. Corrected HMI omits only that optional unconfirmed Pause precondition; M1 itself is unchanged.
- `sqlite-busy-before/`: nonblocking trace captured SQLite code 5/database-is-locked during status connection setup, a latched error with the cycle paused, and a safely inhibited host. Read queries now open read-only/query-only connections without writer setup; actual IO failures still inhibit.
- `writer-contention-before/`: a later cycle transition competed with event commits and failed safely with SQLite code 5/HTTP 503. Bounded per-path host writer coordination now shares the configured busy budget; read-only queries/backups stay concurrent and over-budget failure still inhibits.
- `investigation-m6-concurrent-load.txt` and HISTORY_BENCHMARK.json: an overloaded 100,000-row query hit its unchanged three-second deadline. A before/after equal-timestamp benchmark records failure without normalization reuse and a pass with the bounded cache, preserving pagination/high-water semantics. These development measurements are host-specific, not target acceptance.

The first source CI runs at `9c18579` ([push](https://github.com/turtle-robotics/GERM/actions/runs/43950166946), [PR](https://github.com/turtle-robotics/GERM/actions/runs/43950328916)) failed because the new verifier used wrong archive member names; these were corrected to accepted M6 `tables/*.v1.csv` / `provenance/*.jsonl` without relaxing checks. At source `7820a1e`, [push CI](https://github.com/turtle-robotics/GERM/actions/runs/43951532167) passed but [PR CI](https://github.com/turtle-robotics/GERM/actions/runs/43951543265) timed out in the original M4 schedule-save response wait before start/pause. That test's early unhandled wait rejection prevented artifact cleanup; M9 now retains the original rejection/assertion while capturing API/DOM/field-validity/screenshot/server evidence. Five additional local M4 repetitions passed. The schedule-save intermittency and earliest M8 successful-response timeout remain causally unresolved; subsequent green campaigns do not retroactively prove their cause. No failed campaign is labelled a pass.

## Host readiness and unresolved gates

Ready for scoped host review based on the exact campaign; **not physical or production ready**. The official requirements remain provisional with original partial/missing source statuses. Physical geometry/material/water/pressure/light/thermal/E-stop/interlock/calibration, actual 60-day crop/90-day system life, approved crop settings, camera/model/dataset metrics, novice usability and target timing/endurance/power-loss remain open. Production identity/read/download authorization, network/security and HTTP resource bounds require approval; local anonymous reads and trusted Python/filesystem are explicitly documented gaps. Remote alarm delivery/unsent behavior is not implemented. Retention conflict and all deletion remain unapproved.

No Pi deployment/installation, real sensor/camera/model activation/download, firmware flashing, actuator operation, production POST enablement/new exposure, history deletion/retention automation, PR merge or Gantt update occurred. All previous contracts/tests, original files and untracked work remain preserved. Keep #5 → #6 → #7 → #8 → #9 → #10 → #11 → #12 → #13 → #14 open and unmerged, pending explicit review.
