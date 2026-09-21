# Failure Model — Phase 21

## Infrastructure Failures

| Failure | Detection | Impact | Recovery | Data Loss |
|---|---|---|---|---|
| API crash | Health check | New requests fail | Restart (stateless) | None |
| Worker crash | Lease expiry | Task paused | Re-claim + checkpoint resume | None (last checkpoint) |
| DB unavailable | Connection error | All writes fail | DB failover | None (if sync replication) |
| WeKnora unavailable | Provider error | Knowledge search fails | Circuit breaker → NEEDS_REVIEW | None |
| LLM provider down | Timeout | LLM-dependent skills fail | Circuit breaker → retry → NEEDS_REVIEW | None |
| Object Storage down | Upload error | Artifact write fails | Retry with backoff | None if retried |

## Application Failures

| Failure | Detection | Impact | Recovery |
|---|---|---|---|
| Duplicate task | Idempotency key | Second execution is no-op | Automatic |
| Stale checkpoint | Fingerprint mismatch | Checkpoint rejected | Re-execute from last valid |
| Corrupted artifact | Hash mismatch | Evidence rejected | Re-generate |
| Concurrent update | Optimistic lock | One write wins, other retries | Automatic |
| Split brain | Lease conflict | Stale worker fails on write | Automatic |

## Human Failures

| Failure | Detection | Impact | Recovery |
|---|---|---|---|
| Approval timeout | expires_at | Task stays NEEDS_REVIEW | Escalate or auto-reject |
| Operator cancellation | API call | Task CANCELLED | Notify stakeholders |
| Conflicting approvals | DB constraint | Second approval fails | Surface conflict |

## Data Failures

| Failure | Detection | Impact | Recovery |
|---|---|---|---|
| Accidental deletion | DB backup | Data loss | Restore from backup |
| Corruption | Hash check | Evidence rejected | Re-generate from source |
| Partial write | Transaction rollback | No partial state visible | Automatic |
| Backup failure | Monitoring alert | DR compromised | Fix before incident |
