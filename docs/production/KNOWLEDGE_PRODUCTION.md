# Knowledge Production Architecture — Phase 21 (design only)

## Current State

Single WeKnora v0.8.0 Docker instance, local loopback, with:
- 3 KBs (pilot real docs, fixtures, smoke test)
- Ollama nomic-embed-text for embeddings
- Agent-side governance registry (JSON projection files)
- Scoped retrieve-capability API keys

## Target Production State

| Aspect | Current | Target |
|---|---|---|
| WeKnora instances | 1 (Docker) | 2+ (HA, behind load balancer) |
| Embedding model | Ollama nomic (local) | Managed embedding service |
| Governance registry | JSON files | PostgreSQL tables |
| API auth | Static API keys | Rotated keys + service JWT |
| KB isolation | Per-KB scoped keys | Per-tenant KB + RBAC |
| Backup | Docker volume only | PostgreSQL backup + WeKnora export |
| Scaling | Single instance | Read replicas |
| Network | Loopback only | Private subnet, TLS |

## Registry Sync Pipeline

Current: manual sync script. Target: automated:
WeKnora upload → webhook → sync service → fetch chunks → hash →
PostgreSQL registry → cache invalidate → audit event.

## Key Constraint (preserved)

Dual-identity model: WeKnora owns retrieval; the Agent owns
governance. No production change moves governance into WeKnora.
