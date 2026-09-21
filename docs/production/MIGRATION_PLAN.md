# Migration Plan — Phase 21 (design only)

## 8-Step Migration: JSON/File → PostgreSQL + Object Storage

| # | What | Old | New | Depends on | Rollback |
|---|---|---|---|---|---|
| 1 | Project metadata | projects.json | PostgreSQL projects | — | Fallback to file |
| 2 | Task state | case_state.json tasks[] | PostgreSQL tasks | 1 | Fallback to file |
| 3 | Checkpoints | checkpoints.jsonl | PostgreSQL checkpoints | 2 | Fallback to file |
| 4 | Artifacts | artifacts/*.json | PG metadata + Object Storage content | 1 | Fallback to file |
| 5 | Audit events | events.jsonl | PostgreSQL audit_events | — | Fallback to file |
| 6 | Approvals | approvals.jsonl | PostgreSQL approval_requests | 1 | Fallback to file |
| 7 | Knowledge registry | JSON files | PostgreSQL knowledge_sources/versions | — | Fallback to file |
| 8 | User identity | env-var keys | PostgreSQL users/orgs/memberships | 1-7 | Fallback to env |

## Compatibility Layer

```text
runtime/state/__init__.py  ← existing persistence interface
    ↓ (swap implementation)
    ├── JSONFileStore        ← current (filesystem + FileLock)
    └── PostgresStore        ← future (transactions + SKIP LOCKED)
```

Selection by env var: INSURANCE_AGENT_STATE_BACKEND=json|postgres
Default: json (backward compatible).

## Per-Project Cutover

Projects migrate individually (not all-at-once):
1. Read from old store
2. Write to both stores (dual-write)
3. Verify: read from new store, compare
4. Switch reads to new store only
5. Stop writing to old store
6. Mark project as migrated

## What Does NOT Migrate

- Skill contracts — unchanged
- Governance rules — unchanged (registry moves to DB, logic stays)
- Evidence/provenance contracts — unchanged
- Orchestrator logic — unchanged (reads from new seam)
- Data-chain invariant — enforced above the storage layer
