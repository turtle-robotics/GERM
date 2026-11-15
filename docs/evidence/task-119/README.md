# Task 119 — M0 contract and baseline evidence

Task 119 Phase 0 repository-side deliverables are ready for review. Task 128 shares this campaign. M0 contract-review verdict is PENDING; no SR acceptance, electrical correctness, Gantt completion or deployment approval is asserted.

Implementation/tested code commit: `ef363dc5bdba9b75f5e41a77f450a34c5a53c5ac` on `codex/m0-contract-reconciliation`. This evidence is committed afterward; only documentation/evidence changed after the recorded code test. PR reference is recorded in the repository evidence index after publication.

Inputs: main `8789022`, Phase 0 PR #2 `4293db8`, PR #3/local `b84736f`; merges preserve ancestry. All 15 pre-existing untracked files were verified byte-for-byte unchanged, including the separate root protocol-1 app/tests and prior discovery package. Root app files remain excluded from the release commit. Deployed Pi was not changed or restarted.

Review entry points: [source reconciliation/electrical decisions](../../phase0/M0_RECONCILIATION.md), [contract index](../../phase0/README.md), [schema audit](../../phase0/SO2_FIELD_AUDIT.md), [M1 contract and exact preparation](../../phase0/M1_CONTRACT.md).

## Executed host checks

Reproduce: from the repository root, `python pi_hmi/tests/run_host_checks.py`. Optional `--root-app` includes the preserved local root app if present; it is not part of the committed application. Logs default to ignored `build/m0-evidence`. No device modules are imported by the harness; test processes stub acquisition and firmware subprocesses. Synthetic data never represents installed hardware.

| Check | Result | Evidence |
| --- | --- | --- |
| Existing Pi HMI integration | PASS 12 tests | existing-integration.txt |
| Reused Phase 0 contracts | PASS 24 tests | phase0-contracts.txt |
| New M0 reconciliation/simulator/checklist contracts | PASS 10 tests | m0-contracts.txt |
| Preserved untracked root app | PASS 9 tests | preserved-root-app.txt; protocol-1 FakeDevice only |
| Python syntax | PASS, 22 files parsed without importing hardware | HOST_TEST_RESULTS.json |
| JavaScript syntax | PASS, node --check | javascript-parse.txt |
| Firmware C++ harness locally | NOT EXECUTED | g++ unavailable on host; CI separately required |

Exact timestamp, commands, cwd, Python/platform, source file SHA-256 and log hashes: [HOST_TEST_RESULTS.json](HOST_TEST_RESULTS.json). Dependency versions: host-packages.txt. Total local Python tests: 55 (46 committed Pi/M0 tests + 9 preserved root tests). This is not 55 hardware/acceptance tests.

New coverage: 0–255 PWM including invalid/Unicode inputs and unchanged output on reject; watchdog reset; pump pulse/max duration not extended by STATUS/repeated ON; white rejection/mode behavior; shared firmware copy parity; real serial bridge matching simulator ACK; all seven screens, required Home fields and existing POST routes grounded in the endpoint catalog; all 40 official SR rows retained.

An initial root-directory discovery run of the new suite exposed a module import-path failure. The test now resolves the Pi module directory explicitly. The final logged suite passes. The simulator's former digital-only fan behavior was reconciled with the chosen software candidate, without selecting electrical pins.

## Requirement identity and limitations

Provisional matrix snapshot version `M0-provisional-2026-11-15`, source modified 2026-10-02T16:47:26.088Z. SHA-256 of REQUIREMENTS_BASELINE.json: `117e6ece1f830a83ae80e00de64fb5c2be5c46f8176ccb61e0019ed357381911`. All source PARTIAL/MISSING evidence statuses are unchanged. A controlled baseline approval record remains outstanding.

Electrical screenshot observations do not reconcile to either complete firmware mapping. Pin/polarity/load/sensor/interlock confirmation remains required. Storage deletion versus active-experiment protection remains unresolved and production historical-data deletion is unauthorized. No new production DB, model, state manager, schedules or retention service is claimed.

Pi read-only findings from discovery are retained under docs/discovery/2026-11-15 and clearly distinguished from current host tests. This M0 execution did not flash firmware, send live control commands, energize outputs, restart services, change deployed files, delete history or update Gantt.

## Reviewer checklist

- [ ] Review chosen candidate and all source/electrical discrepancies.
- [ ] Accept current contracts and explicit pending fields; approve/revise proposed M1 single permission boundary.
- [ ] Review Task 128 checklist and SO-2 field/index audit.
- [ ] Review exact host results and separate CI C++ result.
- [ ] Retain requirements-release, electrical, retention, hardware/deployment gates.
- [ ] Record reviewed commit, reviewer/authority/date and contract-review verdict before M1 starts.
