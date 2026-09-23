# Phase 26C-1 — Backpressure & Capacity Control (Result)

Date: 2026-09-22 · Baseline 7ac15aa (26A @ 8eb3007, 26B frozen) ·
Source finding: V-26V-P3-01 (26AB gate-review completion
verification) · Suite 12/12 (80/80 checks) · Regression numbers in
the Regression section.

## Status

```
PHASE_26C1_PASS_WITH_DOCUMENTED_DEBT
```

(debt = the items already on the 26C backlog — F-26R-P2-01 marker
storage, F-26R-P3-01 recovery observability, per-type caps
F26B-P3-02; nothing new beyond V-26V-P3-01's closure)

## What this phase is

Audit + minimal fix + deterministic coverage for the 26A-19 worker
backpressure capability (`max_concurrent_tasks` / `at_capacity`),
which the 26AB gate review never audited and which had ZERO test
coverage. NOT a queue/worker redesign: one real bug fixed, one new
suite, docs.

## Audited semantics (CURRENT REALITY, from code)

`max_concurrent_tasks` (normalized `>= 1`) caps the CONCURRENT
ACTIVE EXECUTIONS of ONE `TaskWorker` instance:

- **Scope: worker-INSTANCE-local** (per Python object). It is not a
  process-global bound across instances and NOT a global bound
  across workers/hosts — global concurrency is deliberately NOT
  claimed (E26C1-07 observes simultaneous global 4 with two workers
  at max 2 each; F-26C1-INFO-01 records the future global-cap
  question).
- A slot is reserved **atomically BEFORE the claim** (INV-02): a
  worker at capacity does not claim, so queued tasks keep
  `status=PENDING`, `lease_id=NULL`, `attempt=0` — backpressure
  never parks a leased task on a local wait, never inflates
  attempts, never causes lease starvation.
- The slot is released in a `finally` on EVERY settle path
  (SUCCEEDED / FAILED / FAILED_REQUEUED / STALE_REJECTED /
  RECOVERY_REQUIRED) — no capacity leak on success, failure, or
  DB-loss (INV-03).
- Capacity is an in-process counter: a crashed worker's slots die
  with it; recovery is the existing 26A lease-expiry path and a
  fresh worker starts at zero (INV-04, real-kill test).
- Retry consumes a slot only while actively executing; a requeued
  attempt holds no slot and no lease (INV retained; 26A retry
  semantics untouched).
- HITL WAITING (26B defer) holds NO slot: defer settles the task
  FAILED+WAITING and releases the slot; resume = new claim = new
  slot (INV-07).

## The real bug found and fixed (F-26C1-P2-01)

`run_once` was check-then-act: `at_capacity()` (lock released)
→ `claim` → increment. Two concurrent `run_once` callers on ONE
instance could BOTH pass the check and BOTH claim → `_inflight`
overshot `max_concurrent_tasks` (INV-01 violated). Concurrent
callers are within the worker's own design (the instance lock
exists for them; 26B's committed tests drive workers from threads).

Fix (runtime/queue/worker.py): atomic `_reserve()` — capacity check
and increment under a SINGLE lock acquisition — released by
`_release_slot()` in the `finally`. Plus introspection/metrics:
`active_tasks` / `capacity_rejections` properties and an
edge-triggered `worker.backpressure` obs event (once per busy
period — a polling loop at capacity must not spam the sink). No
store/lease/SQL change; `at_capacity()` kept as read-only
introspection.

Behavioral kill: M26C-01 bypasses the reservation and the suite
DETECTS the overshoot; E26C1-10 (8 barrier-synchronized callers,
held gate) proves the fixed bound holds — exactly 2 execute, 6
refused, observed active never exceeds 2.

## Test suite (tests/runtime/test_p26c1_backpressure.py)

| Group | Test | Proves |
|---|---|---|
| A basic capacity | E26C1-02 | max=2, 5 tasks/callers → exactly 2 active, 3 refused, all complete once, `max_observed_active == 2` |
| B backpressure | E26C1-03 | queued tasks stay PENDING, no lease, `attempt == 0` while capacity is full |
| C release on success | E26C1-04 | slot returned 1→0; next queued task claimed; later tasks untouched |
| D failure release | E26C1-05 | FAILED execution frees the slot; later tasks execute; bounded retry intact |
| E crash recovery | E26C1-06 | REAL OS process killed mid-run; lease (2s, no heartbeat) expires; worker B (fresh capacity) recovers attempt 2 → SUCCEEDED; dead instance holds no shared capacity |
| F multi-worker | E26C1-07 | 2 workers × max=2 on 8 shared tasks: each ≤ 2, simultaneous global 4 (NOT a global cap), all settle exactly once, both workers participate |
| G lease interaction | E26C1-10 | barrier-synchronized TOCTOU hammer: atomic reservation holds the bound (the 26C-1 fix) |
| H retry | E26C1-08 | slot free between attempts; requeued task holds no lease; attempts 1,2 seen at requeue, success at 3 |
| I HITL | E26C1-09 | WAITING holds no slot; approve→requeue→resume consumes a slot again → SUCCEEDED attempt 2 |
| metrics | E26C1-11 | active/queued/max/rejections measurable; empty-queue miss ≠ capacity rejection |
| semantics | E26C1-01 | max_concurrent normalization; introspection surface |
| J mutations | M26C-01..06 | behavioral kills: bypass detected (overshoot), release-removed detected (leak blocks next task), check-after-claim detector (E26C1-03 invariants), crash-keeps-capacity detector (E26C1-06), local-as-global detector (E26C1-07) |

All waits are deadline-based polls with harness-released gates —
no sleep-and-hope. Real PostgreSQL throughout; real OS subprocess
for the crash test.

## Invariants

INV-01 bound (incl. under synchronized concurrent entry): PROVEN ·
INV-02 backpressure before claim: PROVEN · INV-03 release on every
settle path: PROVEN · INV-04 crash frees capacity: PROVEN (real
kill) · INV-05 per-instance bound, global NOT claimed: PROVEN ·
INV-06 queue/lease semantics preserved: PROVEN (26A 13/13, 26B
10/10, full battery below — zero changes to store/model/ops) ·
INV-07 HITL WAITING holds no slot: PROVEN.

## Regression

```
Runtime:     552 passed in 5:47 (540 pre-existing + 12 new p26c1
             tests; clean run 2026-09-22, PATH python 3.11.8,
             agent-postgres :5433, WeKnora available)
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
26A suite 13/13 · 26B suite 10/10 (frozen capabilities intact)
```

## Findings

| ID | Severity | Finding |
|---|---|---|
| F-26C1-P2-01 | P2 | run_once capacity check was check-then-act → concurrent callers could exceed max_concurrent_tasks — FIXED by the atomic reservation (the only runtime change of this phase) |
| F-26C1-INFO-01 | INFO | worker-local caps do not bound GLOBAL concurrency (N workers × max M → up to N×M); a global capacity control would need cross-worker coordination — Future/P2 candidate, deliberately NOT implemented (per phase boundary) |
| F-26C1-INFO-02 | INFO | PHASE_26A_RESULT's table cited "E26-15 asserts claim refusal" for backpressure; E26-15 actually tests stop-refusal + release — documentation nuance, superseded by this doc |

P0 = 0 · P1 = 0 · P2 = 1 (FIXED) · INFO = 2

## F-26C1-P2-01 closure

```text
Finding: F-26C1-P2-01 (found during this phase's audit)
Status: FIXED / CLOSED (2026-09-22, Phase 26C-1)
Original Problem: run_once capacity check was check-then-act —
  at_capacity() released the lock before claim+increment, so two
  concurrent run_once() callers on ONE worker instance could both
  pass the check and overshoot max_concurrent_tasks.
Fix: atomic _reserve() (capacity check + increment under a single
  lock acquisition) with _release_slot() in the finally of run_once
  (runtime/queue/worker.py — the only runtime change of this phase).
Proof: E26C1-10 — 8 barrier-synchronized callers, held gate:
  exactly 2 execute, 6 refused, observed active never exceeds 2.
Regression: M26C-01 detector — with the reservation bypassed the
  suite DETECTS the overshoot (the pre-fix behavior fails the
  invariant); full battery 552 green post-fix.
```

## V-26V-P3-01 closure

```text
Finding: V-26V-P3-01
Original: Phase 26A implements max_concurrent_tasks / at_capacity,
but the gate review did not audit it and the suite had no dedicated
coverage.
Resolution: audited semantics (this doc), fixed the real
check-then-act bug found during the audit (F-26C1-P2-01), added a
deterministic 12-test/80-check suite covering all seven invariants
incl. a real-OS-process crash test and behavioral mutation kills.
Evidence: tests/runtime/test_p26c1_backpressure.py (12/12, 80/80
checks) + runtime/queue/worker.py (_reserve/_release_slot) + this
document's audited-semantics section.
Tests: E26C1-01..11, M26C-01..06; regression 26A 13/13, 26B 10/10,
full battery / portfolio / benchmark / compileall green.
Status: CLOSED (2026-09-22, Phase 26C-1)
```

Phase 26A and 26B remain frozen (no store/model/ops semantics
touched). Phase 26C-2: NOT STARTED.
