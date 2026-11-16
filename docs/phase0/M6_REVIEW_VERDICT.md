# M6 review — accepted with restrictions

Recorded 2026-11-16 (America/Chicago). User verdict: **ACCEPTED WITH RESTRICTIONS — HOST-ONLY**, PR #11 at `dc0abc8e2f2eb20029bd3e1f96009fd5902fdf43`. History, CSV export, archive integrity and recovery are accepted for continued host development. This is not production, physical, security or deployment approval.

Evidence: [M6 campaign](../evidence/m6/README.md), tested implementation `1c6f463f285f12419c86bf820c5afb872ac2ec7f`; final-head CI [43888079870](https://github.com/turtle-robotics/GERM/actions/runs/43888079870) and [43888063440](https://github.com/turtle-robotics/GERM/actions/runs/43888063440). Resource quotas, per-process cursors, offline-only fixtures, Windows symlink-test limitation, target filesystem/power-loss/latency, authentication, crop/sensor/electrical, controlled requirements release and retention gates remain as documented in [M6 implementation](M6_IMPLEMENTATION.md).

M7 Task 124 storage/backup/offline restore/retention readiness is authorized on a separate branch from that reviewed SHA, with a separate PR targeting `codex/m6-history-export`. Ordinary host coding and simulated tests may proceed; return for M7 review before M8. Preserve the unmerged #5 → #6 → #7 → #8 → #9 → #10 → #11 → M7 stack, M1 gateway, M2–M6 contracts, source provenance, all previous tests, all 15 original hashes and untracked work.

No real camera/model operation or downloads, hardware activation, firmware flashing, live actuators, production controls, deployment, historical deletion/retention enforcement, Gantt updates or merges. Restore must remain an isolated offline copy and cannot activate a runtime or replace live paths. No physical power-loss or safety certification follows from simulated tests.
