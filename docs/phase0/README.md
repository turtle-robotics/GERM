# Phase 0 baseline and review package

Current M5 host review: [Task 123 implementation](M5_IMPLEMENTATION.md), [model/camera dependency register](M5_DEPENDENCIES.md), above [M4 accepted with restrictions](M4_REVIEW_VERDICT.md). No physical camera/model validation, merge, deployment or M6 approval is implied.

Current M4 host review: [Tasks 129/130 implementation and M5 readiness](M4_IMPLEMENTATION.md), above the [restricted M2/M3 acceptance](M2_M3_REVIEW_VERDICT.md). Older readiness statements below are historical. All PRs remain unmerged.

Current host development: [M1 accepted with restrictions](M1_REVIEW_VERDICT.md); [M2 Task 121](M2_IMPLEMENTATION.md) and [M3 Task 122](M3_IMPLEMENTATION.md) have separate dependent review packages. Earlier proposed/pending statements below are historical. No PR merge or physical/deployment approval is implied.

## Current M0 review entry point (2026-11-15)

The user approved the M0 contracts with restrictions at `3b1d20b` and M1 contract `m0-review-2`. See [recorded verdict](M0_REVIEW_VERDICT.md). The current [M1 implementation and traceability guide](M1_IMPLEMENTATION.md) supersedes historical descriptions of direct control paths. Earlier pending-review statements below describe the pre-verdict package; physical/deployment and unresolved requirements/electrical gates remain open.

Start at [M0_RECONCILIATION.md](M0_RECONCILIATION.md), then [Task 128 checklist](HMI_API_CHECKLIST.md), [provisional official SR snapshot](REQUIREMENTS_BASELINE.json), [SO-2 field audit](SO2_FIELD_AUDIT.md) and [M1 proposed contract/readiness](M1_CONTRACT.md). The November 1 report/logs below remain historical evidence. Current execution results are under `docs/evidence/task-119/` and Task 128 references the same campaign. Contract review is pending; no physical/deployment approval or Gantt completion is implied.

Run the reused suites separately, plus `python -m unittest discover -s tests -p "test_m0.py" -v` from pi_hmi. The M0 simulator models the selected PR #3 software candidate while electrical mapping remains unresolved. All simulated data is synthetic.

This package completes the repository-side Phase 0 deliverables from the uploaded brief and development plan. Baseline Gate remains pending contract review and target evidence. It does not assert Phase 1–7 functionality or physical safety acceptance.

| Deliverable | Evidence |
| --- | --- |
| Assets and source versions | ../../ASSET_INVENTORY.md, ASSET_MANIFEST.csv, SOURCE_BASELINE.json |
| Architecture and boundary ownership | ARCHITECTURE_OWNERSHIP.md |
| Serial, API, event and schema contracts | CONTRACTS.md, SCHEMA_CONTRACT.md, API_ENDPOINTS.json; existing ../../pi_hmi/INTEGRATION.md |
| Configuration and deployment | CONFIGURATION_DEPLOYMENT.md |
| Incomplete implementations | PLACEHOLDER_REGISTER.md |
| Reusable fixtures and executable tests | FIXTURE_CATALOG.md; ../../pi_hmi/tests/ |
| Baseline smoke and target checklist | BASELINE_TEST_REPORT.md, PI_VALIDATION.md |
| Prioritized follow-up issues | PHASE0_ISSUES.md |
| Requirement mapping | REQUIREMENT_TRACEABILITY.md |

Run from pi_hmi: `python check_integration.py` then `python -m unittest discover -s tests -p "test_phase0.py" -v`. Minimal host dependencies are in tests/requirements-host.txt. Firmware host check: `g++ -std=c++11 tests/firmware_behavior.cpp -o /tmp/germ-firmware-test && /tmp/germ-firmware-test`. These commands never flash hardware. CI uses the same host checks.

Gate review: accept the serial/API baseline; approve or revise the proposed fixture schema and event envelope; resolve PCB signal mapping; attach Pi observations. Named individuals and subteam responsibility assignments are out of scope by user instruction. No contract is represented as externally approved.
