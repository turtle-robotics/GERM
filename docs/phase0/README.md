# Phase 0 baseline and review package

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
