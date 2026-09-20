# Phase 17 — Security, Governance & Observability Report

Date: 2026-09-20 · Inputs: phase17-p0-security-observability-audit.md,
phase17-threat-model.md · Production code changes: **1 minimal security
fix** (§22/redaction gap — documented below).

## 01 Executive Summary

```text
Phase 17 = PASS
```

Security boundaries are explicitly modeled (T01–T15) and validated by
negative tests and mutations: 98/98 security cases + hard gates all
zero + M-AUTH 10/10; observability: trace completeness 8/8 + M-OBS
8/8, latency percentiles over 10 real runs (honestly labeled NOT
statistically representative), token accounting honest
(llm_calls=0 measured; usage NOT_MEASURABLE on the deterministic
path). One genuine redaction gap (bank_card/policy_number) was found
by the evaluator and fixed minimally in production with regression.

## 02 Audit Scope

P0 audit mapped every control surface (auth/RBAC, approval actor
binding, redaction deny-list, Fernet-at-rest policy, provider gate,
retention/erasure, R-01 state integrity, events/trace, project
namespacing) to its existing tests and identified what Phase 17 must
ADD (the two evaluators + threat model).

## 03 Threat Model

15 threats (T01–T15) each mapped to control + test + expected
fail-closed behavior — see phase17-threat-model.md. Two recorded
gaps: F-18 (events.jsonl append-only by convention, no cryptographic
chain), F-20 (value-shaped credentials inside free-text fields
survive the field-based deny-list).

## 04 Authentication

Anonymous / empty / invalid-token / malformed-header / wrong-scheme →
deterministic None (server maps to 401); strict-mode boot refuses
without identities (cited from server startup guard); malformed
identity entries are skipped, never trusted. 9/9.

## 05 Authorization

33/33 matrix cells across 8 actions × 3 roles + anonymous, per the
CURRENT rank model (OPERATOR<REVIEWER<OWNER); OPERATOR never reaches
approve (REVIEWER-gated). M-AUTH-04/05/08/09 prove the boundaries.

## 06 Project Isolation

5/5: distinct projects load distinctly; traversal/charset/absolute
forged ids all rejected by the loader (None) — no project_id forgery
bypass.

## 07 Approval Security

13/13: human-only resolution (agent/planner/empty actors →
ACTOR_NOT_AUTHORIZED refusal, state unchanged); idempotent
double-resolve never re-executes; FILE-LEVEL forged APPROVED state is
respected as terminal (no re-execution, no actor stamp) and remains
visible as audit evidence; binding fields (project/task/type/
resolved_by/resolved_at, graph_revision key) present.

## 08 Audit Integrity

Artifact/content tampering is hash-detected (checkpoint +
provenance anchors — Phases 13/14 evidence). Raw event-line tampering
is NOT intrinsically detected (no chain) — recorded as F-18 (P2) with
the evaluator asserting the honest behavior (file-level mutation
visible; no safety claim made).

## 09 PII / Redaction

12/12 on the field-based deny-list contract: sensitive-named fields
redacted IN PLACE (event preserved, value dropped — never
whole-event deletion); operational fields survive. **Production fix
(P-17-1)**: `bank_card/card_number/bank_account/account_number/
policy_number/policy_no` were MISSING from SENSITIVE_FIELDS — found
by D08, fixed minimally in runtime/state/dataprotection.py, with
fix-regression cases in the Phase-17 suite and test_p0_r04 green in
the full battery. F-20 (P3) records the value-shape limitation.

## 10 Encryption

Strict modes require a key at startup (cited: test_p01_hardening);
IA1: ciphertext magic verified with a real Fernet key; strict-mode
missing-key path asserted (absence recorded; the hard fail-closed
proof is the startup guard suite). 3/3.

## 11 Retention / Erasure

E01 active-never-swept (policy max_age=0 + execute → swept=[] ✓) ·
E05 erasure audit log exists; E02/E03/E04 stand on the Phase-13
Stage-1 suites (terminal-only, backup-first, delete completeness)
re-verified green in the full battery.

## 12 Provider Policy

6/6 on the REAL gate semantics: REAL data + unverified → BLOCKED
(fail-closed); forged opt-in values ("yes"/"true"/"2") never count —
only the literal documented operator "1"; synthetic default not
gated (documented). No fallback path exists.

## 13 CORS

Boundary verified against the real contract: strict mode never
wildcard; a wildcard SET outside dev is DROPPED (fail-closed to
loopback); wildcard reachable only via explicit INSURANCE_AGENT_DEV=1;
explicit allowlists honored exactly. (Server-layer surface; business
runtime untouched.)

## 14 Error Handling

3/3: corrupt state → deterministic rejection (no fabricated
project/result); unknown knowledge provider → ProviderConfigError
(no fallback — ties to 14.1 C06); error surfaces in stage
failure_reason (trace-visible).

## 15 Observability

Every full run yields the §18 record from durable surfaces: run id
(case), stage statuses + attempts, skills, artifact chain, evidence
refs/count, final status, error list. 8/8 completeness.

## 16 Trace Completeness

One business case traces end-to-end: stages → skills → artifacts →
evidence refs → decision status; M-OBS-01..08 all detected (8/8) —
including forged project-id and deleted error visibility.

## 17 Latency (10 standard full business runs, dev box)

min 0.171s · median 0.398s · p95 0.539s · max 0.539s —
**NOT STATISTICALLY REPRESENTATIVE** (single dev box, convenience
cases; no production performance claim).

## 18 Cost / Token Accounting

llm_calls = 0 (measured: the deterministic pipeline makes none);
input/output tokens **NOT_MEASURABLE** on this path — no estimates
fabricated. (Agent-mode LLM usage accounting exists separately on the
agent path; out of this evaluator's scope by design.)

## 19 Mutation Tests

M-AUTH-01..10: 10/10 · M-OBS-01..08: 8/8 · fail-closed injection
wiring: one forged-allow flips SG-HG02 (proven in-suite).

## 20 Hard Gates

SG-HG01..12 all ZERO across 98 security + observability cases.

## 21 Full Regression

runtime 442 (438→442, +4) · portfolio 12 · 14.1–14.7 suites
52/33/74/52/44/25/21 · 15: business eval 15/15 + suite 23/23 · 16:
30/30 + 26/26 · full regression 51/0/1 (=) · benchmark 42/42 ·
compileall PASS · security eval 98/98 exit 0 · observability eval
PASS exit 0.

## 22 Findings

- **P-17-1 (FIXED)**: bank_card/policy_number absent from the
  redaction deny-list (T07 gap) — root cause: the Phase-13 field list
  predated the Phase-17 fixture set; minimal fix (6 field names +
  pattern), regression tests added, full battery green.
- F-18 (P2): events.jsonl lacks tamper-evidence chaining (append-only
  by convention; artifact tampering IS hash-detected).
- F-20 (P3): value-shaped credentials in free-text fields survive the
  field-based deny-list (value-pattern scanning out of minimal scope).
- F-19 (P3): malformed identity entries skipped silently — acceptable
  (never trusted), noted for operator visibility.
- No P0/P1 outstanding.

## 23 Known Limitations

F-18/F-19/F-20 above; latency not representative; token usage
NOT_MEASURABLE on the deterministic path; audit-log chaining deferred.

## 24 Final Verdict

```text
Phase 17 = PASS
```

Agent execution is controlled, auditable, observable, and fail-closed
— with every claim backed by a negative test or a mutation.
