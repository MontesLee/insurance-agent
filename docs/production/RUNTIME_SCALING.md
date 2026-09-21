# Runtime Scaling — Phase 21 (design only)

## Current: Single Process

```
FastAPI server (1 process)
  → Orchestrator (in-process)
    → Scheduler (1 thread, in-process)
      → Skills (in-process function calls)
        → KnowledgeProvider (in-process)
        → LLM tools (in-process)
```

Limitations: no concurrent cases, no horizontal scale, no crash
isolation, no retry after worker death.

## Target: Multi-Worker

```
API Gateway (stateless, N replicas)
  → Job API → Queue (PostgreSQL SKIP LOCKED)
    → Worker 1..N (each runs the same Orchestrator code)
      → Task claiming via lease
      → Checkpoint per task
      → Artifact write to Object Storage
      → Skill execution (same contracts)
        → KnowledgeProvider (same interface)
        → LLM Gateway (same interface)
```

## Task Claiming Protocol

```sql
-- Worker claims a task (atomic, no race):
UPDATE tasks
SET claimed_by = $worker_id,
    lease_expires = now() + interval '5 minutes',
    status = 'RUNNING'
WHERE task_id = $task_id
  AND status = 'QUEUED'
  AND (lease_expires IS NULL OR lease_expires < now())
RETURNING *;
-- If 0 rows: another worker got it → move on
```

## Duplicate Execution Prevention

Three layers:
1. **Lease**: only one worker holds the lease at a time
2. **Idempotency key**: unique constraint prevents double-insert
3. **Checkpoint fingerprints**: stale worker's writes fail on
   fingerprint mismatch

## Worker Lifecycle

```
START → pick task (SKIP LOCKED) → load checkpoint → execute skill
  → write artifact → update task → write checkpoint → release
  → pick next task
HEARTBEAT → update lease_expires (every 60s)
CRASH → lease expires → task returns to QUEUED → other worker
```

## What the Orchestrator Does NOT Change

- Stage ordering (same YAML)
- Artifact contracts (same schemas)
- Eval boundary (same invariants)
- Governance (same rules)
- Evidence/provenance (same validators)
- Data-chain invariant (same enforcement)

Only the persistence seam (`runtime/state/`) and the task dispatch
mechanism change.
