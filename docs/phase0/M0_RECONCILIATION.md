# M0 source reconciliation and review decision record

Date: 2026-11-15. Candidate contract version `m0-review-2`. Tasks 119 and 128 are delivered for explicit contract review; this report does not mark the Gantt completed, certify physical safety or approve deployment. The user approved M0 execution and the M0–M9 sequence, but explicitly retained the M0 contract-review gate before M1 development.

## Chosen software candidate

| Input | Pinned revision | Disposition |
| --- | --- | --- |
| Current GitHub main | 8789022415ffb44aca8ff88c4d1ba31f4ef994be | Merged into the M0 feature branch; retains PC simulator from PR #4. |
| PR #2 Phase 0 | 4293db86efcebe92f707230ee778dd8d6ca8a3cc | Merged intact, then updated contracts/catalog/manifest and extended tests/checklist. Historical reports/logs remain dated evidence. |
| PR #3/local source | b84736f7604abf6c2089a7f361b0bf2a795b5613 | Preserved in ancestry. Candidate fan D3/PWM and RGB D5/D6/D9 behavior retained only as source history/software contract, not as an electrically confirmed choice. No firmware pins changed during M0. |
| Deployed Pi source | 22-file SHA-256 manifest matched during read-only Phase 0 | Reused observation in discovery evidence. This identifies those files, not the flashed controller or as-built wiring. No new deployment occurred. |
| Untracked root app/boot/tests | Existing protocol-1 control-only application | Preserved byte-for-byte, excluded from M0 commit/production selection. Hash verification record kept locally; no overwrite/reset. |

The M0 branch is `codex/m0-contract-reconciliation`. Both merges preserve ancestry and do not modify main, PR #2 or PR #3. No claim is made that merging source from #3 closes its electrical review. Do not deploy this candidate until the wiring mismatch is resolved. Reconciliation fixes the simulator to model the selected software candidate's 0–255 fan PWM, including feedback/reset/watchdog behavior; it does not infer wiring from PWM capability.

## Electrical reference and discrepancy register

