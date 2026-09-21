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

## Principle

Each item is deferred because its DEPENDENCY is not yet met.
Installing infrastructure before the architecture that uses it is
wasted effort and creates lock-in before the design is validated.
