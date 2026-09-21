# Disaster Recovery — Phase 21 (design only)

## Current DR (implemented and tested)

| Capability | Implementation | Tested |
|---|---|---|
| Backup | Locked snapshot + sha256 manifest | 50/50 |
| Restore | Verify-first + staging + atomic commit | 57/57 |
| Retention | Terminal-only + backup-first + erasure audit | 21/21 |
| Crash recovery | Checkpoint fingerprints + cross-process resume | All suites |

## Target DR (ASSUMPTION: single-region, sync replica)

| Scenario | RPO | RTO | Strategy |
|---|---|---|---|
| PostgreSQL failure | 0 (sync replica) | <5 min | Automated failover |
| Object Storage failure | 0 (replicated) | <5 min | Multi-AZ |
| WeKnora failure | <1 hour | <30 min | Re-deploy + re-index |
| LLM provider outage | N/A | <15 min | Circuit breaker + fail-closed |
| Full region loss | <15 min | <1 hour | Cross-region restore |
| Data corruption | Last backup | <2 hours | Restore + replay |

All RPO/RTO are ASSUMPTIONS based on typical single-region
PostgreSQL with sync replication.

## Key Principle

Fail-closed: if the system cannot guarantee evidence integrity
(hash verification, provenance validation), it does not produce
recommendations. Recovery restores verification capability.
