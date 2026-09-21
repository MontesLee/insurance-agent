# ADR-009: Queue and Worker Architecture

## Status: APPROVED (design only — implementation in Phase 26)

## Context

Current execution is synchronous in-process. No queue, no workers.
Cannot support concurrent cases, retry after crash, or horizontal
scaling.

## Decision

Introduce Queue + Worker in Phase 26 (after PostgreSQL).
Technology choice deferred: PostgreSQL SKIP LOCKED (simplest),
RabbitMQ (if throughput requires), or Kafka (if event streaming
becomes a requirement).

## Key Design Decisions

1. **Idempotency**: task has idempotency_key (project_id + type +
   input_hash). Duplicate execution is a no-op.

2. **Lease-based claiming**: worker claims task by setting claimed_by
   + lease_expires in a DB transaction. Expired lease = claimable.

3. **Heartbeat**: long-running workers update lease_expires to
   prevent premature expiry.

4. **Retry classification**:
   - Transient (network) → retry with backoff
   - Permanent (schema) → NEEDS_REVIEW
   - Business (eval FAIL) → NEEDS_REVIEW after max repair
   - Provider (LLM down) → circuit breaker, then retry

5. **Cancellation**: sets CANCELLED; workers check before sub-tasks.

## Task Lifecycle

```
CREATED → QUEUED → CLAIMED → RUNNING → COMPLETED
                              ↓
                          FAILED → RETRYING → QUEUED (max 3)
                              ↓
                          NEEDS_REVIEW
                              ↓
                          CANCELLED
```
