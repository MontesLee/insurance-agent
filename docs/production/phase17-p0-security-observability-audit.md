# Phase 17 P0 — Security & Observability Audit (read-only, 2026-09-20)

Probed this round against code; historical coverage from the Phase-13
P0/P0.1 suites is cited where it already proves a control.

## Inventory of existing controls

| Surface | Code | Existing tests |
|---|---|---|
| Authentication | runtime/auth.py (Identity key:role:user; authenticate fail-closed; strict-mode startup refuses no-key boot — server.py:633) | tests/runtime/test_p0_r06.py |
| RBAC | ROLES OWNER/REVIEWER/OPERATOR + rank/has_role + server._require_role | test_p0_r06 |
| CORS | auth.cors_origins() allowlist; `*` only explicit dev mode | test_p0_r06 |
| Approval security | approval/models.can_resolve_actor (human/human:* only), terminal-state rules, ApprovalStore | test_p0_r02, test_approval |
| PII redaction | dataprotection.redact deny-list (name/phone/id/income/health…) applied on every event/log append | test_p0_r04 |
| Encryption | Fernet IA1: at-rest; mode.encryption_required() strict modes | test_p0_r04, test_p01_hardening |
| Provider policy | agent/data_policy.py fail-closed gate (PROVIDER_POLICY_UNVERIFIED) | test_p0_r05 |
| Retention/erasure | state/retention.py (terminal-only, backup-first, dry-run default, erasure.log) + backup/restore + delete_project | test_p1_backup/restore, test_p14-era suites |
| Runtime-state integrity | R-01 atomic+locked writes; checkpoint fingerprint validate | test_p0_r01, test_step3_mutation |
| Events/trace | events.jsonl (redacted), observability.py load_trace/summarize/render | test_events, test_knowledge_evidence T10-T16 |
| Project isolation | per-project dirs under one root; R-01 index locks per root; delete/retention validate project ids | partial (cross-process suites); Phase 17 adds explicit matrix |

## Gaps Phase 17 must ADD (no duplication of the above)

1. A single security evaluator (evals/security/) with ≥70 cases:
   auth (anonymous/roles/invalid), authorization matrix (per-action
   allowed/denied/reason), project isolation, approval forgery,
   redaction, provider policy, error fail-closed, audit tamper —
   plus M-AUTH-01..10 mutation detection.
2. An observability evaluator (evals/observability/): trace
   completeness from run artifacts, latency percentiles over 10
   standard cases (explicitly NOT statistically representative),
   token/cost accounting honesty (NOT_MEASURABLE unless the adapter
   reports real usage), M-OBS-01..08 detection.
3. Threat-model mapping (docs/production/phase17-threat-model.md —
   written).

## Honest limitations recorded up front

- Audit logs (events.jsonl) are append-only by CONVENTION; artifact
  tampering is hash-detected, raw-event-line tampering is not
  intrinsically detectable (F-18, P2).
- No OpenTelemetry (out of scope by the brief); the existing event
  system is the observability substrate.
- Latency numbers on this single dev box are NOT representative of
  production (will be labeled).
