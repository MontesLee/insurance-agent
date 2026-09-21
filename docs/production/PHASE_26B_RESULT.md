# Phase 26B Result — Agent Runtime Integration

Date: 2026-09-21 · Baseline 8eb3007 verified (code-identical; only the
user-directed docs-only closure commit 1be94b5 on top) · Suite 68/68 ·
Regression 540/12/42 · compileall PASS.

## Status

```
PRODUCTION_AGENT_WORKER_INTEGRATION_READY_WITH_DOCUMENTED_DEBT
```

(see Findings — P2=1, P3=2, INFO=1; none block Phase 26C)

## What was built

Additive integration ON the frozen 26A foundation — zero business
Skill / orchestrator / governance / gateway changes (scope audit:
only runtime/queue/* + one test file + docs):

| Piece | Where | Proof |
|---|---|---|
| Task boundary: one queue task = one AGENT RUN | agent_runtime.make_agent_executor | E26B-01: the real 9-skill pipeline settles through the queue |
| AgentTaskWorker settle policy (HITL deferral) | agent_runtime.AgentTaskWorker | E26B-09/10 |
| Attempt-isolated checkpoint resume | run_root/attempt-N, newest-first lineage | E26B-04, C3/C5: crash mid-run → attempt 2 resumes FROM checkpoint |
| Authorized ops + audit | ops.QueueOps (cancel OWNER/OPERATOR; approve/reject OWNER/REVIEWER/OPERATOR; queue_ops_events audit) | E26B-11/12, M26B-07/08 — closes F26A-P2-01 |
| HITL hand-back with binding | approval marker (project, run, task, stage) + requeue | E26B-10: unapproved resume re-defers; approval never resumes another task |
| Typed claim isolation | worker task_types filter (additive) | suite hygiene + per-type backpressure |

26A semantics UNCHANGED: requeue is the already-legal FAILED→PENDING
transition; waiting = FAILED + WAITING_FOR_APPROVAL@stage; every CAS,
lease and idempotency guarantee from 26A holds verbatim (re-verified
in this suite).

## Gates

HG26B-01..26 all PASS. Highlights:

- **Business invariance (E26B-17, top priority)**: direct runtime vs
  queue runtime on bm-complete-001 — artifact SETS identical, artifact
  CONTENT deep-identical (timing fields excluded), terminal states
  identical (COMPLETED).
- **Crash matrix**: C1 claim-then-crash → recovered attempt 2; C3/C5
  mid-run crash → checkpoint resume; C6 duplicate settle →
  DUPLICATE_SUCCESS no-op; C7 terminal never re-claimable.
- **HITL**: defer → (unauthorized approval denied) → REVIEWER approve
  → different-worker resume from checkpoint → COMPLETED, 3 attempts,
  audited; REJECT cancels fail-closed.
- **Cancel security**: REVIEWER denied, OPERATOR allowed + audited;
  cancelled task can never complete (not claimable, settle refused).
- **Concurrent runs**: 6 agent runs / 3 workers / 2 projects — all
  COMPLETED once, isolated run roots, project partition intact.
- **Knowledge/LLM integrity**: worker path drives orchestrator →
  KnowledgeService → governance → evidence (no bypass — structural +
  behavioral: empty-KB case stays fail-closed through the queue);
  zero gateway changes.
- **Trace**: adopted context reaches knowledge/LLM records
  (req/corr/trace/task); worker/lease/attempt on task.* records;
  join on task_id answers who/which/what end-to-end.
- **stdout**: stays product-only (worker logging unchanged from 25.1).

## Failure matrix (E26B-18)

F01-F15 each with expected+actual: dead DB fails closed; stale
lease/completion rejected; unauthorized cancel/approval denied;
LLM/knowledge failures classified (TIMEOUT / NETWORK_ERROR with
operator actions); F14/F15 covered by C1 + 26A shutdown paths. No
UNKNOWN→SUCCESS anywhere.

## Mutations (E26B-19)

M26B-01..14 detected: checkpoint-lineage bypass (resume must load
newest), forged lease/task ids, auth bypass (cancel/approve),
cancelled-task completion, trace loss (context assertions),
governance/gateway bypass (structural + behavioral), wrong-task
resume (marker binding), duplicate terminal (no-op).

## Measured (engineering, single host)

2w/4 runs: 1.13 runs/s · 5w/10 runs: 1.38 runs/s; every run
COMPLETED exactly once; retries = HITL defers by design. NOT a
capacity/SLA claim.

## Regression

```
Runtime:     540 passed in 7:18  (530 + 10 new p26b tests)
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
(Phase 14-26A suites all green inside the battery)
```

## Findings

| ID | Severity | Finding |
|---|---|---|
| F26B-P2-01 | P2 | WAITING_FOR_APPROVAL reuses the FAILED status + retry_reason convention (legal 26A states, semantics frozen) — readable but a dedicated status would be clearer; changing it means unfreezing 26A → documented, deferred |
| F26B-P3-01 | P3 | Approval markers are files under run_root (single-host pilot scope); multi-host operation needs them in PostgreSQL — deferred to the worker-deployment phase |
| F26B-P3-02 | P3 | One worker instance claims across ALL its configured task types round-robin; per-type concurrency caps are future sugar (max_concurrent already bounds total) |
| F26B-INFO-01 | INFO | deferred lease COLUMNS remain set on FAILED rows (inert: status gates every transition); cosmetically imperfect, harmless |

P0 = 0 · P1 = 0 · P2 = 1 · P3 = 2 · INFO = 1

## Execution semantics (honest)

**At-least-once execution + idempotent completion + stale-lease
rejection + checkpoint recovery. Exactly-once is NOT claimed.**

STOP — Phase 26C NOT started (requires separate authorization).
