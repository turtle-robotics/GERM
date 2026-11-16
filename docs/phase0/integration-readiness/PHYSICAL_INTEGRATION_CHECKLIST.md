# Owner-grouped physical integration checklist

**PLANNING ONLY — NOT EXECUTED.** All 40 SRs retain exact official wording, source status and provisional baseline identity from [the accepted host matrix](../M9_ACCEPTANCE_MATRIX.json). Host milestone acceptance does not approve the requirements or physical results. Proposed roles below are not named/assigned people. A project owner must appoint each accountable person and approver. [Approval gates](APPROVAL_GATES.md) apply before execution. [Structured checklist](PHYSICAL_INTEGRATION_CHECKLIST.json) retains every field and stop condition.

For each item record a named owner/reviewer, signed procedure/version, configuration and instrument calibration, planned versus actual result, UTC/elapsed timing, raw artifact hashes, deviations and an explicit scope-specific acceptance decision. A checked box in this local document must not update the Gantt or imply permission to energize. Stop on unexpected/unknown state and preserve all evidence.

## Electrical — proposed Electrical lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-SAF-01 — MISSING source evidence status

> GERM shall include a readily accessible, latching red mushroom emergency-stop device. Actuation shall remove power from the pump, grow lights, Peltier device, and other high-power actuators within 1 second. Resetting the device shall not restart equipment until a separate user start command is given.

Action: Approve independent E-stop wiring/reset circuit and a qualified measured cutoff test before any hazardous load commissioning.

Required evidence: As-built circuit, calibrated physical cutoff timing, latch/reset/no-restart observations and signed electrical review.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-02 — MISSING source evidence status

> Opening the front access panel shall stop the pump and mist generation within 0.5 seconds. The pump shall remain inhibited until the panel is closed and the user explicitly resumes operation.

Action: Confirm door circuit, polarity and independent/specified cutoff path; measure pump/mist stop and explicit-resume behavior.

Required evidence: Continuity/interface record, physical cutoff timing, fresh door-state logs and no automatic restart evidence.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-04 — MISSING source evidence status

> An independent hardware thermal cutoff, not dependent on Raspberry Pi or Arduino software, shall de-energize pump, lighting, and thermoelectric loads if electronics-bay air reaches 60 +/-5 deg C. It shall require manual reset after temperature falls below 50 deg C.

Action: Approve independent thermal cutoff and controlled calibrated trip/reset test; software cannot substitute for this circuit.

Required evidence: Circuit/component evidence, measured trip/reset temperatures, physical de-energization and manual-reset record.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-05 — MISSING source evidence status

> Each DC power branch shall be protected by a fuse or resettable breaker rated no higher than 125% of the measured maximum normal branch current and below the current rating of every downstream conductor and connector.

Action: Measure normal branch currents using an approved procedure and verify protection against every downstream conductor/connector rating.

Required evidence: Branch schedule, measured maxima, fuse/breaker ratings, wiring/connector datasheets and qualified signoff.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-06 — MISSING source evidence status

> All wiring and exposed electrical devices inside the wet zone shall operate at 24 VDC or less. AC mains and AC/DC power supplies shall remain in the dry electronics zone, and the complete system shall be supplied from a GFCI-protected outlet.

Action: Inspect wet/dry zoning, supply voltages and GFCI protection under the approved electrical inspection procedure.

Required evidence: As-built zoning/voltage records, supply/outlet ratings, inspection checklist and signed disposition.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Mechanical — proposed Mechanical lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-PLT-01 — PARTIAL source evidence status

> GERM shall support six simultaneous plant positions. Each position shall accommodate a target plant canopy up to 300 mm above the plant deck and 150 mm in diameter while maintaining at least 75 mm clearance from the light source, camera window, walls, and door.

Action: Approve six-position CAD/as-built envelope and measure clearances against the official metric.

Required evidence: Dimensioned drawings, six-position measurements, instrument IDs and photographs.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-PLT-03 — PARTIAL source evidence status

> All wetted structural materials, tubing, seals, and adhesives shall remain functional in nutrient solution from pH 5.5 to 7.5. A 30-day soak test shall produce no cracking, swelling greater than 2%, loss of seal, or visible corrosion that exposes the solution to aluminum.

Action: Approve material/solution compatibility and a controlled 30-day soak procedure; measure dimensional changes and inspect seals/corrosion.

