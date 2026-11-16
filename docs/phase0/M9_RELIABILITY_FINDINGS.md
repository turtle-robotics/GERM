# M9 paused-summary investigation and corrections

2026-11-16. M8 accepted the historical timeout as unresolved. [M9 plan](M9_PLAN.md), [raw evidence](../evidence/m9/README.md). All probes are disposable synthetic loopback processes at 739×447. Existing M1–M8 browser assertions and 30-second waits are unchanged. Tests were not made green by extending timeouts.

Baseline investigation repeated the complete M8 browser flow five times successfully. Success alone could not exclude a race. New M9 instrumentation collects monotonic HTTP durations/status/cycle snapshots, worker alive/heartbeat/lifecycle/repository/logging state, SQLite operation/connection/error activity, client request/response sequence and DOM mutations, plus failure API/DOM/screenshot artifacts. Server traces retain at most 2048 records, client traces 512. SQLite values, tokens and request bodies are not recorded. Atomic trace replacement preserves evidence after terminating the disposable server. Instrumentation adds overhead and is test-only; timings are diagnostic, not product latency claims.

## Demonstrated defect: older responses overwrite newer state

The browser fetched a running state and deliberately delayed its delivery. Pause and a newer refresh completed: API and DOM were paused. Releasing the older response changed the DOM back to running while a direct API read remained paused. `ordering-before/response-ordering.json` records that contradiction. A monotonically increasing client poll revision now discards superseded successful responses and errors. No gateway, permission or persistence rule changes. The M9 browser asserts the DOM stays paused after the exact same ordering challenge.

Reproduce the old-client probe with the accepted M8 client: write `git show e1511c1fa39a155801e5c1855872747c9b78c8f8:pi_hmi/static/hmi.js` to an ignored build file, set `GERM_M9_BASELINE_CLIENT` to its absolute path and `GERM_M9_EXPECT_RACE=1`, then run `node pi_hmi/tests/browser_m9.cjs` with the usual Playwright/Python environment. The route override is a test-only local static asset response. Expected diagnostic output: older running response overwrote newer paused DOM. With those flags unset the corrected assertion must pass. No production setting selects an old client.

## Demonstrated defect: unconfirmed Pause unnecessarily binds a stale revision

An instrumented repeat reproduced the same 30-second paused-summary wait symptom. The browser prepared Pause, then the automatic lighting worker changed the state revision before dispatch. The POST returned 409; the API and DOM correctly remained running, with SQLite ready, core worker alive and no SQLite exception. The client sent an expected revision even though M1 explicitly marks Pause confirmation-not-required. M1 correctly rejected that supplied stale precondition.

The HMI now omits only the optional revision for **unconfirmed Pause**, preserving its existing safe-stop contract and M1 gateway dispatch. Start and every confirmed workflow retain the nonce/exact revision and reject stale confirmations. A unit test demonstrates stale prepared Pause rejection, then successful revision-optional Pause, then rejection of stale confirmed Start. Chromium deliberately supplies an old Pause preparation revision on every repeat; three start/pause cycles and all seven screens must still show paused. `pause-revision-before/` retains the failure screenshot, client/API observations, server trace and HTTP 409. No retry of an energizing command was added.

## Demonstrated defect: concurrent queued events mistaken for logging failure

A repeat also left the core worker degraded with a healthy repository, pending events and no IO error. M3 drain snapshots its queue: an event arriving during that drain legitimately leaves a queued remainder and returns false (not fully durable). M8 interpreted every false result as fatal logging failure.

HostPersistenceRuntime now exposes a fresh per-tick evidence record without changing its boolean durable-result contract. The lifecycle tolerates **only** a freshly evidenced pending remainder with durable restart checkpoint, repository ready and no logging error. It reports logging queued and skips actuator scheduling that tick. An unknown false result, poison/dropped events, non-durable restart, DB/IO error or stale evidence still causes degraded state, STOP through M1 and explicit restart inhibition. No queued event is labelled committed. A deterministic test injects an event during a real commit, preserves queued state for observation and verifies the next tick drains it. Existing M8 failure-injection tests remain unchanged and pass.

## Remaining uncertainty

These are reproducible, corrected causes of stale display, pause rejection/wait and spurious worker shutdown. They do **not** conclusively explain every historical failure: the earliest M8 source campaign's old M4 Pause response was HTTP 200, so its original successful-response timeout remains causally unproven. No evidence was rewritten to claim otherwise. Repeated corrected workflows, exact source/CI traces and failure artifacts support host review; target timing, filesystem contention, long real elapsed runtime, novice usability and physical safety remain unaccepted.
