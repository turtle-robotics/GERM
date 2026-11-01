# Phase 0 baseline test report

Assessment date: 2026-11-01. Repository baseline commits and uploaded source hashes are recorded in SOURCE_BASELINE.json. Exact execution environment, UTC timestamp, commands, exit codes and LF-normalized UTF-8 log hashes are in HOST_TEST_RESULTS.json; installed host dependency versions are in host-packages.txt. Target Pi is user-reported Debian 13 trixie. Tests below ran on Windows with Python 3.12 in an isolated workspace environment, not on the Pi.

## Executed host results

| Check | Result | Evidence and scope |
| --- | --- | --- |
| Existing integration suite | PASS, 10 tests | existing-integration.txt; hardware and compiler/uploader are mocked |
| New Phase 0 contract suite | PASS, 24 tests | phase0-contracts.txt; real Flask/services/serial parser plus synthetic physical adapters |
| Flask startup and routes | PASS in controlled host harness | Physical imports replaced before import and background threads disabled; exact route/method catalog checked |
| Missing DB/ML/camera and controller | PASS explicit unavailable behavior | DatabaseUnavailable/MLUnavailable retained, alerts active=null in /api/state, no false physical verification |
| Fault/log behavior | PASS covered paths | Capture indexing/disk failure, alert and ML errors, actuator logging exception; known unhandled repository read exceptions remain issues |
| SQLite review fixture | PASS | Empty→v1, eleven populated entities via builder, constraints/FKs, WAL reader during uncommitted write, ack≠clear, reopen/backup row comparison and integrity; no production DB adapter |
| Camera sample and restart | PASS synthetic JPEG/hash and module reload | No camera device, worker/process restart or power recovery; local JPEG retained when indexing fails |
| Offline case | PASS in-process socket.connect denied | Local pages/state with missing services; no browser/network-disconnect or real DB/ML evidence |
| Sample builder | PASS | Creates new path only; refuses existing path; temporary data only |
| Firmware C++ harness locally | NOT EXECUTED | No host C++ compiler found. Existing uploaded historical pass is not rerun evidence. CI is configured to compile and execute the actual sketch harness |

The added builder test initially exposed a Windows file-handle cleanup failure. Connections were changed to close explicitly; final captured runs above pass. No application runtime behavior was changed except documentation corrections.

## Baseline operational observations and limits

The host harness starts Flask with no physical adapter side effects and serves all seven local screens. It opens no listening TCP port; Flask test_client is in-process. Expected target service/listener is hmi.service/TCP 5000, but installed/enabled state, actual port exposure, germ permissions, GPIO/USB access, camera ownership and deployed package/source drift were not observed. A temporary writable image root and disposable SQLite paths were used, never /var/lib/germ production data.

The inspected source creates one camera instance in app.py and one serial bridge guarded by RLock; runtime exclusivity on Pi is unverified. Ordinary hardware imports may fail before startup if Pi dependencies or GPIO initialization fail. The current production repository and model remain unconfigured. Sensor plausibility/future timestamps are known gaps, deliberately identified by fixtures. Firmware acknowledges software settings, not measured output state.

No live safe-off, controller disconnect/replug, process supervision, electrical timing, E-stop/door/leak/water-level, actual camera, sensor accuracy, Debian install, production migration, clean machine restore, physical offline operation, 72 h endurance or user usability test was executed. PI_VALIDATION.md specifies required target evidence. Ten-second firmware watchdog is source-level behavior until the C++/hardware checks are run; it is not evidence for the matrix's faster safety interlocks.

## Gate decision

Repository-side assets, contract proposals, configuration inventory, placeholder register, reusable fixtures, baseline evidence and prioritized issues are delivered for review. Baseline Gate is OPEN pending producer/consumer contract approval, PCB signal reconciliation and target smoke/hardware evidence. No named subteam assignments are required by the user. Phase 1–7 implementation and requirement-level system acceptance remain separate work; fixture successes do not close those obligations.

Publication status: committed on the local phase0/contracts-assets-fixtures branch. GitHub connector write requests returned HTTP 403. Automatic approval review rejected public Git push because the package includes user-uploaded planning and inventory material. No remote branch, pull request or CI result is claimed; a portable Git bundle, source archive and draft PR description are supplied for review. Public publication awaits explicit confirmation of this content scope.