Required evidence: Material lot/datasheets, pH log, before/after dimensions and inspection photographs.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-PLT-04 — PARTIAL source evidence status

> In a 10-minute water-collection test, each of the six root positions shall receive a collected mist volume within +/-20% of the six-position mean, and no position shall remain visibly dry.

Action: Approve and execute a controlled six-position mist-collection test under electrical isolation/supervision appropriate to the procedure.

Required evidence: Ten-minute collected volumes, calculated mean/deviations, dry-position observations and configuration.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-WAT-01 — PARTIAL source evidence status

> The internal water-recycling path shall recover and return at least 90% of the solution discharged during a 60-minute operating test, excluding measured solution retained in tubing and test collectors. No external leak greater than 5 mL shall occur.

Action: Approve a measured collection/return test, accounting for retained tubing/collector solution separately.

Required evidence: Discharge/return volumes, 60-minute duration, external leakage and balance calculation.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-WAT-02 — PARTIAL source evidence status

> All solution returning to the pump shall pass through a removable filter rated at 250 micrometers or finer. After 24 hours of representative mist cycling, nozzle flow shall remain within 90% of its initial value and no nozzle shall be blocked.

Action: Verify filter rating/removability, then compare nozzle flow before and after the approved 24-hour cycling test.

Required evidence: Filter specification, inspection, baseline/final flow per nozzle and blockage observations.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-WAT-03 — PARTIAL source evidence status

> Starting from the normal full level, the reservoir shall support at least 72 hours of the selected mist schedule with at least 20% usable volume remaining.

Action: Approve the selected mist schedule and reservoir measurement method before the real 72-hour reserve demonstration.

Required evidence: Initial/remaining usable volume, calibrated level/volume evidence, schedule, refill and fault logs.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-07 — PARTIAL source evidence status

> A leak sensor or equivalent detection method shall stop the pump within 2 seconds of detecting liquid outside the intended basin. In a 500 mL controlled spill test, no liquid shall contact energized electronics or escape the external containment boundary.

Action: Approve leak/containment test jointly with electrical and sensor owners; controlled spill work remains separately gated.

Required evidence: Containment/spill evidence, measured leak-to-pump-off timing, sensor polarity and dry-electronics observations.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-08 — MISSING source evidence status

> Pump tubing, fittings, nozzles, and pressure-bearing seals shall be rated for at least 150 psi. The assembled plumbing shall withstand 125 psi for 10 minutes with no rupture, fitting movement, or leak greater than one drop per minute.

Action: Verify pressure-bearing ratings and approve a guarded pressure-test procedure before testing the assembled plumbing.

Required evidence: Manufacturer ratings, calibrated pressure/duration trace, joint movement/leak observations and signed test report.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-09 — MISSING source evidence status

> Wetted materials and sealants used with edible plants shall have manufacturer documentation supporting potable-water or food-contact use, or shall be isolated from the nutrient solution. Uncoated aluminum shall not be exposed to the recirculating solution.

Action: Review all wetted materials/sealants against food/potable-water documentation and inspect aluminum isolation.

Required evidence: Wetted BOM, manufacturer documents, isolation drawings and as-built inspection/photos.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-MNT-01 — PARTIAL source evidence status

> The user maintenance schedule shall require an interior wipe-down and visual leak/film inspection no more frequently than once every 7 days. The task shall be completable by one user in 15 minutes or less.

Action: Approve wipe-down/leak-film procedure and demonstrate interval/access/time with a representative operator.

Required evidence: Maintenance schedule, elapsed task time, access/cleanliness observations and recorded maintenance transition.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-MNT-02 — PARTIAL source evidence status

> The filter, nozzles, reservoir, and drain path shall be inspected and cleaned every 14 days or sooner when flow falls below 90% of baseline. The complete task shall be possible in 30 minutes or less without removing the main frame.

Action: Approve filter/nozzle/reservoir/drain inspection and flow-trigger procedure; measure service time without frame removal.

Required evidence: Flow baseline/trigger, schedule, service timing, required tools/access photos and maintenance logs.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-MNT-03 — PARTIAL source evidence status

> A deep clean and nutrient-solution replacement shall be performed between crop cycles or every 90 days, whichever occurs first, and shall be completable in 60 minutes or less using the documented maintenance mode and assembly guide.

Action: Approve between-cycle/deep-clean/solution-replacement process and measure safe completion using reviewed maintenance mode.

