# GERM asset inventory

Reconciled on 2026-11-01 against the two commits in [source baseline](docs/phase0/SOURCE_BASELINE.json). The supplied inventory is reused in full in [its transcription](docs/phase0/UPLOADED_ASSET_INVENTORY.md); the current [per-file manifest](docs/phase0/ASSET_MANIFEST.csv) adds exact Git blob versions, purpose, runtime boundary and disposition for every tracked file in both repositories. Nothing is formally retired by this change. Named subteam assignments are intentionally omitted.

## Corrections to the supplied inventory

- GERM main resolves to ba38df7f8fa77c5ea8e947ee46ad179645a32388, not the locally described afce9d1 README state. That absent local edit is not part of this baseline.
- check_integration.py currently defines 10 tests, not three. Current execution evidence is in the baseline report; the uploaded historical firmware pass remains historical only.
- Protocol 2 already implements matched acknowledgements, STATUS, STOP and watchdogs. Firmware reports software output state; there is no independent actuator feedback sensor.
- GERM-PCB contains KiCad project, schematic, board, footprint table and two mounting footprints. It contains no controller firmware or approved load/interlock wiring map. Header nets do not establish an installed actuator mapping.
- SQLite migrations, production schema, backup/export, state manager, sensor plausibility rules, schedules and alert pipeline are absent. Fixture SQL is a review contract, not a production adapter.
- DatabaseUnavailable and MLUnavailable remain explicit. E-stop is not_connected; water temperature and A0 are unavailable. No new Pi observations are asserted.
- deploy_to_pi.py is an eight-file partial update and firmware upload helper, not a full install or a consistent data backup.

## Deliverables

See [Phase 0 index](docs/phase0/README.md), [configuration inventory](docs/phase0/CONFIGURATION_DEPLOYMENT.md), [placeholder register](docs/phase0/PLACEHOLDER_REGISTER.md) and [baseline report](docs/phase0/BASELINE_TEST_REPORT.md). New Phase 0 docs and test assets are owned by their functional contract boundaries in the architecture map; approval remains pending review.
