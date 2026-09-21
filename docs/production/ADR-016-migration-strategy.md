# ADR-016: Migration Strategy

## Status: APPROVED (design only — implementation starting Phase 22)

## Context

Current: all state in JSON/JSONL files. Target: PostgreSQL + Object
Storage. Must not break existing contracts.

## Principle

Skill contracts are UNCHANGED. The database is persistence, not
business logic. Skills still produce schema-validated artifacts.

## Migration Steps (in dependency order)

### Migration 1: Project metadata
- Old: projects.json index
- New: PostgreSQL projects table
- Dual read: yes (compatibility layer reads either)
- Dual write: during transition
- Rollback: fallback to projects.json
- Verification: row count == JSON entry count; spot-check fields

### Migration 2: Task state
- Old: case_state.json tasks[] (in-memory + file)
- New: PostgreSQL tasks table
- Depends on: Migration 1

### Migration 3: Checkpoints
- Old: checkpoints.jsonl
- New: PostgreSQL checkpoints table
- Depends on: Migration 2

### Migration 4: Artifacts
- Old: artifacts/*.json files
- New: metadata in PostgreSQL + content in Object Storage
- Depends on: Migration 1

### Migration 5: Audit events
- Old: events.jsonl
- New: PostgreSQL audit_events table
- Independent of other migrations

### Migration 6: Approvals
- Old: approvals.jsonl
- New: PostgreSQL approval_requests + approval_decisions
- Depends on: Migration 1

### Migration 7: Knowledge registry
- Old: JSON files (pilot_sources.json, weknora_*.json)
- New: PostgreSQL knowledge_sources + knowledge_versions
- Independent of other migrations

### Migration 8: User identity
- Old: env-var API keys
- New: PostgreSQL users + organizations + memberships
- Depends on: all above (needs multi-tenant infrastructure)

## Compatibility Layer

A `runtime/state/` implementation that can read from either JSON
files or PostgreSQL, selected by configuration. This allows gradual
migration with per-project cutover and instant rollback.

## Rollback Strategy

Each migration step can be rolled back independently by switching
the compatibility layer back to JSON file reads. Data written to
PostgreSQL during dual-write is retained but not read after rollback.
