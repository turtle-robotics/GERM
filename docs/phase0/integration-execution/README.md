# GERM integration execution and Pi readiness

Observed 2026-11-17T00:12:05.409292+00:00. This report records actual operations; the original readiness package at `551ff294afff39c2237bb7a2bd9ca4addb5109f8` remains a historical proposal. The user's subsequent direct chat authorization explicitly permits exact-head merge commits and retarget operations for #5â€“#14, plus a separate documentation PR. That authorization supersedes G0 no-merge statements in the historical package only for these operations. It does not authorize Pi installation, hardware, production, Gantt changes or historical deletion.

## GitHub execution

Journal status: **blocked**; verified merges: **7/10**. Every merge below preserves its source branch, has the previous main as first parent and approved head as second parent, and has an identical tree to that approved head. Retargeted PR diffs were checked unchanged with equivalent old/new base trees. Fresh immutable-head CI and predecessor main CI must pass before each next merge. No squash, rebase, force push, branch deletion, protection override or administrative bypass was used. Existing Git credential was used because the GitHub connector returned HTTP 403 for writes. Repository policies were read; no protection/rulesets were changed.

| PR | Approved source head | Actual merge | Verified tree | Rollback checkpoint |
| --- | --- | --- | --- | --- |
| [#5](https://github.com/turtle-robotics/GERM/pull/5) | `d93b7bbdff5d5c319d1bd2a8b0f4e1425e22620c` | `5ee6228cd6b6c3c28847a9007ff2c27a47bc955e` | `c49138dea96709779cc063be72759ecff6d868b5` | `8789022415ffb44aca8ff88c4d1ba31f4ef994be` |
| [#6](https://github.com/turtle-robotics/GERM/pull/6) | `3951173ca087c1ce3bfc18526bbec05f97021a05` | `79927b18754c63e0b79d134e00d4fbdfb7d12034` | `c0f664eb820fe64f6dcb5b07e4d83f6cb0fd3ef3` | `5ee6228cd6b6c3c28847a9007ff2c27a47bc955e` |
| [#7](https://github.com/turtle-robotics/GERM/pull/7) | `07a367b52c10d940e757bb593ad9f1e6eae52e44` | `062bf256c6edda1922267643852841b9bb70a85f` | `03ec114f236450443ffa5d7787c5f4206449918e` | `79927b18754c63e0b79d134e00d4fbdfb7d12034` |
| [#8](https://github.com/turtle-robotics/GERM/pull/8) | `cc052957e8761cda3d848eed3cec4e5b0d60f38b` | `5de81b195a683dc27e1858d26eb39af47870aa92` | `089f95054fe3a7a50d090c3a52673a1e42d64f33` | `062bf256c6edda1922267643852841b9bb70a85f` |
| [#9](https://github.com/turtle-robotics/GERM/pull/9) | `1a7090d7c3cc5daf0ac002f74250dba5efdb66e4` | `91447920fa052928190174307f55b59c6db14e2c` | `2e4a5feeae8968b392aa0b871dcd11f0f1ac8c5a` | `5de81b195a683dc27e1858d26eb39af47870aa92` |
| [#10](https://github.com/turtle-robotics/GERM/pull/10) | `2d73aebb88378ce46ac67859e91ad90b75593ad2` | `b574f7e9ba0a95a6c3dbf1d55a721a46733edabe` | `038d9ce75d3b999fe50a842d1f7c05748560fcb2` | `91447920fa052928190174307f55b59c6db14e2c` |
| [#11](https://github.com/turtle-robotics/GERM/pull/11) | `dc0abc8e2f2eb20029bd3e1f96009fd5902fdf43` | `713800931a5926abd8c9c5d57669c124c54dac42` | `e28a65b3c5b9a558246092b3b53d72fed40e4268` | `b574f7e9ba0a95a6c3dbf1d55a721a46733edabe` |

## Integration blocked: mandatory human review

PR #11 main CI [43984868691](https://github.com/turtle-robotics/GERM/actions/runs/43984868691) failed in the unchanged M4 paused-summary 30-second wait. Main is `713800931a5926abd8c9c5d57669c124c54dac42`, accepted M6 tree `e28a65b3c5b9a558246092b3b53d72fed40e4268`. PRs #12–#14 remain open on their original bases, unretargeted/unmerged. The worker exited, no failing CI was rerun and no rollback occurred. Python checks through M6 and C++ passed; later browser steps were skipped. Read [failure findings](CI_FAILURE_FINDINGS.md) and the hash-verified artifact manifest. The HTTP-409 observation is not proof of every historical cause. No completed M9 integration or deployment readiness is claimed.

Human disposition is required before resuming, changing a gate/head, or reverting. The separate documentation PR targets `codex/m9-acceptance-hardening` so its diff is documentation only and includes the authorized readiness commit 551ff29. Do not merge it while this integration sequence is blocked. Original readiness no-merge statements remain historical, with only the explicitly authorized G0 operations superseded.

## Automated evidence

The separate clean-worktree ten-merge rehearsal finished at `415d1010649e8428d24f229bbff14f5d0fd139e4`, tree `77a3abdbbcacbdea0d1ab8a892ecb41c332a34d5`, identical to accepted M9 `8027b9f5b424aa5fc226ea4c3897ee3e2fbfdab3`. Its full campaign passed: 264 tracked checks (two Windows symlink-privilege skips covered by exact-tree POSIX CI), all seven Chromium workflows, actual Arduino-sketch C++ mock-I/O harness compiled/run with existing local WSL g++, and 72 accelerated synthetic hours in 116.228921300004 real seconds. Nine preserved untracked root-app checks also passed. No firmware/device operation was involved. Initial Windows checkout EOL conversion broke a raw requirements hash; restoring exact reviewed Git blob bytes in the isolated worktree resolved it without source/test/hash/assertion changes. Original failure artifacts remain retained.

Historical REL-01 paused-summary and REL-02 schedule-save intermittency remain OPEN; green runs do not close them. Simulation is neither 72 real elapsed hours nor physical/security/production acceptance.

Raw local evidence is under `build/integration-run/`: `GITHUB_INTEGRATION_JOURNAL.json`, `CI_OBSERVATIONS.jsonl`, `PREMERGE_REHEARSAL_GATE.json`, `REHEARSAL.json`, `CHECKOUT_BYTE_FIDELITY.json`, `CPP_RESULTS.json` and policy records. Full host/browser/endurance artifacts remain in the managed rehearsal worktree. Each stage's CI URLs are retained in the journal. All 15 original hashes and seven original untracked root entries remain unchanged.

## Raspberry Pi status and installation hold

Read-only SSH inventory verified the existing target identity. Pi 4 Model B Rev 1.2, Debian 13 aarch64, Python 3.13.5, approximately 43 GiB free at observation. Existing HMI listens on all interfaces port 5000 and has an active GPIO4 DHT helper; neither was stopped/restarted/changed. Firewall verification is incomplete. No Arduino was detected; firmware identity is unknown. Installed camera utility enumeration returned `No cameras available!`; no frames, overlay or driver changes occurred. Sensor helper presence does not establish calibrated sensor quality.

No Pi backup, test installation, service creation or runtime validation has been performed. Target installation approval is still required by the user's Phase 4 instruction. The prepared plan requests a new private preservation directory and immutable synthetic release under `/home/germ/germ-m9-test`, isolated fresh data, offline hashed dependencies, device-denied non-autostart transient service, loopback 127.0.0.1:5055 and optional local SSH forwarding. Exact immutable source remains M9 `8027b9f5b424aa5fc226ea4c3897ee3e2fbfdab3`. No existing deployment or database is adopted. Backup must complete and independently verify before installation. Full local plan: `build/integration-run/PI_STAGING_APPROVAL_PLAN.json`; inventory: `PI_INVENTORY_REPORT.md` and JSON observations. No off-device historical copy is authorized.

## Rollback and remaining gates

Source rollback requires a separately reviewed corrective revert PR, reverse dependency order where necessary, with explicit mainline and preserved checkpoints above. Never reset/force-push main, downgrade a database or overwrite history. No rollback is executed here. Proposed test-install rollback stops only the specifically approved new transient unit and retains all new release/data/evidence/backup paths; old services remain unchanged.

G1 target backup/install remains pending. G2 requires named electrical/safety, sensor/metrology, software safety, security/data/deployment and validation approval for the exact physical boundary and hardware; current host guards must not be bypassed. G3 per-load supervised commissioning, G4 camera/model/crop approval, G5 real endurance/production and retention decisions remain unresolved. Requirements remain provisional. Proposed source changes and tests are in the accompanying physical boundary proposal; no physical adapter is implemented or activated. No models, electrical pins/polarity, crop values or safety outcomes are invented.
