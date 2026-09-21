# ADR-013: Multi-Instance Runtime

## Status: APPROVED (design only — implementation in Phase 26)

## Context

Current: single process, single node, FileLock-based coordination.
Target: N workers on M nodes, coordinated by PostgreSQL.

## Key Challenges

### 1. Task ownership (no duplicate execution)

**Solution**: PostgreSQL `SELECT ... FOR UPDATE SKIP LOCKED` +
lease_expires column. A worker atomically claims a task; no other
worker can claim the same task until the lease expires.

**Proof**: The idempotency_key constraint provides a second barrier:
even if two workers somehow start the same task, the second is a
no-op.

### 2. Scheduler ownership

**Current**: The harness's scheduler thread runs in-process.
**Target**: No central scheduler. Workers pull tasks from the queue
when their dependencies are met (depends_on all COMPLETED). The
orchestrator creates tasks + dependencies; workers execute them.

### 3. Checkpoint ownership

**Current**: Per-project checkpoint file, written by the running
process.
**Target**: Checkpoint in PostgreSQL, written by the worker that
owns the task lease. Cross-worker checkpoint reading is safe (read
past checkpoints, write only your own).

### 4. Approval ownership

**Current**: Approval state transitions in-process.
**Target**: Approval state in PostgreSQL; transitions use optimistic
concurrency (`WHERE status = 'WAITING_HUMAN'`). Double-approval is
prevented by the WHERE clause.

### 5. Event ordering

**Current**: Append-only JSONL, single writer.
**Target**: PostgreSQL BIGSERIAL event_id provides global ordering.
Events from different workers interleave but the sequence is
deterministic.

### 6. Concurrent artifact writes

**Current**: Filesystem + artifact freeze (completed artifacts
immutable). 
**Target**: Artifact insert is a DB transaction; concurrent inserts
for the same (project_id, artifact_type) are prevented by unique
constraint. The existing freeze semantics carry over.

### 7. Split brain / stale worker

**Solution**: Lease expiry. If a worker dies, its lease expires,
and another worker picks up the task. The stale worker's late
writes fail on the idempotency_key.

### 8. Worker crash mid-task

**Solution**: Checkpoint + lease expiry. The task returns to QUEUED,
the next worker resumes from the last checkpoint. The existing
RUNNING→PENDING recovery logic in the harness already handles this
semantically; PostgreSQL makes it cross-process.

## What guarantees resume doesn't bypass?

- **Approval**: Resume recreates the task state including approval
  status. If the task was WAITING_HUMAN, it resumes as WAITING_HUMAN,
  not as running.
- **Governance**: Governance runs on every knowledge retrieval,
  regardless of resume. No bypass.
- **Provenance**: Provenance validation runs on evidence consumption,
  regardless of how the task was restarted.
