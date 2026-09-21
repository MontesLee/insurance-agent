# Agent Worker Runtime — Phase 26B (as implemented)

The real insurance agent workflow now runs ON the 26A distributed
task foundation. Direct runtime and worker runtime produce the SAME
business results; every distributed concern (lease, crash, retry,
HITL hand-off, cancellation) is handled OUTSIDE the business layers.

## Task boundary (TASK_BOUNDARY_MAP)

One queue task == ONE AGENT RUN (`task_type=agent-run`). The skill
graph, per-stage repair, eval gates and checkpoints stay INSIDE the
existing orchestrator — a worker executes the orchestrator, never
business logic. Skills are queue-agnostic (zero `.trae/skills`
imports of `runtime.queue`; verified by grep).

```
queue task (agent-run) → AgentTaskWorker → orchestrator.run/resume
  → client-intake → requirement → risk → gap → solution
  → knowledge-search → product-candidates → recommendation → report
  → artifacts + checkpoints → idempotent settle
```

## Direct vs worker runtime

| Concern | Direct (RunManager) | Worker runtime (26B) |
|---|---|---|
| execution | in-process thread | any worker process, PG-claimed |
| checkpoints | run dir | `run_root/attempt-N/` (physical attempt isolation) |
| HITL gate | approve loop in-process | task DEFERS, lease released, human approves, another worker resumes |
| crash | process loss | lease expiry → requeue → next worker resumes from the newest checkpoint lineage |
| trace | request-scoped | task-carried req/corr/trace ADOPTED by the worker |

## ExecutionContext (26B-04/05)

The authoritative task row carries project/run/case/task ids,
req/corr/trace, attempt, worker_id + worker_instance_id. Downstream
records (knowledge.search, llm.call) inherit the CONTEXT identity
through the adopted TraceContext; the worker's own task.* records
carry worker/lease/attempt; everything joins on task_id — from any
artifact or error you can answer which run / task / worker / attempt
/ lease / trace.

## Checkpoint integration (26B-06, §10)

Attempt N reads the newest checkpoint from attempt dirs N-1..1
(newest-first, forward-only) and writes only to its OWN dir. A stale
attempt's late writes land in its already-superseded dir — they can
never roll a newer attempt's state backward (stale checkpoint
rejection by construction).

## HITL (26B-12, §18-20)

A run pausing at a human gate does NOT hold the lease: the worker
persists the paused state as a checkpoint and DEFERS (FAILED +
`WAITING_FOR_APPROVAL@stage`; a legal 26A state, semantics frozen).
`QueueOps.approve_and_resume` (OWNER/REVIEWER/OPERATOR) writes an
approval marker bound to (project, run, task, stage) and requeues;
the next worker re-verifies the marker against ITS task and stage —
an approval for task A can never resume task B, and a worker NEVER
auto-approves a gate. REJECT cancels (terminal, fail closed).

## Cancel (26B-13, closes F26A-P2-01)

`QueueOps.cancel`: OWNER/OPERATOR only (REVIEWER and unauthenticated
DENIED), audited to `queue_ops_events` (actor/role/project/run/task/
reason/timestamp). A cancelled task is terminal and can never be
completed (the 26A CAS refuses any later write; verified).

## Retry layering (26B-11)

Provider retry (transport) < LLM retry (gateway, ≤2, transient) <
Skill repair (in-case, ≤2) < TASK retry (queue, attempt<max_attempts
on agent-level failure). One task failure = one bounded requeue with
attempt+1 and a recorded retry_reason; no multiplication (the gateway
does not re-run per task attempt, it runs per call as always).

## Duplicate execution & idempotency (§11/§12)

Honest semantics: **at-least-once execution + idempotent completion +
stale-lease rejection + checkpoint recovery** — exactly-once is NOT
claimed. A crash between business completion and settle can re-run
the pipeline, but: duplicate settles are DUPLICATE_SUCCESS no-ops
(first result stands), stale leases are rejected, artifacts are
deterministic for deterministic skills, and the queue holds exactly
one terminal result per task.

## Security

Cross-project: tasks carry project_id; results/artifacts stay inside
the task's own run root (verified across 6 concurrent runs on 2
projects). Cross-task/cross-worker: lease CAS (forged or foreign
lease ids rejected — re-verified at the agent layer). Approval and
cancel are role-gated + audited. Sensitive data: observability fields
only; no payloads in logs (Phase 25 redaction unchanged).

## Measured (engineering, single host, correctness-oriented)

2 workers / 4 agent runs: 1.13 runs/s · 5 workers / 10 runs: 1.38
runs/s (retries = HITL defers, by design; every run COMPLETED exactly
once). Multi-process queue behavior proven in 26A. NOT a production
capacity claim.
