# ADR-008: Production Persistence (PostgreSQL)

## Status: APPROVED (design only — no implementation in Phase 21)

## Context

Current persistence is JSON/JSONL files on a single filesystem.
This works for single-node development but cannot support concurrent
workers, multi-tenancy, transactions, or horizontal scaling.

## Decision

Migrate all structured state to **PostgreSQL** in Phase 22.
See DATA_ARCHITECTURE.md for the full target schema.

What moves: project metadata, task state, checkpoints, approvals,
artifact metadata, knowledge registry, audit events, identity.
What stays out: artifact content (Object Storage), WeKnora chunks,
LLM prompts.

What does NOT change: skill contracts, governance rules, evidence/
provenance contracts, orchestrator logic, data-chain invariant.

## Why PostgreSQL

- Needs transactions (task + checkpoint + artifact atomically)
- Needs concurrent access (multi-worker task claiming)
- Needs relational integrity (task dependencies, artifact lineage)
- Needs indexing (query by status, project, time)
- Mature, well-understood, existing team knowledge

## Trade-offs

Pro: transactions, concurrency, indexing, multi-tenant, mature.
Con: infrastructure dependency, migration effort, connection management.
