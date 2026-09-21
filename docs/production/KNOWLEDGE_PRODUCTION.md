# Knowledge Production Architecture — Phase 21 (design) / Phase 24 (registry implemented)

> Phase 24 implementation status: the governance registry rows of the
> table below are DONE — PostgreSQL is the authoritative registry in
> strict modes (lifecycle state machine, canonical chunks, at-rest
> integrity, F-24 re-anchoring). See [KNOWLEDGE_REGISTRY.md](
> KNOWLEDGE_REGISTRY.md) and [KNOWLEDGE_GOVERNANCE.md](
> KNOWLEDGE_GOVERNANCE.md). WeKnora HA, managed embeddings, key
> rotation and multi-tenant KBs remain design targets.

## Current State

Single WeKnora v0.8.0 Docker instance, local loopback, with:
- 3 KBs (pilot real docs, fixtures, smoke test)
- builtin-embedding-local for embeddings
- Agent-side governance registry — PostgreSQL-authoritative in strict
  modes, JSON projection files in non-strict modes
- Scoped retrieve-capability API keys

## Target Production State

| Aspect | Current | Target | Status |
|---|---|---|---|
| WeKnora instances | 1 (Docker) | 2+ (HA, behind load balancer) | deferred (P26+) |
| Embedding model | builtin local | Managed embedding service | deferred |
| Governance registry | PostgreSQL (strict) / JSON (non-strict) | PostgreSQL everywhere | **implemented (P24)** |
| API auth | Static API keys | Rotated keys + service JWT | deferred (P27) |
| KB isolation | Per-KB scoped keys | Per-tenant KB + RBAC | scope field ready, GLOBAL_ONLY today |
| Backup | pg_dump verified (operator procedure) | Scheduled backup | procedure verified (P24); scheduling deferred |
| Scaling | Single instance | Read replicas |
| Network | Loopback only | Private subnet, TLS |

## Registry Sync Pipeline

Current: manual sync script. Target: automated:
WeKnora upload → webhook → sync service → fetch chunks → hash →
PostgreSQL registry → cache invalidate → audit event.

## Key Constraint (preserved)

Dual-identity model: WeKnora owns retrieval; the Agent owns
governance. No production change moves governance into WeKnora.