Required evidence: Cleaning interval/procedure, elapsed time, solution/material handling and maintenance/restore-to-safe-state evidence.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-MNT-04 — PARTIAL source evidence status

> The pump, filter, fan, temperature/humidity sensor, camera, and any single nozzle shall each be replaceable in 30 minutes or less using common hand tools, without disassembling the primary aluminum frame.

Action: Review replaceability procedure for each listed component and demonstrate timed common-tool access without primary-frame disassembly.

Required evidence: Per-component task/tool/time records, drawings and before/after inspection.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-LIF-01 — PARTIAL source evidence status

> Selected components shall have manufacturer ratings or equivalent test evidence of at least: pump 1,000 operating hours; cooling fans 10,000 hours; horticultural LEDs 10,000 hours to 70% light output; door/interlock 1,000 cycles; tubing and seals 12 months in the specified nutrient-solution range.

Action: Obtain component-specific manufacturer ratings or approved equivalent evidence; retain operating-cycle accounting.

Required evidence: BOM-linked ratings/test reports for pump/fans/LEDs/interlock/tubing/seals and stated operating conditions.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-LIF-03 — PARTIAL source evidence status

> With the specified maintenance and replacement of documented wear items, the GERM chassis, enclosure, basin, electrical architecture, and control platform shall have a design service life of at least 3 years or 12 crop cycles, whichever occurs first, with no structural failure or through-leak.

Action: Approve service-life substantiation method and maintenance/wear-item assumptions rather than extrapolating a host run into years of physical life.

Required evidence: Design calculations, material/component evidence, wear/maintenance assumptions and qualified three-year/12-cycle assessment.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Sensors — proposed Sensor/metrology lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-ENV-01 — PARTIAL source evidence status

> A growth-zone temperature sensor shall measure air temperature at canopy level, not nutrient-solution or electronics temperature. It shall cover 10-40 deg C with accuracy of +/-2 deg C, update at least once per 60 seconds, and generate an alert if the measured air temperature remains outside 18-30 deg C for 5 minutes.

Action: Confirm canopy-air sensor ownership/interface/location, calibrate across the range and verify update/fault/band-alarm timing with approved injected inputs.

Required evidence: Reference calibration points/error, sample/receive/alert timestamps, location photos and approved policy.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-ENV-02 — PARTIAL source evidence status

> A growth-zone humidity sensor shall measure relative humidity of the air at canopy level. It shall cover 20-95% RH with accuracy of +/-5% RH, update at least once per 60 seconds, and generate an alert if RH remains outside 40-75% for 10 minutes.

Action: Confirm canopy RH interface/location, calibrate across range and test approved sustained band excursions and update/fault handling.

Required evidence: Reference RH/error data, cadence and ten-minute alert timing logs, approved policy and location.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-ENV-03 — PARTIAL source evidence status

> During a 4-hour worst-case load test at 25 +/-2 deg C ambient, the Raspberry Pi SoC shall remain below 75 deg C, electronics-bay air below 50 deg C, and every monitored component at least 10 deg C below its manufacturer maximum rating. If a normal limit is exceeded, software shall reduce nonessential high-power loads and issue an alert within 10 seconds.

Action: Approve distinct Pi/electronics/component channels and supervised worst-case load/ambient procedure; verify warning/load-reduction behavior through M1.

Required evidence: Four-hour ambient/component traces, manufacturer limits/margins and source-to-command/physical response timing.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-10 — MISSING source evidence status

> A failed, disconnected, or implausible temperature, humidity, water-level, leak, or door sensor shall be detected within two expected update periods. The UI shall identify the failed sensor, log the event, and place affected actuators in a documented conservative state.

Action: Approve each input interface/polarity/cadence and affected-actuator fallback; test missing/disconnected/implausible/stale/replayed inputs within the metric.

Required evidence: Fault injection/timing matrix, named HMI faults, durable events, gateway rejection and independent physical response evidence.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Growing — proposed Growing/agronomy lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-PLT-02 — PARTIAL source evidence status

> During a 60-day basil or spearmint grow demonstration, at least five of six established seedlings shall remain viable and reach a minimum 150 mm canopy height or eight mature leaves, with no plant loss attributed to missed misting, overheating, or lighting failure.

Action: Approve basil/spearmint protocol and run the separately authorized 60-day crop demonstration; record each plant and attribute losses from source logs.

Required evidence: Six-position dated viability/height/leaf records, interventions, crop settings and fault/actuator history.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-LGT-01 — PARTIAL source evidence status

