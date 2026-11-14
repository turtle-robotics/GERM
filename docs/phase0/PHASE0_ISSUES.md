# Prioritized follow-up issues

P0 blocks unattended/automatic operation; P1 blocks relevant integration/acceptance; P2 is planned follow-up. These are review-ready issue records, not claims that production work is complete. No people assigned.

## P0-01 [P0] Implement authoritative state and command authorization

app.py direct sends; dashboard state is display-only. Add STARTUP CHECK/DEGRADED/MAINTENANCE/SAFE STOP/E STOP, inhibits and explicit resume. Accept when fault/maintenance/restart tests prove no affected command bypass and transition events retain cause.

Trace: SR-SAF-03, SR-SAF-10, SR-AUT-02, SR-UI-03. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-02 [P0] Approve PCB/controller signal and interlock mapping

GERM-PCB contains headers, not an installed load map. Confirm D2/D8/D3/D6/D9 polarity, driver ratings, E-stop, door, leak and water-level signals with electrical evidence. Accept signed mapping and measured safe-state timing; ten-second communications timeout is not a substitute for faster physical interlocks.

Trace: SR-SAF-01/02/07/10, SR-AUT-02. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-03 [P1] Replace DatabaseUnavailable with reviewed migrations and repository

Implement all eleven entities, foreign keys, UTC/units, WAL/FULL/busy_timeout and short single-writer transactions. Reconcile fixture proposal with SO-2 before production. Accept migration, restart, concurrency, integrity and restore tests.

Trace: SO-2/3, SR-DAT-01/03. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-04 [P1] Isolate repository read/write exceptions

dashboard.py catches alert/ML errors in state but trends/alerts/experiments/captures may raise 500; accepted commands may fail to log. Accept explicit error/unavailable status without false zero alerts, plus failure injection tests.

Trace: SR-DAT-03, SR-UI-02. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-05 [P1] Implement validated sensor quality and reader recovery

reading() labels impossible/nonfinite/future samples fresh; DHT initializes at import. Add bounds/rate/location/period/recovery policies and reader health. Accept failed-sensor identification within two expected periods and documented conservative actuation.

Trace: SR-SAF-10, SR-ENV-01/02/03. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-06 [P1] Verify reproducible Debian 13 install and complete recovery

Partial updater excludes services/CSS/camera/readers and data; exported Raspberry Pi OS dependencies may differ from Debian trixie. Accept clean install, permissions, single camera/serial owner, safe restart and full data restore on target.

Trace: SR-AUT-02, SO-5. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-07 [P1] Implement logging, offline workflows and retention

Deliver state events and ~60 s validated persistence, 90 days of five-minute records, hourly images, 80% warning/pruning with >=30 days images, CSV/image export and queued remote alarms. Add profiles/maintenance UI and measure <=2 s refresh; 72 h missing records <1%.

Trace: SR-DAT-01/02/03, SR-NET-01, SR-UI-01/02/03, SR-AUT-01. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-08 [P1] Recover camera and index durable captures

Monitor camera worker, index saved/recovered JPEGs, scheduled capture and verified metadata/hash/size. Accept SQL failure, disk-full and service-restart cases with one camera owner.

Trace: SO-5, SR-DAT-02/03. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-09 [P2] Integrate local versioned ML with uncertainty handling

Keep MLUnavailable until local artifact is present. Accept <0.70 Uncertain, two abnormal results, image/model linkage, <=250 MB and <=10 s display; separate held-out metric campaign.

Trace: SR-ML-01/02/03. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-10 [P2] Resolve duplicated firmware and legacy assets

Document callers before retirement; ensure normal/rainbow variants share protocol, pins and safety behavior. Accept parity test and removal review without changing main directly.

Trace: Maintainability. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-11 [P1] Define firmware upload failure and serial session policy

firmware_port ignores STOP failure; request IDs wrap without session identity. Accept failed-STOP upload policy, stale/replayed ack and reconnect tests; preserve safe output behavior.

Trace: SR-AUT-02, controller contract. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.

## P0-12 [P1] Constrain control and firmware endpoint exposure

Flask binds all interfaces; control routes are unauthenticated, firmware token is served by local pages and is not operator authentication. Accept documented trusted network boundary or access control before wider deployment.

Trace: Deployment review. Evidence: inspected baseline files; see source manifest. Closure requires linked results, not only code.