User-designated [Lucidchart](https://lucid.app/lucidchart/86bcd882-8c25-4b40-a1c4-7b818aa46412/edit?page=0_0) is the intended reference. Browser inspection ended when Computer Use could not confidently verify the Windows browser URL; no bypass was attempted. The user supplied the [electrical screenshot deck](https://docs.google.com/presentation/d/1hlEVInu-LpOkdN61Ud107CVMvaIauQz7/edit) as an alternative. Drive metadata: `GERM Electrical Schematic.pptx`, modified 2026-11-08T03:02:46.382Z. Slide 2 explicitly says Updated 11/7/26; its image is `ppt/media/image5.png`. Slide 1 is dated October 2; slides after the OLD SCHEMATICS divider are historical, even where an older slide says NEW DIAGRAM CHECK FIRST. The original deck and extracted images remain local/ignored; no invitation URL/token is published.

The following are visual trace observations from slide 2, not a verified netlist or physical continuity test:

| Signal | November 7 screenshot observation | Source conflict / remaining decision |
| --- | --- | --- |
| Red LED driver | D3 appears connected to red MiniPuck dimming input | Main uses red D3; PR #3 uses D3 for fan and D5 for red. Confirm net/color, dimming polarity/voltage and actual wiring. |
| Green / blue | D6 / D9 appear connected to green / blue driver dimming | Pin numbers align with both RGB variants; polarity still needs electrical confirmation. |
| White | D10 appears connected to white MiniPuck dimming | Both current firmware variants report white_channel=false and reject nonzero W. Confirm installed white hardware and required control. |
| Variable power supply DIM+ | D5 appears connected to DIM+; fans and Peltier share its supply | Neither dedicated fan D2 nor PR #3 fan D3 describes this topology. Confirm whether supply dimming controls cooling/Peltier together, safe states, limits and actuator names. Do not call it a verified independent fan channel. |
| Pump | D8 appears connected through resistor/MOSFET gate network | Both variants use D8. Confirm actual driver/polarity, flyback, off behavior and independent interlocks. |
| DHT data | D12 appears wired to DHT11 | Current software acquires DHT11 from Pi GPIO4, not Uno D12. Confirm actual location/interface; no fake replacement readings. |
| E-stop/interlocks | E-stop is shown in supply path; no verified software-feedback/door/leak/level map established | Confirm signal identities, active levels, expected update periods and independent stop/reset behavior. A diagram does not establish measured safety timing. |

**Electrical confirmation required before hardware-dependent integration:** pin/load/net map, dimming polarity, supply-control semantics and independent fan availability, white-channel installation, DHT acquisition owner, sensor/interlock input map, safe states and feedback provenance. M1 pure symbolic state/permission tests can proceed only after contract review and do not need a pin selection.

## Provisional requirements identity and unresolved policy

[REQUIREMENTS_BASELINE.json](REQUIREMENTS_BASELINE.json) snapshots the current official `PO-SR Matrix`, spreadsheet `1kSyYpYcDUr8cOaF3OiD30v9o_b0VQY4fkpBZvLmSCYU`, tab ID 177980321, source last modified 2026-10-02T16:47:26.088Z, retrieved November 15. All 40 unique SR rows, official wording, source evidence status, verification method and open action are preserved. Local snapshot version: `M0-provisional-2026-11-15`; content hash is recorded in the test/source evidence. No numeric native revision was exposed by the metadata used. This is not an invented official version number.

The user explicitly authorized that matrix as provisional. A signed controlled baseline release is still not established. SRS says Proposed, while task-4 tracker completion and its older brief differ. Requirements/evidence approval and implementation approval remain separate.

Retention conflict remains OPEN: SR-DAT-02 asks for warning at 80% and deleting oldest images while preserving >=30 days; SO-5 protects active-experiment images and asks for archive/export. User prohibits historical-data deletion without explicit authorization. Decision required: approved precedence/policy for active experiments, protected evidence and minimum retention, followed by explicit authorization for any production prune action. M0 performs no deletion. M7 can implement warning/export/dry-run and disposable-fixture retention tests first.

Cadence proposal for later review: 60-second validated sensor rows plus complete five-minute operating snapshots, 30-minute routine image captures, immediate fault/command/system events. This covers the distinct SO-5 recommendations and SR minimum records/images without equating HMI polling with persisted cadence. No production scheduler exists in M0.

## Task 119 / 128 delivery map

| Required output | Reused/completed artifact |
| --- | --- |
| Current assets and runtime authority | ASSET_INVENTORY.md, ASSET_MANIFEST.csv, ARCHITECTURE_OWNERSHIP.md; original inventory transcription retained |
| Serial/API/event/sensor boundaries | CONTRACTS.md, API_ENDPOINTS.json, INTEGRATION.md; M1_CONTRACT.md lists every command path and proposed additions |
| Schema/design audit | SCHEMA_CONTRACT.md and SO2_FIELD_AUDIT.md; fixture remains explicitly non-production |
| Configuration and deployment | CONFIGURATION_DEPLOYMENT.md, PI_VALIDATION.md; read-only Pi observation referenced without new operational actions |
| Placeholders / decisions | PLACEHOLDER_REGISTER.md, PHASE0_ISSUES.md, this register |
| Fixtures / baseline tests | Existing tests, schema/seed/JPEG and catalogs reused; deterministic simulator/contract tests added |
| All seven screens, fields, commands, errors, units, quality, inhibits, confirmations and cases | HMI_API_CHECKLIST.json (authoritative structured rows), HMI_API_CHECKLIST.md (review table), API_ENDPOINTS.json (current success/error models) |
| Evidence / planned work | BASELINE_TEST_REPORT.md current supplement, m0 evidence/results, M1_CONTRACT.md exact increments/readiness |

## Review gate

Automated checks can verify route/schema/checklist/fixture contracts; they cannot supply producer/consumer or electrical approval. M0 contract review must explicitly accept the current contracts and proposed M1 boundary or record requested changes. Until that review passes, M1 is prepared but not started. Hardware acceptance, firmware/deployment authorization, destructive data actions and Gantt updates remain blocked independently.

- [ ] Accept reconciliation/source disposition with electrical mismatch visible.
- [ ] Accept Task 128 field/workflow/error checklist and current versus missing API distinction.
- [ ] Accept serial/request/ACK/physical-state and proposed M1 gateway/event/sensor contracts.
- [ ] Accept provisional SR snapshot identity; locate actual controlled release when available.
- [ ] Keep retention decision and all physical/deployment restrictions open.
- [ ] Record review verdict/authority/date and reviewed commit before starting M1.