> At the nominal canopy plane, the lighting system shall deliver photosynthetic photon flux density (400-700 nm) with a six-position average of 200-300 micromoles/m^2/s, no position below 150 micromoles/m^2/s, and minimum-to-average uniformity of at least 0.70. The default photoperiod shall be 16.0 +/-0.25 hours per day.

Action: Approve horticultural settings and optical measurement procedure; map canopy PPFD at all six positions and measure actual photoperiod.

Required evidence: Calibrated quantum-meter readings, geometry, average/minimum/uniformity and photoperiod logs.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-LIF-02 — PARTIAL source evidence status

> GERM shall complete one continuous 90-day grow-cycle simulation without replacement of the pump, fans, LEDs, controller, sensors, camera, tubing, basin, frame, or wiring. Filters, nutrient solution, and intentionally replaceable seals are consumables and may be serviced per the maintenance schedule.

Action: Resolve and approve the required 90-day system grow-cycle simulation method, replacements/consumables and real versus accelerated duration interpretation. The 72-hour host run is insufficient.

Required evidence: Approved protocol, complete elapsed/simulated-time declaration, replacement/intervention register and continuous system evidence.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Camera Ml — proposed Camera/ML lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-ML-01 — PARTIAL source evidence status

> Plant-health inference shall execute locally using TensorFlow Lite, Edge Impulse, or another documented edge-runtime. Model storage shall not exceed 250 MB, and one image shall be processed and displayed within 10 seconds without internet access.

Action: Approve local runtime/model artifact and its hash/licensing; measure size and real Pi inference/display latency offline. No model download is authorized now.

Required evidence: Approved manifest/artifact hashes, runtime/dependency bill, measured storage and end-to-end latency distribution.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-ML-02 — PARTIAL source evidence status

> On a held-out test set captured under GERM-like lighting and camera geometry for the target plant species, the model shall achieve balanced accuracy of at least 85%, unhealthy-plant recall of at least 90%, and macro F1 score of at least 0.85. The test set shall contain at least 50 unique images per class and no source image may appear in both training and test sets.

Action: Approve held-out GERM-like dataset and no-leakage split; evaluate every required metric/sample count without training/test overlap.

Required evidence: Unique-image/class counts, dataset provenance/split hashes, confusion matrix, balanced accuracy/recall/F1 and reviewer approval.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-ML-03 — PARTIAL source evidence status

> Predictions below 0.70 confidence shall be displayed as “Uncertain,” not as a diagnosis. An abnormal-health alert shall require two consecutive abnormal results unless a separately documented severe condition is detected. Each result shall store the image, confidence, class, and model version.

Action: Approve real labels/normal-abnormal policy and any severe-condition exception; test uncertainty threshold and consecutive-result logic with persisted image/model provenance.

Required evidence: Boundary-confidence cases, two-result/reset sequences, reviewed policy/version and durable image/inference/event joins.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Security — proposed Security/network lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-NET-01 — PARTIAL source evidence status

> Loss of internet connectivity shall not interrupt local control, HMI, ML, or logging. When a network is available, critical alarms shall be delivered to the configured remote channel within 5 minutes; during an outage, alarms shall be queued locally and marked unsent.

Action: Approve network/authentication/remote channel and implement/review currently missing remote delivery/unsent behavior before this SR can pass; separately test offline local functions.

Required evidence: Outage/delivery timing, durable unsent/retry receipts, destination approval and no unauthorized exposure or command replay.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Data Retention — proposed Data/retention owner

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-DAT-01 — PARTIAL source evidence status

> The primary database and ML inference pipeline shall operate locally on the Raspberry Pi using SQLite or an equivalently documented local store. Core sensing, control, HMI, and logging shall not require an internet connection.

Action: Approve isolated Pi installation and local database/model runtime; distinguish internet loss from loss of local HMI service.

Required evidence: Pinned release/dependencies, offline traces, local DB/model provenance and camera/ML owner signoff.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-DAT-02 — PARTIAL source evidence status

> GERM shall retain at least 90 days of 5-minute environmental/operating records and at least one plant image per hour. When storage reaches 80% capacity, the system shall warn the user and automatically delete the oldest images only after preserving at least the most recent 30 days. Data shall be exportable as CSV plus image files.

Action: Resolve 90-day records/hourly images versus image pruning/30-day horizon/active-experiment protections; approve capacity and fail-full policy before long runs. No deletion is authorized by this checklist.

