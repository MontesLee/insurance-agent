# Distributed Task Execution — Phase 26A (as implemented)

PostgreSQL is the ONLY queue and the ONLY task-state authority. Redis
is DEFERRED (a Phase 26B+ decision, driven by measured contention —
none exists at this scale). Workers are stateless execution units.

## Layer

`runtime/queue/` — a NEW parallel entity; the in-case task model
(`runtime/tasks.py`) is untouched. Business Skills never see
worker/lease/queue concepts (verified: zero `.trae/skills` imports of
`runtime.queue`).

| Module | Role |
|---|---|
| `model.py` | states + legal transitions, task/lease/worker-instance ids, idempotency keys |
| `store.py` | `queue_tasks` table; every mutation a lease-guarded compare-and-set |
| `worker.py` | `TaskWorker`: claim → start → execute (injected executor) → succeed/fail/release; heartbeat; backpressure; graceful shutdown |

## Task state machine

```
PENDING → LEASED → RUNNING → SUCCEEDED ✝
   ▲        │         │        └─fail→ FAILED ──retry(attempt<max)──┐
   │        │         ├─ expiry → LEASE_EXPIRED → PENDING           │
   └────────┴─ release ┘                                           (requeue)
PENDING/LEASED/RUNNING → CANCELLED ✝      ✝ terminal, never re-executed
```

Illegal transitions are refused by compare-and-set SQL
(`WHERE status=... AND lease_id=... AND lease_expires_at > now()`);
LEASE_EXPIRED can never jump to SUCCEEDED (expiry is loss of
authority, not a result).

## Identity

- `task_id` `qt_<type>_<rand>` globally unique; `(task_id, attempt)`
  identifies one logical execution (`idempotency_key = task#attempt`,
  recomputed on every claim).
- `worker_id` logical + `worker_instance_id = wi_<worker>_<rand>` per
  PROCESS LIFETIME — never hostname/pid/thread alone; restarts and
  concurrent instances of one logical worker are distinguishable.

## Lease + atomic claim (SKIP LOCKED)

Claim is ONE statement: `UPDATE ... WHERE task_id = (SELECT ... FOR
UPDATE SKIP LOCKED LIMIT 1)` — selection, lease assignment and
`attempt+1` in a single transaction; there is no SELECT-then-UPDATE
window. Claimable = PENDING, or LEASED/RUNNING with an expired lease
(crash recovery). Verified: 4 concurrent connection racers → exactly
one winner; a locked row is skipped fast, not waited on.

Only the holder of the CURRENT VALID lease may write: stale,
mismatched or expired leases are rejected (`LeaseRejected`) with the
reason distinguished by the DATABASE clock (never Python-side time
comparison).

## Execution semantics (honest)

**AT-LEAST-ONCE execution + idempotent completion + stale-lease
rejection.** Exactly-once is NOT claimed (§34): a crash between
executor completion and the settle write means the task may run again
— but a second valid business result CANNOT be produced:

- `succeed` on an already-SUCCEEDED task → `DUPLICATE_SUCCESS`,
  changed=false, stored result stays the FIRST one
- a stale worker's succeed/fail/heartbeat → `LeaseRejected`, the
  current owner's truth is never overwritten
- terminal tasks are never claimable again

## Crash recovery

`recover_expired()` requeues LEASED/RUNNING tasks whose lease expired
(recorded via `retry_reason='lease_expired'`); the next claim takes
the task with `attempt+1`. Verified end-to-end: A crashes → lease
expires → B reclaims (attempt 2) → A's stale completion REJECTED →
B's completion stands.

## Heartbeat

Only the current lease owner may extend (`heartbeat` is lease-guarded
like every write). A worker whose heartbeat is rejected has lost
authority: execution runs to its safe point but CANNOT settle.

## Retry model (bounded)

Task-level retry only (`fail(..., retry=True)` requeues while
`attempt < max_attempts`; at max the task stays FAILED). This is
DELIVERATELY separate from Skill repair (in-case, ≤2) and LLM
transient retry (gateway, ≤2): no multiplication — a Task retry
re-executes the skill fresh, and the gateway's internal retries are
bounded per call.

## Backpressure + graceful shutdown

`max_concurrent_tasks` caps the CONCURRENT ACTIVE EXECUTIONS of ONE
worker instance (worker-instance-local — global concurrency is NOT
bounded by it; audited 26C-1). The slot is reserved atomically
BEFORE the claim: a worker at capacity does not claim, so queued
tasks keep `PENDING` with no lease and no attempt consumed —
backpressure happens before the lease, never after it. The slot is
released on every settle path; introspection via `active_tasks` /
`capacity_rejections` (+ edge-triggered `worker.backpressure` event).
SIGTERM / `request_stop()` stops new claims; the
in-flight task runs to a safe point and settles — or is RELEASED
(`release` → PENDING immediately) so another worker takes it without
waiting for expiry. A task is never silently lost.

## Agent run lifecycle + deadline (26C-2)

The TASK stays the queue/execution authority. The RUN (PG table
`agent_runs`, `runtime.queue.RunControl`) is the BUSINESS lifecycle
authority: QUEUED → RUNNING → {SUCCEEDED, FAILED, TIMED_OUT,
CANCELLED}, with WAITING_HUMAN for HITL and CANCEL_REQUESTED for
operator intent. Every terminal-destiny decision (success, defer,
failure/retry, cancel, expiry) writes run + task in ONE PostgreSQL
transaction — a late worker, duplicate command or racing operator
can never leave them contradictory. The run deadline is ABSOLUTE
(set once at submit, DB clock; retry never resets it) and is
enforced at control points (before start / settle-success / retry /
approval-resume + pull-based `expire_overdue()`, no daemon). A
completion after the deadline is never accepted (TIMED_OUT);
terminal runs cannot be revived by approval, retry, lease recovery
or late workers. Workers opt in via `AgentTaskWorker(run_control=…)`;
without it the 26A/26B path is unchanged. See
PHASE_26C2_RESULT.md.

## DB failure (fail closed)

Claim/store failures raise `QueueError` (never fabricated
emptiness). A critical write whose outcome cannot be determined
(connection lost mid-flight) raises `OutcomeUnknown` — the worker
surfaces `RECOVERY_REQUIRED` and never assumes success/failure.

## Observability propagation

Task rows carry `request_id/correlation_id/trace_id`; the worker
ADOPTS them as its TraceContext for execution. Every worker log line
answers: worker_id, worker_instance_id, task_id, lease_id, attempt,
trace_id. Sinks stay stderr/file — stdout remains product-only
(Phase 25.1 invariant, re-verified during worker runs).

## Verified scale (engineering, single host)

3 processes × 12 tasks and 5 processes × 50 tasks: every task
succeeded exactly once, attempt stayed 1 (no contention losses), all
workers shared the queue, 50 tasks in 4.7s. NOT a production
throughput claim.
