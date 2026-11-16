# M9 acceptance matrix

Version `m9-host-review-1`. All six objectives and 40 system requirements retain exact official wording and source status in [structured matrix](M9_ACCEPTANCE_MATRIX.json). Baseline `M0-provisional-2026-11-15`; controlled approval is unresolved. Source statuses remain unchanged; no row is declared physically or production accepted. Source-linked manual evidence is recorded as a claim, not independently accepted evidence.

| Objective | Official wording | Linked requirements |
| --- | --- | --- |
| PO-1 | Complete a defined herb grow cycle. | SR-PLT-01, SR-PLT-02, SR-PLT-03, SR-PLT-04, SR-WAT-02, SR-LGT-01, SR-SAF-09 |
| PO-5 | Protect users, plants, and electronics through fail-safe design. | SR-PLT-03, SR-ENV-03, SR-AUT-02, SR-SAF-01, SR-SAF-02, SR-SAF-03, SR-SAF-04, SR-SAF-05, SR-SAF-06, SR-SAF-07, SR-SAF-08, SR-SAF-09, SR-SAF-10 |
| PO-2 | Operate autonomously with controlled resource delivery. | SR-PLT-04, SR-WAT-01, SR-WAT-02, SR-WAT-03, SR-LGT-01, SR-ENV-01, SR-ENV-02, SR-ENV-03, SR-AUT-01, SR-AUT-02, SR-NET-01 |
| PO-3 | Monitor, store, and interpret system and plant-health data. | SR-ENV-01, SR-ENV-02, SR-DAT-01, SR-DAT-02, SR-DAT-03, SR-UI-02, SR-ML-01, SR-ML-02, SR-ML-03, SR-NET-01, SR-SAF-10 |
| PO-4 | Be usable and maintainable by a first-time operator. | SR-UI-01, SR-UI-02, SR-UI-03, SR-ML-03, SR-SAF-03, SR-MNT-01, SR-MNT-02, SR-MNT-03, SR-MNT-04 |
| PO-6 | Provide a reusable and serviceable product across multiple crop cycles. | SR-MNT-01, SR-MNT-02, SR-MNT-03, SR-MNT-04, SR-LIF-01, SR-LIF-02, SR-LIF-03 |

