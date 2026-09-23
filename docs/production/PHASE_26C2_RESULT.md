# Phase 26C-2 — Agent Run Lifecycle & Deadline Control (Result)

Date: 2026-09-22 · Baseline 7ac15aa (26A @ 8eb3007 / 26B frozen /
26C-1 closed same day) · Suite 15/15 (107/107 checks) · Regression
numbers below.

## Status

```
PHASE_26C2_PASS_WITH_DOCUMENTED_DEBT
```

## Audit finding (what existed before this phase)

An "agent run" had NO lifecycle object of its own: the run WAS the
26A task row (PENDING→…→terminal), WAITING was FAILED+reason, and
there was NO run deadline / timeout concept anywhere (grep: zero
`deadline`/`TIMED_OUT` in the queue path). Cancellation was already
race-safe (task CAS, 200-round proven) but timeout, terminal-run
immutability and late-worker-vs-timeout protection did not exist.
`run_id` existed only as a task column for approval-marker binding.

## Architecture (minimal production control boundary — no second
lifecycle machine, no queue rewrite)

```
agent_runs (NEW, PG)  = BUSINESS lifecycle authority
queue_tasks (26A)     = QUEUE/EXECUTION authority (unchanged)
```

- `runtime/queue/run_control.py` (NEW): `RunControl` — run state
  machine, absolute deadline, cancel/approve gates, pull-based
  expiry. `submit_run` creates QUEUED run + enqueues the task
  (idempotent, deadline set once).
- `AgentTaskWorker(run_control=...)` (additive): when the task
  carries a MANAGED run, every settle goes through the boundary;
  without it the 26A/26B path is byte-identical (regression-proven).
- `QueueOps(..., run_control=...)` (additive): approve gated by
  `approve_resume_gate`; cancel co-transacts run+task.

### Run state machine (RUN_TRANSITIONS, literal-pair-oracle tested)

```
QUEUED → RUNNING | CANCEL_REQUESTED | TIMED_OUT | CANCELLED
RUNNING → WAITING_HUMAN | SUCCEEDED | FAILED | TIMED_OUT
        | CANCEL_REQUESTED | CANCELLED
WAITING_HUMAN → RUNNING | TIMED_OUT | CANCEL_REQUESTED | CANCELLED
CANCEL_REQUESTED → CANCELLED | TIMED_OUT
SUCCEEDED/FAILED/TIMED_OUT/CANCELLED → (terminal, no exits)
```

### Transition authority

Task CAS (lease/status) decides EXECUTION outcomes; run CAS decides
BUSINESS outcomes. Every terminal-destiny decision writes run+task
in ONE PostgreSQL transaction (both CAS, rowcount-checked) —
`settle_success` / `settle_defer` / `settle_failure` / `cancel_run`
/ expiry. `CANCEL_REQUESTED` = operator intent (no task mutation);
a real completion beats a mere intent (one terminal winner).

### Deadline semantics (absolute; §9 answers)

`deadline_at = now()+N at submit (DB clock), never moved`.
Enforced at control points — before start, before settle-success,
before retry, before approval-resume, plus pull-based
`expire_overdue()` (no daemon; periodic reaper = P3 debt).

- A: start 09:59:59, deadline 10:00 → ALLOWED (start guard
  `now() <= deadline_at`).
- B: provider still running at deadline → not hard-killed; bounded
  at the next control point (settle/retry gate).
- C: provider returns after deadline → result NOT accepted — same
  transaction converts to TIMED_OUT.
- D: completion lands after deadline → TIMED_OUT (success CAS
  carries `now() <= deadline_at`).
- Retry NEVER resets the deadline (attempt 2 inherits attempt 1's
  absolute bound; post-deadline failures do not requeue).

### Cancellation

`request_cancel` records intent (idempotent). `cancel_run` =
task cancel CAS + run CANCELLED in one transaction; if the task CAS
loses (already terminal) the run syncs — exactly one terminal
winner, never both effects (60 barrier rounds × 2 race families).
RBAC unchanged (OWNER/OPERATOR cancel; REVIEWER denied — 26B).

### Terminal-state rule & late-worker protection (highest priority)

Terminal run ⇒ NOTHING can reactivate: approve gate refuses,
`on_started`/settle CAS from-states exclude terminals, expiry
cancels the task (unclaimable), and a late worker's completion is
rejected at BOTH layers (task CAS misses; run CAS refuses) with
`run.late_completion_rejected` logged. TIMED_OUT → SUCCEEDED and
CANCELLED → SUCCEEDED are structurally impossible (illegal
transitions, machine-enforced).

### HITL

Defer = task FAILED+WAITING + run WAITING_HUMAN (one txn, slot-free
— 26C-1 invariant preserved). Approval: the approval transaction's
own `now()` must be ≤ deadline (09:59:59 approval + 10:00:01 resume
= ALLOWED — approval won; 10:00:01 approval = refused + TIMED_OUT).
Late approval after CANCELLED/TIMED_OUT refused — no revival.

### Crash recovery (C1–C5, C1 = real OS kill)

