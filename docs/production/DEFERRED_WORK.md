# Deferred Work — Phase 21

What is NOT being done now, why, and when.

| Item | Why Deferred | Dependency | Target Phase |
|---|---|---|---|
| PostgreSQL install | Architecture first, infra later | This document | P22 |
| Redis install | Not justified at pilot scale | Measured QPS >1000 | P26+ |
| Queue (RabbitMQ/Kafka) | PostgreSQL SKIP LOCKED suffices | Multi-worker need | P26 |
| Object Storage (MinIO/S3) | Design only; artifacts still local | PostgreSQL metadata | P22 |
| Real LLM (OpenAI etc.) | R-05 BLOCKED; LLM Gateway design first | Gateway + operator verification | P23 |
| OIDC / Keycloak | Current API-key auth works for pilot | Multi-tenant requirement | P27 |
| Production WeKnora HA | Single Docker instance is pilot | HA requirement | P24 |
| Kubernetes / Docker Swarm | Single-node is sufficient | Multi-node requirement | P26+ |
| Load testing | No production data | PostgreSQL + LLM + real corpus | P29+ |
| Multi-tenant implementation | Single-tenant pilot is the current scope | P22 data model supports it | P27 |
| Prometheus/Grafana | Existing evaluator covers correctness | Production deployment | P25 |
| TLS everywhere | Local loopback is pilot | Public deployment | P27 |
| RV-P3-01: live-eval test determinism | F-24 A/B assertion depends on live hit mix (safety property itself unit-proven deterministically) | Next revision of tests/runtime/test_p24_live_eval.py | P25+ |
| RV-P3-02: backup restore verification | pg_dump verified generatable + content-complete; restore never exercised | DR scheduling decision (with automated backup) | P26 |
| RV-P3-03: document_hash self-check | source-level ingestion anchor is recorded but verified by neither selfcheck nor runtime | Next registry hardening round | P25+ |
| RV-INFO-01: full compose restart exercise | app-container restart + named-volume static verification done; docker compose down/up not run | Ops window on the dev stack | P25 |
| F26A-P2-01: queue cancel() auth gate | cancel is operator-authority via DB access only (single-operator pilot acceptable) | Multi-party operation / operator-role integration | P26B |
| F26A-P3-01: lease-recovery reaper | recovery is pull-based (claims pick up expired leases directly, so nothing blocks); no background timer | Phase 26B worker deployment design | P26B |
| F26A-P3-02: dead-letter queue | max_attempts-exhausted tasks stay FAILED in-place (queryable) — no separate DLQ surface | Operator tooling round | P26B+ |
| F26A-INFO-01: idle drain polling | run_until_empty polls list() per idle cycle — fine at pilot scale | LISTEN/NOTIFY or backoff when scale demands it | P26B |

## Principle

Each item is deferred because its DEPENDENCY is not yet met.
Installing infrastructure before the architecture that uses it is
wasted effort and creates lock-in before the design is validated.
