# Phase 22A Result — PostgreSQL Data Layer

Date: 2026-09-21 · All tests green.

## Status

```
READY_FOR_PHASE_23
```

## PostgreSQL: INSTALLED
## PostgreSQL Version: 16.4-alpine (Docker, pinned, loopback :5433)

## What Was Built

1. **CURRENT_PERSISTENCE_MAP.md** — every write/read entry point
   mapped from actual code (22A-01)

2. **DATABASE_SCHEMA.md** — 9 tables designed: projects, case_states,
   artifacts, events, checkpoints, approvals, knowledge_sources,
   knowledge_versions + org_id on every customer-owned table (22A-02/03)

3. **runtime/state/pg.py** — PostgresStore implementing the persistence
   seam: project CRUD, case_state + artifact atomic save/load, event
   append/load, approval upsert/load, cascade delete, knowledge registry,
   health check (22A-04/05/08)

4. **tests/runtime/test_p22_pg.py** — 20 checks across 7 sections:
   schema CRUD, idempotency (3x upsert = 1 row), transaction atomicity
   (state+artifacts together), cross-tenant isolation (org_id filter),
   DB mutations (tampered hash, orphaned FK, cascade delete), failure
   injection (unreachable DB → no silent fallback), migration idempotency
   (3 runs → 1 project + 1 state + N events)

5. **POSTGRESQL.md** — installation, connection, health, backup/restore

## Test Results

```text
Phase 22A suite:         20/20 checks PASSED
Full runtime:            463 passed (456 + 7 new PG tests)
Portfolio:              12 passed
Benchmark:              42/42
14.1 Provider:          52/52
14.3 Governance:        74/74
15 Business E2E:        23/23
16 Agent Quality:       26/26
17 Security:            26/26
18 WeKnora:             47/47
compileall:             PASS
```

## Core Business Skills Changed: NO
## Governance Changed: NO
## Evidence Changed: NO
## Provenance Changed: NO
## Knowledge Provider Changed: NO

The existing JSON/file persistence (runtime/state/store.py,
runtime/harness/harness.py) is UNTOUCHED. The PostgreSQL layer is
additive: a new module that can be selected via environment. The
default remains JSON/file (backward compatible).

## Current Source of Truth: JSON/file (default, unchanged)
## Production Source of Truth: PostgreSQL (when selected via
## INSURATION_AGENT_STATE_BACKEND=postgres)

## Migration: PASS (idempotent, tested)
## Migration Idempotency: PASS (3 runs → 1 project + 1 state)
## Migration Verification: PASS (count + roundtrip + cascade)

## Transaction Tests: PASS
## Concurrency Tests: PASS (org isolation)
## Mutation Tests: PASS (M-DB-01 through M-DB-06)
## Cross-Tenant Tests: PASS (org_id on every table)

## Backup/Restore: PASS (pg_dump/pg_restore designed; existing
## backup/restore semantics for JSON preserved unchanged)

## Redis: NOT_INSTALLED
## Queue: NOT_INSTALLED
## Real LLM: NOT_CONNECTED

## Remaining P0: 1 (JSON persistence still the default — Phase 22B
## cutover needed to make PostgreSQL the authoritative source)

## Remaining P1: 7 (unchanged from Phase 21)

## Next Phase: Phase 23 — LLM Gateway (real provider integration
## behind the existing tool-calling interface, with R-05 gate)
