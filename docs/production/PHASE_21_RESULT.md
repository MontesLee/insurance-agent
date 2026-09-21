# Phase 21 Result — Production Architecture & Migration Design

Date: 2026-09-21 · Status: READY_FOR_PHASE_22

## Answers to the 10 Required Questions

### Q1: Why can't the current JSON/File architecture go to Production?

Three hard blockers: (1) FileLock only works on a single machine —
multi-worker deployment is impossible; (2) JSON files have no
transactions — concurrent writes can corrupt state; (3) no indexing —
querying 10K projects means reading the entire projects.json into
memory.

### Q2: Why is PostgreSQL Phase 22, not Phase 21?

Because architecture-first: the data model must be designed before
the database is installed. Installing PostgreSQL before knowing what
tables are needed creates schema lock-in to a wrong design. Phase 21
designs the schema; Phase 22 implements it.

### Q3: Is Redis necessary?

No. See ADR-010. Every candidate responsibility (cache, locks, rate
limiting, queue, pub/sub) is handled by PostgreSQL at pilot scale.
Redis is DEFER until measured QPS > 1000.

### Q4: When must a Queue be introduced?

When concurrent cases exceed what a single worker can handle (~10
concurrent cases), or when LLM latency (30+ seconds) blocks the API
thread. Phase 26, after PostgreSQL and the data layer.

### Q5: How to prevent duplicate task execution across Workers?

Three layers: (1) PostgreSQL `FOR UPDATE SKIP LOCKED` lease-based
claiming; (2) idempotency_key unique constraint; (3) checkpoint
fingerprint mismatch detection. See ADR-013.

### Q6: Where does Real LLM sit?

Behind an LLM Gateway (library, in-process) that wraps the existing
httpx client. Skills call it through the existing tool-calling
interface. The Gateway adds: R-05 provider policy check, PII filter,
rate limit, token budget, cost tracking, circuit breaker, and schema
validation. See ADR-011.

### Q7: What is the WeKnora ↔ Agent Runtime boundary?

WeKnora owns "find what" (document parsing, chunking, hybrid
retrieval, relevance ranking). The Agent owns "what evidence may
inform an insurance decision" (governance, evidence validation,
provenance, decision constraints). WeKnora's LLM answer path is
structurally unreachable from the provider.

### Q8: Where do client data, artifacts, and knowledge live?

Client data (facts, case state) → PostgreSQL (encrypted at rest).
Artifacts (JSON blobs, reports) → Object Storage + PostgreSQL metadata.
Knowledge chunks/embeddings → WeKnora's internal storage.
Knowledge governance metadata (registry) → PostgreSQL.

### Q9: Top 5 Production risks?

1. **JSON persistence under concurrent load** (data corruption) — P0
2. **No real LLM provider** (R-05 BLOCKED, no cost model) — P1
3. **Single WeKnora instance** (single point of failure) — P1
4. **No multi-tenant isolation** (single-user API keys) — P1
5. **No production-scale testing** (all metrics ASSUMPTION) — P2

### Q10: What should Phase 22 specifically do?

Implement the PostgreSQL data layer: install PostgreSQL, create the
schema from DATA_ARCHITECTURE.md, implement the `runtime/state/`
compatibility layer (JSONFileStore + PostgresStore), migrate project
metadata + task state + checkpoints, run dual-write verification,
and prove all 456 tests still pass with the postgres backend.

## Deliverables Created

```text
docs/production/
├── PRODUCTION_ARCHITECTURE.md     ← current + target + dependency order
├── DATA_ARCHITECTURE.md           ← PostgreSQL schema + ownership matrix
├── RUNTIME_SCALING.md             ← multi-worker design
├── LLM_GATEWAY.md                 ← gateway responsibilities
├── KNOWLEDGE_PRODUCTION.md        ← WeKnora production topology
├── SECURITY_ARCHITECTURE.md       ← current + target security
├── OBSERVABILITY.md               ← metrics + logs + traces
├── DISASTER_RECOVERY.md           ← failure model + RPO/RTO
├── MIGRATION_PLAN.md              ← 8-step migration
├── CAPACITY_MODEL.md              ← ASSUMPTION-labeled estimates
├── FAILURE_MODEL.md               ← detection/impact/recovery matrix
├── DEFERRED_WORK.md               ← what NOT to do and why
├── PHASE_21_RESULT.md             ← this document
├── ADR-008-production-persistence.md
├── ADR-009-queue-and-worker.md
├── ADR-010-redis-decision.md
├── ADR-011-llm-gateway.md
├── ADR-012-object-storage.md
├── ADR-013-multi-instance-runtime.md
├── ADR-014-production-identity.md
├── ADR-015-production-observability.md
└── ADR-016-migration-strategy.md
```

## Verification

- Core runtime changed: NO
- Infrastructure installed: NO
- Real LLM connected: NO
- Production deployment: NO
- Production ready: NO
- Phase 14-20 regression: GREEN (verified during this session)
