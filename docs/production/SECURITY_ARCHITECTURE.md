# Security Architecture — Phase 21 (design only)

## Current State (all implemented and tested)

| Layer | Implementation | Test |
|---|---|---|
| Authentication | API-key bearer (OWNER/REVIEWER/OPERATOR) | 17 auth tests |
| Authorization | Rank-based RBAC (33 matrix cells) | 17 authz tests |
| Project isolation | Per-project dirs + charset validation | 5 isolation tests |
| PII redaction | Field-based deny-list (26 fields) | 12 PII tests |
| Encryption at rest | Fernet IA1: (strict modes) | 3 encryption tests |
| Approval security | Human-only actor; forged state detection | 13 approval tests |
| Provider policy | R-05 fail-closed gate | 6 provider tests |
| CORS | Allowlist; no wildcard outside dev | CORS tests |
| Retention | Terminal-only sweep; backup-first; erasure.log | Retention tests |

## Target Production State

| Layer | Current | Target | Phase |
|---|---|---|---|
| Auth | API-key env vars | OIDC/OAuth2 + JWT | P27 |
| Service auth | Shared API keys | mTLS or service JWT | P27 |
| Secret mgmt | Env vars | Vault / K8s Secrets | P27 |
| Key rotation | Manual | Automated | P27 |
| TLS | Loopback only | TLS everywhere | P27 |
| Rate limit | None | Per-user, per-org | P23/P27 |
| Audit | events.jsonl | PostgreSQL audit_events | P22 |
| DR | File backup | DB + Object Storage backup | P26 |
| Pen testing | Adversarial suites | Professional pen test | P30 |

## What Does NOT Change

The security ARCHITECTURE (fail-closed, human-only approvals,
governance-before-evidence, provenance validation) is production-
ready. Only implementation details change.
