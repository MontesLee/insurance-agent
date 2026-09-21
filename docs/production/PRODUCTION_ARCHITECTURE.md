# Production Architecture — Phase 21

Date: 2026-09-21 · Status: DESIGN ONLY — no infrastructure installed,
no code modified. This document defines the TARGET architecture that
the current prototype would migrate toward.

## 1. Current Architecture (measured from code)

```text
┌─────────────────────────────────────────────────────────────────┐
│                    Current (single process)                      │
│                                                                  │
│  Entry: FastAPI server (runtime/server.py)                       │
│    ↓                                                             │
│  Orchestrator (runtime/orchestrator.py)                         │
│    YAML-driven stage graph, artifact freeze, eval boundary      │
│    ↓                                                             │
│  Harness (runtime/harness/harness.py)                           │
│    Bounded parallel DAG scheduler, project lifecycle            │
│    ↓                                                             │
│  Skills (9, .trae/skills/*/ + runtime/agent/tools.py)          │
│    Schema-validated contracts (contracts/*.schema.json)         │
│    ↓                                                             │
│  KnowledgeService (knowledge/service.py)                        │
│    Provider → Governance → Evidence → Provenance               │
│    ↓                                                             │
│  KnowledgeProvider (knowledge/provider/)                        │
│    ├── MockKnowledgeProvider (deterministic BM25, offline)     │
│    └── WeKnoraLiveProvider (HTTP → WeKnora v0.8.0, Docker)    │
│                                                                  │
│  Persistence: ALL filesystem, single-node                        │
│    projects.json     ← global index (FileLock-protected)        │
│    case_state.json   ← per-project state (encrypted at rest)   │
│    events.jsonl      ← append-only event log                    │
│    checkpoints.jsonl ← per-project checkpoints                  │
│    approvals.jsonl   ← per-project approval records             │
│    artifacts/        ← per-project artifact files               │
│                                                                  │
│  Auth: API-key bearer (runtime/auth.py)                         │
│    OWNER/REVIEWER/OPERATOR rank-based RBAC                      │
│                                                                  │
│  Control: HITL approval gateway + HOTL control commands        │
│  Recovery: checkpoint fingerprints + cross-process resume        │
│  Lifecycle: backup/restore/retention/erasure (Stage 1)         │
└─────────────────────────────────────────────────────────────────┘
```

**Key limitation**: Everything is single-process, single-node,
filesystem-bound. The FileLock is advisory and only works within
one machine. No queue, no database, no distributed coordination.

## 2. Target Production Architecture

```text
┌──────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Client  │────▶│  API Gateway     │────▶│  Auth (OIDC/    │
│  / UI    │     │  (rate limit,    │     │  OAuth2 + RBAC) │
│          │     │   TLS, routing)  │     └─────────────────┘
└──────────┘     └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │  Job / Task API  │  ← creates jobs, returns IDs,
                 │  (REST/gRPC)     │    clients poll or subscribe
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Queue /          │  ← durable, at-least-once,
                 │ Dispatcher       │    idempotency-keyed
                 └────────┬─────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Worker 1 │ │ Worker 2 │ │ Worker N │  ← horizontal scale
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │             │             │
             └─────────────┼─────────────┘
                           │
                           ▼
                 ┌──────────────────┐
                 │ Agent             │  ← UNCHANGED core logic:
                 │ Orchestrator     │     skills, contracts, eval,
                 │ (same code)      │     governance, evidence,
                 └────────┬─────────┘     provenance, recommendation
                          │
            ┌─────────────┼─────────────┐
            ▼             ▼             ▼
     ┌────────────┐ ┌───────────┐ ┌────────────┐
     │ Knowledge  │ │   LLM     │ │   Object   │
     │ Provider   │ │  Gateway  │ │  Storage   │
     │ (existing  │ │           │ │ (artifacts│
     │  contract) │ │           │ │  reports)  │
     └─────┬──────┘ └─────┬─────┘ └────────────┘
           │              │
           ▼              ▼
     ┌──────────┐   ┌───────────┐
     │ WeKnora  │   │ Model     │
     │ (HA      │   │ Providers │
     │  cluster)│   │ (LLM API) │
     └──────────┘   └───────────┘

Persistence:
  PostgreSQL ← all structured state (projects, cases, tasks,
              checkpoints, approvals, audit events, knowledge
              registry, evaluation results)
  Object Storage ← large content (artifacts, reports, snapshots)
  Redis ← DEFER (see ADR-010 for necessity analysis)
```