C1 RUNNING+kill → lease expiry → recovery claim → run survives →
SUCCEEDED (attempt 2). C2 CANCEL_REQUESTED+kill → hard cancel
completes terminal. C3 TIMED_OUT+kill → nothing claimable, expiry
idempotent. C4 WAITING+kill → approval still resumes. C5
approval+kill → requeued task executes on any worker. Recovery
never violates a terminal run.

### Idempotency

Duplicate cancel = ALREADY_TERMINAL (no second effect); duplicate
expire = NO-OP; duplicate approve = refused (not waiting);
duplicate completion = DUPLICATE_SUCCESS (no state corruption).

### Observability (existing taxonomy reused, no OTel)

`run.created / started / waiting_human / cancel_requested /
cancelled / timeout / failed / succeeded / resume_approved /
late_completion_rejected / late_start_rejected / late_approval_
rejected / cancel_noop` via `runtime.obs` (run_id+task_id+status;
worker fields already carried by task.* events).

## Failure matrix (all PROVEN by tests)

| Failure / Race | Expected | Evidence |
|---|---|---|
| deadline reached | TIMED_OUT | E26C2-03/04/06 |
| late success | rejected | E26C2-04/05/06 (both layers) |
| cancel queued run | CANCELLED | E26C2-10 |
| cancel running run | bounded (worker settles to STALE_REJECTED) | E26C2-05 |
| cancel waiting run | CANCELLED | E26C2-08(c) |
| late approval after timeout | rejected | E26C2-08(b) |
| late approval after cancel | rejected | E26C2-08(c) |
| retry after timeout | rejected (no requeue) | E26C2-09 |
| retry after cancel | nothing claimable | E26C2-11 C2/C3 |
| lease recovery after timeout | no reactivation | E26C2-06 |
| lease recovery after cancel | no reactivation | E26C2-05/11 |
| duplicate cancel | idempotent | E26C2-10 |
| duplicate timeout | idempotent | E26C2-06/10/11 |
| duplicate completion | no corruption | E26C2-02/10 |
| worker crash | recoverable | E26C2-11 C1 (real kill) |
| DB failure | fail closed (26A OutcomeUnknown paths kept) | inherited |
| commit unknown | recovery required (26A semantics kept) | inherited |

## Mutation / adversarial evidence (M26C2-01..10)

Behavioral kills: 01 gate removal revives a terminal run (observed
→ detector fires); 02 run-layer bypass accepts late success →
task/run divergent (managed path refuses exactly this); 03
run-only cancel + live lease → managed settle REVERTS the success
(one winner); 06/07 blind terminal overwrite corrupts state → the
CAS guards exist to prevent exactly this (races prove they hold).
04/08 deadline drift detectable (equality assertions); 09/10
detector mapping to the 60+45 barrier-round races.

## Tests

`tests/runtime/test_p26c2_run_lifecycle.py` — E26C2-01..14 +
C1–C5 + M26C2 (15 tests / 107 checks; deterministic DB-clock polls,
barrier-synchronized races, real subprocess kill for C1; real PG
throughout; dual-mode pytest+script).

## Regression

```
Runtime:     567 passed (552 + 15 new p26c2 tests)
26A 13/13 · 26B 10/10 · 26C-1 12/12 (frozen capabilities intact)
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
```

## Invariants (INV-26C2-01..08)

01 run terminal ⇒ no new accepted success: PROVEN · 02 task
terminal ≠ auto run terminal (authority split): PROVEN · 03
deadline never moves: PROVEN · 04 terminal → non-terminal
impossible: PROVEN · 05 cancelled never resumes: PROVEN · 06
timed-out never resumes: PROVEN · 07 late worker cannot mutate
terminal run: PROVEN (both layers) · 08 duplicate commands
idempotent: PROVEN.

## Findings

| ID | Severity | Finding |
|---|---|---|
| F-26C2-INFO-01 | INFO | Deadline enforcement is control-point-based (no background reaper): an abandoned run whose task finished is terminal, but an overdue run with NO future control point (worker died, nobody calls expire) stays non-terminal until an operator/test runs `expire_overdue()` — periodic reconciliation remains Future/P3 debt |
| F-26C2-INFO-02 | INFO | A worker executing at deadline-pass (Case B) is not hard-interrupted: bounded at its next control point — consistent with the at-least-once/lease model (hard cancellation of in-flight provider calls is out of scope) |
| F-26C2-INFO-03 | INFO | `submit_run` deadline defaults to 3600s; production wiring (who calls submit_run, per-case deadline policy) is deliberately left to the deployment phase — the boundary is composable and tested, not yet wired behind the HTTP API |

P0 = 0 · P1 = 0 · P2 = 0 · P3 = 0 · INFO = 3

## Scope discipline

runtime/queue/{run_control.py NEW, agent_runtime.py, ops.py,
__init__.py} + tests/runtime/test_p26c2_run_lifecycle.py (NEW) +
this doc + DISTRIBUTED_TASK_EXECUTION.md (§26C-2). Zero changes to
skills/knowledge/gateway/orchestrator/store/model (26A semantics
frozen; unmanaged task path byte-identical). Exactly-once NOT
claimed: at-least-once + idempotent completion + stale-lease
rejection + checkpoint recovery + terminal-run protection.

Phase 26C-3 (Budget / Bounded Execution): NOT STARTED.
