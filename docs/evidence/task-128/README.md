# Task 128 — seven-screen contract checklist evidence

Deliverables: [44-row structured checklist](../../phase0/HMI_API_CHECKLIST.json), [human review table](../../phase0/HMI_API_CHECKLIST.md), [existing endpoint success/error catalog](../../phase0/API_ENDPOINTS.json), [provisional official requirements](../../phase0/REQUIREMENTS_BASELINE.json) and [M1 proposed command/sensor/state model](../../phase0/M1_CONTRACT.md).

All seven screens and shared offline/navigation/usability/refresh/diagram criteria are covered. Each behavior has source, displayed field/units, actual backend route/field or explicit missing contract, quality/fault/inhibit behavior, confirmation, acceptance case, functional review boundary, evidence/status and gap. No invented endpoint is presented as working.

Code commit: `ef363dc5bdba9b75f5e41a77f450a34c5a53c5ac`. Shared test campaign and exact logs: [Task 119](../task-119/README.md), particularly ChecklistContractTests in m0-contracts.txt and the existing route catalog check in phase0-contracts.txt. Tests prove checklist coverage/route grounding, not screen usability, actual DOM refresh <=2s, editable diagram import or physical interlocks.

Contract review is PENDING. SR-UI-01/02/03 source evidence remains PARTIAL. No new novice-user, browser screenshot, touchscreen or hardware result is claimed. No Gantt status changed. PR reference is recorded in the repository evidence index after publication.

Review: confirm source coverage; actual versus proposed/missing fields; every POST path including firmware/mode; confirmation and unavailable semantics; measurable cases and downstream evidence; then record reviewed commit and verdict.