## 3. What Changes vs. What Doesn't

### UNCHANGED (the architectural core is production-ready)

| Component | Why unchanged |
|---|---|
| Skill contracts (11 schemas) | Database is persistence, not business logic |
| Data-chain invariant | Enforced by orchestrator, independent of storage |
| Governance rules (9) | Deterministic, registry-based; registry just moves to DB |
| Evidence + citation tuple | Contract unchanged; storage backend changes |
| Provenance (P001-P010) | Hash-anchored; hashes work regardless of storage |
| KnowledgeProvider protocol | Already abstracted; Mock↔WeKnora swap proven |
| Eval engine | Deterministic rules, no storage coupling |
| HITL approval state machine | Logic unchanged; store moves to DB |
| Fail-closed posture | Architectural principle, not infrastructure |
| Contamination invariant | Checks artifact content, not storage |
| LLM tool-calling boundary | Bounded by schemas.py, unchanged |

### CHANGED (infrastructure migration)

| Component | Current | Target | Why |
|---|---|---|---|
| Persistence | JSON/JSONL files | PostgreSQL | Indexing, transactions, concurrent access |
| Concurrency | FileLock (single node) | DB transactions + row locks | Multi-worker coordination |
| Task dispatch | Direct function call | Queue + Worker | Async, retry, horizontal scale |
| Artifact storage | Local filesystem | Object Storage | Durability, size, access control |
| Authentication | API-key bearer | OIDC/OAuth2 + JWT | Multi-tenant, service-to-service |
| Event log | append-only JSONL | PostgreSQL table + optional stream | Queryable, durable |
| LLM calls | Mock / 0 calls | LLM Gateway → Model Provider | Real cost, rate limit, fallback |
| Knowledge | Single WeKnora Docker | HA WeKnora cluster | Availability, scaling |
| Observability | stdout + trace files | Structured logging + metrics + tracing | Production operations |

## 4. Production Environment Model

```text
DEV          → local development, mock everything, no PII
STAGING      → real infrastructure, synthetic data, no PII
CONTROLLED_  → real WeKnora, real knowledge, real LLM (verified),
PILOT           limited users, full audit
PRODUCTION   → full scale, multi-tenant, full DR
```

Maps to existing `runtime/mode.py`:
- `DEMO` → maps to DEV (current default)
- `EVALUATION` → maps to STAGING
- `CONTROLLED_PILOT` → maps to CONTROLLED_PILOT (already exists)
- `PRODUCTION` → maps to PRODUCTION (already exists, unused)

The mode system is ALREADY designed for this progression — no code
change needed. Each mode gates: encryption, final-review, provider
policy, CORS strictness.

## 5. Dependency Order for Implementation

```text
Phase 22: PostgreSQL data layer (highest value, most dependencies)
   ↓
Phase 23: LLM Gateway (real LLM, cost tracking, provider policy)
   ↓
Phase 24: Production Knowledge (HA WeKnora, registry in DB)
   ↓
Phase 25: Observability (metrics, traces, structured logs)
   ↓
Phase 26: Reliability / Scale (Queue, Workers, multi-instance)
   ↓
Phase 27: Security (OIDC, service auth, key rotation)
   ↓
Phase 28: HITL Production (approval workflows, notifications)
   ↓
Phase 29: Production Evaluation (online + offline)
   ↓
Phase 30: Controlled Pilot → Production
```

Each phase depends on the ones above it. PostgreSQL MUST come first
because everything else needs a database. Queue/Workers come AFTER
the data layer because the queue needs to store state in the DB.
LLM Gateway can be built in parallel with PostgreSQL.
