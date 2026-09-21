# ADR-010: Redis Decision

## Status: DEFER

## Context

"Production architecture needs Redis" is a common assumption.
This ADR applies a necessity test to each candidate responsibility.

## Candidate Responsibilities

| Responsibility | Assessment | Reason |
|---|---|---|
| A. Cache | OPTIONAL | In-process dict works for single-instance; PostgreSQL suffices for pilot |
| B. Distributed lock | NOT_RECOMMENDED | PostgreSQL `FOR UPDATE SKIP LOCKED` provides same guarantee |
| C. Rate limit | OPTIONAL | PostgreSQL rate-limit table suffices at pilot scale |
| D. Short-lived task state | NOT_RECOMMENDED | Task state needs transactional consistency; mixing Redis+PostgreSQL creates consistency risks |
| E. Queue | NOT_RECOMMENDED | PostgreSQL `SKIP LOCKED` queue is simpler and sufficient |
| F. Pub/Sub | OPTIONAL | PostgreSQL LISTEN/NOTIFY works for single-DB pub/sub |

## Final Decision

```
Redis Decision: DEFER
```

**Rationale**: Every candidate responsibility is handled by PostgreSQL
at pilot scale (<1000 QPS). Redis adds infrastructure complexity,
a second consistency model, cache invalidation, and no clear
performance win.

**Re-evaluate when**: sustained QPS > 1000, multi-region deployment,
or measured rate-limiting bottleneck.

**If adopted later**: only for (1) read-through cache with >80% hit
rate, (2) rate limiting at measured QPS. Nothing else.
