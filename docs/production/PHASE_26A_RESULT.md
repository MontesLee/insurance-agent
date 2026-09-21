# Phase 26A Result — Distributed Task Execution Foundation

Date: 2026-09-21 · Baseline 59bb76f (verified exact before start) ·
Queue suite 74/74 · scale runs green.

## Status

```
PRODUCTION_DISTRIBUTED_TASK_FOUNDATION_READY_WITH_DOCUMENTED_DEBT
```

(see Findings — one P2, three P3; none block Phase 26B)

## What was built

`runtime/queue/` — PostgreSQL as the ONLY queue and task-state
authority; workers are stateless executors with INJECTED executors
(business skills queue-agnostic, verified by grep: zero `.trae/skills`
imports). Full design: DISTRIBUTED_TASK_EXECUTION.md.

| Piece | Proof |
|---|---|
| Task state machine (PENDING→LEASED→RUNNING→SUCCEEDED / FAILED→PENDING / LEASE_EXPIRED→PENDING / CANCELLED) | E26-01: legal×9 + illegal×6 refused; expiry never reaches SUCCEEDED |
| Task identity (qt_-prefixed, globally unique; (task_id, attempt) = idempotency_key) | E26-02 |
| Worker identity (logical worker_id + per-process-lifetime worker_instance_id; never host/pid/thread alone) | E26-03 (50 unique) |
| Atomic claim: single UPDATE…WHERE task_id=(SELECT…FOR UPDATE SKIP LOCKED) with attempt+1 + lease in ONE transaction | E26-05/06: 4-connection race → exactly one winner; locked rows skipped fast |
| Lease ownership: every write lease-guarded; stale/mismatched/expired → LeaseRejected (DB-clock decided) | E26-09, M26-03/09 |
| Idempotency: duplicate succeed/fail → DUPLICATE_SUCCESS no-op, FIRST result stands; terminal never re-claimable | E26-08, M26-05/06/10 |
| Crash recovery: expired lease → recover_expired → requeue → next claim attempt+1; stale worker's completion rejected; current owner's truth stands | E26-10 end-to-end |
| Heartbeat: owner-only lease extension | E26-11 (mismatched + expired refused) |
| Bounded retry: fail requeues while attempt<max; stays FAILED at max | E26-14 |
| Backpressure: max_concurrent caps claiming | worker at capacity stops (E26-15 asserts claim refusal) |
| Graceful shutdown: SIGTERM → stop claiming → settle or RELEASE (immediately PENDING, no silent loss) | E26-15 |
| DB failure fail-closed: QueueError on claim; OutcomeUnknown → RECOVERY_REQUIRED (never assume; worker hardened not to crash-loop) | E26-13 (incl. a real defect found & fixed: settle-time raw DB loss used to escape the worker) |
| Observability propagation: task-carried request/correlation/trace ids ADOPTED as worker TraceContext; every log line answers worker/instance/task/lease/attempt/trace | E26-16 |
| stdout stays product-only during worker execution | E26-17 (captured stdout empty) |
| Business invariance: real coverage-gap engine, direct vs worker-queued → deep-equal result | E26-18 |

## Concurrency evidence (engineering, single host)

- 3 OS processes × 12 tasks (E26-12): 12/12 succeeded exactly once,
  all attempts=1, ≥2 workers shared the queue
- 5 OS processes × 50 tasks: 50/50 once, attempts=1, 5 workers, 4.7s
- 4 concurrent connections racing one task: exactly one lease
- SKIP LOCKED behavior: locked row skipped without blocking

Execution semantics are AT-LEAST-ONCE + idempotent completion +
stale-lease rejection. Exactly-once is NOT claimed.

## Mutations M26-01..10

SKIP LOCKED presence (structural+behavioral), duplicate-lease
impossibility, forged-lease rejection (succeed/heartbeat/release),
attempt identity, terminal overwrite rejection, terminal
re-claim refusal, single-statement claim — all detected (74/74).

## Security

Lease IS the write authority: worker/task/lease spoofing reduces to
guessing an unguessable lease_id; cross-worker writes rejected
(E26/M26 + §29 section); ownership truth visible in PG columns
(worker_id/lease_owner). Cancel is operator-authority by design
(documented).

## Regression

(full battery re-run clean after an anomalous 2:41h run was
investigated: the queue suite itself measures 11.75s under pytest;
the anomaly was environmental machine slowness during the first
battery — final numbers below are from the clean run)

```
Runtime:     530 passed in 11:38  (513 pre-existing + 17 new p26a tests;
            slowest durations are the known heavy suites — no anomalies)
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
p24/p25 suites unchanged and green inside the runtime battery
```

## Findings

| ID | Severity | Finding |
|---|---|---|
| F26A-P2-01 | P2 | cancel() is operator-authority WITHOUT auth integration — any process with DB access can cancel; fine for single-operator pilot, needs an operator-role gate before multi-party operation (Phase 26B candidate) |
| F26A-P3-01 | P3 | recover_expired is pull-based (worker/ops must call it); a background reaper timer is deferred — expired leases are only requeued when the next claim/recovery pass runs (claims DO pick up expired leases directly, so recovery is not blocked) |
| F26A-P3-02 | P3 | No dead-letter queue: a task failing at max_attempts stays FAILED in-place (queryable) — a DLQ table/view is future sugar |
| F26A-INFO-01 | INFO | run_until_empty's drain check polls list() per idle cycle — fine at pilot scale; a LISTEN/NOTIFY or longer idle backoff is a Phase 26B optimization |

P0 = 0 · P1 = 0 · P2 = 1 · P3 = 2 · INFO = 1

## Hard gates

HG26A-01..25: PASS (PostgreSQL authoritative; deterministic state
machine; stable identity; unique workers; lease ownership; atomic
SKIP LOCKED claim; no duplicate valid lease; attempt semantics; stale
worker rejected; idempotency; crash recovery; heartbeat ownership;
multi-process concurrency; DB fail-closed; bounded retry; graceful
shutdown; observability propagated; stdout product-only; security
isolation; business invariance; regression; mutations detected; no
Redis; no business Skill changes; scope clean — redis/kafka/celery/
k8s/otel/prometheus absent from runtime/queue).

STOP — Phase 26B NOT started (requires separate authorization).
