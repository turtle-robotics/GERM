# GERM implementation evidence index

Current M4: [HMI/profile/cycle/schedule evidence](m4/README.md), [implementation/traceability/M5 readiness](../phase0/M4_IMPLEMENTATION.md). Host-only; the M0→M4 PR dependency stack remains unmerged and no Gantt status changes are implied.

M2/M3 host review: [Task 121 migration/recovery evidence](m2/README.md), [Task 122 logging evidence](m3/README.md), [implementation plan/dependencies](../phase0/M2_M3_PLAN.md). M1 was accepted with restrictions at `99a42a2`; PRs #5 → #6 → #7 → M3 remain separate and unmerged. No Gantt status changes.

Current M1 host review: [implementation, restrictions and traceability](../phase0/M1_IMPLEMENTATION.md), [test package](m1/README.md). M0 was approved with restrictions at `3b1d20b`; [recorded verdict](../phase0/M0_REVIEW_VERDICT.md). The pending-review statuses below are historical. No Gantt status is changed. Current Task 128 structured checklist has 45 rows after adding the M1 confirmation contract.

M0 candidate: `codex/m0-contract-reconciliation`; tested implementation commit `ef363dc5bdba9b75f5e41a77f450a34c5a53c5ac`. Review PR: [#5](https://github.com/turtle-robotics/GERM/pull/5), open against main. Evidence commit `e13dca2d880b3c80c191e2631283782b0ddf6106` passed [CI run 43759399482](https://github.com/turtle-robotics/GERM/actions/runs/43759399482), including Python suites and compiled C++ firmware harness; [step readback](task-119/CI_RESULTS.json). Later evidence-only commits do not change tested runtime/fixture code. This index is not a Gantt completion update.

| Task | Evidence package | Status |
| --- | --- | --- |
| 119 | [Contracts, assets, fixtures and host results](task-119/README.md) | Repository deliverables ready; contract review pending |
| 128 | [Seven-screen/API checklist](task-128/README.md) | 44 rows complete for review; behavior acceptance remains open |
| 12/120 | [M1 exact plan/contract/readiness](../phase0/M1_CONTRACT.md) | Prepared only; development awaits M0 contract-review verdict |

Existing Phase 0 [PR #2](https://github.com/turtle-robotics/GERM/pull/2) and pin/PWM [PR #3](https://github.com/turtle-robotics/GERM/pull/3) are preserved in candidate ancestry; neither is merged/closed by this work. Electrical mapping/polarity, controlled SR release and storage-retention decision remain unresolved. Deployment, firmware flashing, physical tests, historical-data deletion and Gantt changes remain unauthorized.
