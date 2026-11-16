# Integration readiness — proposal for human review

2026-11-16. **M0–M9 accepted for host-only development; physical and production readiness NOT established.** Authority: [M9 final verdict](M9_REVIEW_VERDICT.md), reviewed `8027b9f5b424aa5fc226ea4c3897ee3e2fbfdab3`. This local documentation package does not change GitHub/Gantt status, merge/publish PRs, connect to the Pi or install/start/stop any target software. It proposes future work for separate authorization.

## Readiness package

| Item | Review artifact |
| --- | --- |
| Exact PR #5–#14 bases/heads, dependencies, changed files/blobs, reviewed-head deltas and v1–v8 migrations | [Stack audit](integration-readiness/STACK_AUDIT.md), [machine-readable snapshot](integration-readiness/STACK_AUDIT.json) |
| Per-milestone evidence and twenty observed exact-head CI runs; open reliability findings | [Evidence coverage](integration-readiness/EVIDENCE_COVERAGE.md), [metadata](integration-readiness/EVIDENCE_COVERAGE.json) |
| Human-authorized merge train and non-destructive code/data rollback proposal | [Merge/rollback procedure](integration-readiness/MERGE_ROLLBACK_PROPOSAL.md) |
| Every one of the 40 SRs assigned to a proposed accountable owner group, with exact metrics/actions/evidence | [Physical integration checklist](integration-readiness/PHYSICAL_INTEGRATION_CHECKLIST.md), [structured checklist](integration-readiness/PHYSICAL_INTEGRATION_CHECKLIST.json) |
| Minimum approvals by connection/commissioning stage | [Approval gates](integration-readiness/APPROVAL_GATES.md) |
| Isolated Pi staging, deployment, rollback and supervised commissioning evidence — not executed | [Pi deployment/commissioning plan](integration-readiness/PI_DEPLOYMENT_COMMISSIONING_PLAN.md) |
| Local documentation validation and preservation evidence | [Validation results](integration-readiness/VALIDATION_RESULTS.json) |

## What the audit establishes

Main was observed at `8789022415ffb44aca8ff88c4d1ba31f4ef994be`. PRs #5–#14 are open/unmerged, with adjacent bases matching the preceding heads. API mergeability was clean at observation; this is neither branch-policy approval nor assurance about a later merge. The read is a non-atomic multi-request snapshot; exact refs must be re-read before approval/execution.

Current heads differ from named review commits for #5, #6, #8 and #9, exclusively in documentation. Every file is listed; human merge authorization must acknowledge those exact current heads. PR #7's 25 path changes correspond to 24 rename-aware changes, including an unchanged baseline-fixture rename into migrations/001_baseline.sql. No source rename is represented as deletion of database history.

All 15 original raw hashes remain equal: eight tracked discovery files and seven untracked root files. These are distinct from 28 intentionally modified files that existed on original main. Those 28 changes and before/after Git blobs are audited, including firmware source; they do not establish a correct electrical mapping or authorize flashing. The root protocol-1 app/boot/deploy artifacts remain untracked and are not selected as the release. All historical evidence/data is preserved; no live Pi data was inspected by this task.

Accepted M9 evidence includes 264 tracked checks, seven Chromium workflows, compiled C++ checks, nine preserved root checks locally, and 72 accelerated hours in 240.9323783 local real seconds. Two Windows symlink skips were covered by POSIX CI. These results do not meet real physical 72-hour endurance, crop/service-life, electrical, calibration, approved-model, novice usability or production-security acceptance. Existing historical pending-review wording in evidence/matrix files is superseded only by the recorded host verdict; their content and hashes are left intact.

## Decisions still required

**REL-01** historical M4 paused-summary wait after a successful Pause response and **REL-02** separate schedule-save response wait remain open. Corrected demonstrated races do not prove all historical causes. A named reliability/validation owner must reproduce/capture and fix or explicitly disposition both before commissioning reliance; no timeout/assertion relaxation or green-run-only closure is proposed.

The PO/SR matrix remains `M0-provisional-2026-11-15`; controlled release/signoff is unresolved. Electrical pins/load topology/polarity, independent safety circuits and sensor ownership/interfaces require as-built approval. Crop timings and real camera/model/dataset approvals are absent. Anonymous local HTTP reads/downloads and production identity/network/Host/Origin/resource boundaries remain security blockers. Remote-alarm delivery/unsent behavior is unimplemented. Storage-retention precedence and protected image/record horizons require a human policy decision; **no deletion is authorized**, even if a policy proposal is accepted.

Current code deliberately supports synthetic host operation and denies physical serial, production POSTs and deployment/firmware operations. It cannot be made hardware-ready by flipping a configuration value. A separately authorized and reviewed physical-adapter/runtime boundary must preserve the single M1 gateway, fresh interlocks, confirmations, persistence failure behavior and conservative restart before hardware connection.

## Requested future decisions, not execution authority

The reviewer may separately approve or revise: (1) exact-SHA merge/retarget strategy and rollback checkpoints; (2) named owners, requirements/deviations and gate evidence; (3) isolated Pi simulation installation only; (4) reviewed physical interface implementation and electrically isolated acquisition; (5) supervised hazardous-load/camera/model commissioning; (6) real endurance/crop and production access. Approval of this readiness report alone should not be interpreted as all six approvals.

No PR merge/retarget/status change, Pi deployment/access, hardware/model/camera activation, flashing, production exposure, historical deletion, retention automation or Gantt update occurred. Original hashes/untracked work and accepted milestone contracts remain preserved.