| SR | Source status | Implementation / automated evidence | Remaining acceptance gate |
| --- | --- | --- | --- |
| SR-PLT-01 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-PLT-02 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Profiles/cycles only; 60-day biological survival/size demonstration absent |
| SR-PLT-03 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-PLT-04 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-WAT-01 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-WAT-02 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-WAT-03 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [m9_endurance.py](../../pi_hmi/tests/m9_endurance.py) | Synthetic schedules do not measure 72-hour reservoir reserve |
| SR-LGT-01 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Synthetic timing only; approved crop settings, PPFD and photoperiod measurement absent |
| SR-ENV-01 | PARTIAL | [sensor_policy.py](../../pi_hmi/services/sensor_policy.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | No approved canopy interface/calibration or five-minute thermal alarm acceptance |
| SR-ENV-02 | PARTIAL | [sensor_policy.py](../../pi_hmi/services/sensor_policy.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | No approved RH interface/calibration or ten-minute band alarm acceptance |
| SR-ENV-03 | PARTIAL | [state_service.py](../../pi_hmi/services/state_service.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | Electronics sensor/thermal loads and independent cutoff unresolved; target load test absent |
| SR-AUT-01 | PARTIAL | [host_lifecycle.py](../../pi_hmi/services/host_lifecycle.py) / [m9_endurance.py](../../pi_hmi/tests/m9_endurance.py) | 72 accelerated synthetic hours are not 72 real elapsed hours or unattended physical endurance |
| SR-AUT-02 | MISSING | [restart_service.py](../../pi_hmi/services/restart_service.py) / [test_m8.py](../../pi_hmi/tests/test_m8.py) | Software inhibition/recovery only; electrical de-energization and target two-minute startup unverified |
| SR-DAT-01 | PARTIAL | [sqlite_repository.py](../../pi_hmi/services/sqlite_repository.py) / [test_m8.py](../../pi_hmi/tests/test_m8.py) | Local synthetic contracts only; Pi installation and approved local model remain gated |
| SR-DAT-02 | PARTIAL | [storage_service.py](../../pi_hmi/services/storage_service.py) / [test_m7.py](../../pi_hmi/tests/test_m7.py) | Retention conflict unresolved: 90-day records/hourly images versus 80% cleanup preserving 30-day images; automatic deletion prohibited |
| SR-DAT-03 | PARTIAL | [event_service.py](../../pi_hmi/services/event_service.py) / [m9_endurance.py](../../pi_hmi/tests/m9_endurance.py) | Synthetic provenance/records only; physical cadence/missing-record rate and unavailable inputs require target evidence |
| SR-UI-01 | PARTIAL | [host_lifecycle.py](../../pi_hmi/services/host_lifecycle.py) / [browser_m9.cjs](../../pi_hmi/tests/browser_m9.cjs) | Five novice users/orientation/task timing/error acceptance not performed |
| SR-UI-02 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [browser_m9.cjs](../../pi_hmi/tests/browser_m9.cjs) | Synthetic UI only; physical readings, target refresh latency and touch usability unverified |
| SR-UI-03 | PARTIAL | [command_service.py](../../pi_hmi/services/command_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Host confirmations/profiles only; crop timings and physical controls require approval |
| SR-ML-01 | PARTIAL | [local_ml_service.py](../../pi_hmi/services/local_ml_service.py) / [test_m5.py](../../pi_hmi/tests/test_m5.py) | Synthetic adapter only; approved model/runtime, target size and ten-second performance absent |
| SR-ML-02 | PARTIAL | [model_contract.py](../../pi_hmi/services/model_contract.py) / [test_m5.py](../../pi_hmi/tests/test_m5.py) | No approved model, held-out dataset, measured accuracy/recall/F1 or leakage audit |
| SR-ML-03 | PARTIAL | [local_ml_service.py](../../pi_hmi/services/local_ml_service.py) / [test_m5.py](../../pi_hmi/tests/test_m5.py) | Rules tested for reviewed synthetic labels only; plant classifications/models remain unapproved |
| SR-NET-01 | PARTIAL | [host_lifecycle.py](../../pi_hmi/services/host_lifecycle.py) / [test_m8.py](../../pi_hmi/tests/test_m8.py) | Offline host only; remote channel delivery/unsent alarm queue not implemented or authorized |
| SR-SAF-01 | MISSING | [state_service.py](../../pi_hmi/services/state_service.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | Reporting/latching only; physical E-stop removal within one second requires electrical verification |
| SR-SAF-02 | MISSING | [command_service.py](../../pi_hmi/services/command_service.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | Normalized synthetic door only; wiring/polarity and 0.5-second pump cutoff unverified |
| SR-SAF-03 | MISSING | [grow_service.py](../../pi_hmi/services/grow_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Synthetic maintenance boundary only; hazardous physical loads and human confirmation acceptance remain open |
| SR-SAF-04 | MISSING | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-SAF-05 | MISSING | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-SAF-06 | MISSING | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-SAF-07 | PARTIAL | [command_service.py](../../pi_hmi/services/command_service.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | Normalized leak inhibition only; two-second cutoff/500mL physical containment test absent |
| SR-SAF-08 | MISSING | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-SAF-09 | MISSING | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-SAF-10 | MISSING | [sensor_policy.py](../../pi_hmi/services/sensor_policy.py) / [test_m1.py](../../pi_hmi/tests/test_m1.py) | Synthetic validation only; approved interfaces/policies, actuator fallback and target fault deadlines unresolved |
| SR-MNT-01 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Maintenance trace only; seven-day interval and 15-minute human task unverified |
| SR-MNT-02 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Maintenance trace only; flow baseline, 14-day interval and 30-minute service acceptance unverified |
| SR-MNT-03 | PARTIAL | [grow_service.py](../../pi_hmi/services/grow_service.py) / [test_m4.py](../../pi_hmi/tests/test_m4.py) | Maintenance trace only; cleaning procedure/90-day interval/60-minute acceptance unverified |
| SR-MNT-04 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-LIF-01 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |
| SR-LIF-02 | PARTIAL | [host_lifecycle.py](../../pi_hmi/services/host_lifecycle.py) / [m9_endurance.py](../../pi_hmi/tests/m9_endurance.py) | 72-hour accelerated software run is not the required 90-day no-replacement system simulation |
| SR-LIF-03 | PARTIAL | Physical/manual only | Physical/material/service-life inspection or test required; software simulation does not establish this requirement |

Cross-cutting [security review](M9_SECURITY_REVIEW.md), [operator acceptance checklist](M9_OPERATOR_ACCEPTANCE.md), [test evidence](../evidence/m9/README.md). Provisional requirements, physical measurements, approved model/crop settings, production security and retention remain gated.
