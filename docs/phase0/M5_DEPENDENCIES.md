# M5 model / camera dependency register

2026-11-16. Host review only; [M4 restricted acceptance](M4_REVIEW_VERDICT.md). No real model or physical camera is installed/enabled by this package.

| Item | Implemented / supplied | Missing decision or evidence |
| --- | --- | --- |
| Camera ownership | One injectable synthetic owner; no physical imports/start by default; legacy Camera() without adapter fails | Separate physical activation approval, one-owner target implementation, camera identity/mount/lighting/calibration |
| Frame freshness | Explicit UTC/sequence/source; bounded JPEG decode; configurable synthetic five-second age guard; stale/future/corrupt denied | Actual frame rate, source timestamp/monotonic acquisition guarantee and reviewed physical freshness policy |
| JPEG metadata | Decoded dimensions, byte size, SHA-256 and UTC frame time; active experiment, optional verified plant FK | Physical image quality/lighting/geometry and actual plant-position setup; unassigned plant remains explicit |
| File publication | Owned stages and deterministic UUID paths; exclusive atomic Windows rename / POSIX hard-link publication; no overwrite/delete | Target filesystem/link/directory-fsync behavior, disk permissions/capacity and physical power-cut acceptance |
| Persistence | M2 migration 005, transactional image/inference journals and durable M3 outbox; recovery preserves partial/unowned files | Production DB/image archive consistency, scheduling/supervision and storage-retention conflict (M6+); no deletion approved |
| Model artifact | Only an explicitly named local **text fixture**, stating NOT PLANT MODEL WEIGHTS; exact SHA-256 is computed and checked | User-reviewed real weights, versioned manifest/hash/license, training provenance, permitted use, runtime and deployment approval |
| Input/output contract | RGB uint8 HWC, explicit stretch resize/dimensions; complete finite probability vector over unique manifest labels | Real model normalization, preprocessing/geometry, supported runtime and reviewed label semantics |
| Classifications | No real plant classes reviewed. Default mapping absent → uncertain. Positive tests use only fixture_normal / fixture_abnormal and synthetic-fixture review references | Reviewed normal/abnormal classification set for a real model; no inference of meaning from class strings; no diagnoses invented |
| Confidence policy | Below 0.70 → uncertain. Only mapped reviewed fixture labels at/above threshold can count; two consecutive distinct chronologically increasing images; error/uncertain/normal reset | Real model calibration, uncertainty review and actual plant-alert content/channel approval |
| Model performance | Host timeout/single-flight/late-result discard tested; no accuracy assertion | Held-out images, leakage audit, >=50 unique images/class, official balanced accuracy/recall/F1 targets and measured target latency/storage |
| HMI | Synthetic preview marked as such, exact capture metadata/age and unavailable/stale/error/historical inference states | Physical <=2 s update campaign and novice usability/target acceptance |

Physical interfaces, actuators, firmware, production POST controls, deployment, PR merges and Gantt updates remain disabled/unauthorized. M1 remains the sole command gateway; neither camera nor model code has actuator dispatch authority. Crop timings, electrical pin/polarity/sensor interfaces, provisional requirements release, production authentication/network boundary and retention remain unresolved.

Host codec dependency: Pillow **13.0.0** is pinned in both tracked requirement files and recorded in test package versions. Its JPEG identification/verification/full decode APIs are used with an 8 MiB byte cap and 4,000,000-pixel cap before decoding; no model package or weights are downloaded. Implementation references: [Pillow Image API](https://pillow.readthedocs.io/en/stable/reference/Image.html), [Pillow release metadata](https://pypi.org/project/pillow/13.0.0/). Dependency installation is not approval of target performance or physical safety.