Required evidence: Signed precedence/retention decision, capacity forecast, warning/exhaustion tests, protected archive/export/backup inventory and separate authorization for any later deletion.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-DAT-03 — PARTIAL source evidence status

> Each record shall include timestamp, plant profile, growth-zone temperature, RH, electronics temperature, water-level state, pump state, light state, door state, active alarms, maintenance mode, and ML label/confidence when available. Missing scheduled records shall be below 1% during the 72-hour endurance test.

Action: Approve acquisition/record cadence, units and provenance joins; audit all required fields and missing-record fraction over the real endurance run.

Required evidence: Scheduled-versus-durable counts, UTC/clock provenance, quality flags, image/model joins and request/ACK/physical evidence distinction.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

## Validation — proposed Validation/test lead

Named accountable person / approver: **unassigned**. Cross-functional review is required where the metric spans other disciplines.

### [ ] SR-AUT-01 — PARTIAL source evidence status

> GERM shall complete a 72-hour unattended endurance test while maintaining the programmed mist and light schedules, collecting required data, and avoiding manual reset or refill. No more than one noncritical warning and no uncontrolled shutdown shall occur.

Action: Approve supervision, stop/escalation criteria and resources before a 72-real-hour continuous run; never splice restarts into a continuous pass.

Required evidence: Real elapsed/UTC record, all schedule/data/warning/shutdown/refill/reset events and signed disposition.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-AUT-02 — MISSING source evidence status

> On loss of input power, all actuators shall de-energize. After power is restored, GERM shall retain the active plant profile and stored data, complete startup checks within 2 minutes, and keep the pump off until door, water-level, leak, and emergency-stop states are safe.

Action: Approve power-interruption procedure after independent electrical safeguards; measure de-energization, startup and retained intent with fresh interlocks and separate Start.

Required evidence: Before/after data/profile hashes, measured startup duration, physical off evidence, fresh inputs and rejected stale confirmations.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-UI-01 — PARTIAL source evidence status

> In a usability test, at least four of five users who have not previously operated GERM shall, after no more than a 5-minute orientation, select a plant profile, start a grow cycle, enter maintenance mode, identify an active alarm, and return to the status screen within 5 minutes with no critical error and no more than one noncritical error.

Action: Approve novice protocol and privacy/observation consent; test five new users with the specified orientation/tasks/time/error scoring.

Required evidence: Per-user timings, orientation duration, critical/noncritical errors and independently scored success counts.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-UI-02 — PARTIAL source evidence status

> The primary status screen shall display current growth-zone temperature and RH, electronics temperature, reservoir/low-water state, pump and light state, light schedule, selected plant profile, grow-cycle day, live plant image, latest ML result and confidence, active alarms, and date of last maintenance. Values shall refresh within 2 seconds of new data.

Action: Verify all primary-screen fields on the actual 739×447 display; measure source-update-to-DOM latency and stale/unavailable/degraded behavior.

Required evidence: Timestamped source/API/DOM traces, screenshots, measured refresh latency, touch/keyboard observations and physical reading references.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-UI-03 — PARTIAL source evidence status

> The local touchscreen shall provide preloaded basil and spearmint profiles and controls for Start, Pause, Maintenance, and Safe Manual Test. Any command that energizes the pump after a stop or maintenance state shall require explicit confirmation.

Action: Review approved crop settings and exercise profile/Start/Pause/Maintenance/Safe Manual Test with confirmation rejection/restart checks.

Required evidence: Operator sequence, API/event/ACK traces, separate physical observations and rejected missing/stale confirmation cases.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

### [ ] SR-SAF-03 — MISSING source evidence status

> Maintenance mode shall inhibit all automatic pump starts and other hazardous automatic motion/actuation, display a persistent “MAINTENANCE - OUTPUTS INHIBITED” state, and require user confirmation to exit.

Action: Approve hazard-specific maintenance inhibition policy with electrical/software owners; verify persistent banner and confirmed exit without load resumption.

Required evidence: All automatic entry-path attempts, event/API/ACK records, physical off observations and cancellation/restart cases.

Decision: **not performed; physical acceptance open**. No controlled requirement approval is established.

Cross-cutting items in [approval gates](APPROVAL_GATES.md) additionally cover exact-SHA merge authorization, production identity/read-download privacy, physical adapters, backup/data adoption, retention precedence and explicit installation/commissioning permission. They are not invented new SRs.
