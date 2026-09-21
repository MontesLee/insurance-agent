# Phase 25 Independent Observability & Reliability Audit

Date: 2026-09-21 · Mode: read/inspect/test/mutate only — no fixes
applied. Probes: tmp/review25/audit_probes.py (16/16, fresh random
data, independent of the committed suites).

## What was independently verified

| Area | Method | Result |
|---|---|---|
| Trace | fresh random request/spans; correlation single-valued per request; skill/task fields scoped to their span only; empty context outside requests (no phantom ids) | PASS |
| Logs | JSONL parseability, field contract, error projection completeness (incl. user_visible) — from the committed E25-03 re-run + fresh span probe | PASS |
| Metrics | 50 random observations → percentile correctness (min/max exact); unknown counter NAMES flagged, never invented; unmeasured tokens stay UNKNOWN | PASS |
| Errors | classification independent of message content (random messages, same class); deterministic across instances | PASS |
| Secrets | random high-entropy credential (sk- + 64 hex) injected into a free-text field — fully redacted; diagnostics body carries no env dump / no key-shaped values | PASS |
| Health | backward-compat `status:"ok"` AND `liveness:"LIVE"` (the compat break introduced mid-phase was fixed and re-verified against the Phase-1 contract tests) | PASS |
| Readiness | vocabulary READY/NOT_READY/DEGRADED; strict+dead-PG → NOT_READY bounded; liveness unaffected by dependency outage | PASS |
| Diagnostics security | OPERATOR RBAC (401 anonymous/invalid token with identities configured — verified in E25-12 re-run); aggregate-only (no project/case payloads); scrub keeps boolean facts, redacts secret-named strings | PASS |
| Failure injection | §11 matrix re-executed (33/33): PG dead-port/transaction, WeKnora refused/401/403/malformed, LLM timeout/429/401/403/500/budget, app-level invalid/corrupt/unexpected — every case classified + counted, business fail-closed unchanged | PASS |
| Retry visibility | attempt/max_attempts/reason in every retry record; EXHAUSTED not double-counted in metrics; duplicate-execution safety honestly documented as LIMITATION | PASS |
| Business invariance | §29: same input + observability ON → same business result (deep-equal governance outcomes E25-15; two full pipeline runs same status; random-query stability probe C1) | PASS |
| Scope | git diff walked: 4 modified files contain ONLY instrumentation (verified line-by-line: QueryContext→provider→governance calls untouched; gateway changes confined to _log/_observe); no Redis/Queue/K8s/OTel/LangChain/MCP; no schema changes; Phase-24 governance/registry code untouched | PASS |
| Regression | 513/12/42 + compileall; p25 suites 122 + 33 + 8; earlier INFRA-flake (parallel tmp interference) not reproduced serially | PASS |

## Gate verdicts

G25 equivalents of HG25-01..25: all PASS. Notable audit discoveries
(recorded during the phase, fixed within observability scope):
the /api/health contract break (fixed, backward-compatible again),
the metrics self-deadlock (RLock), the gateway EXHAUSTED
double-counting (de-duplicated), the label-keyword collision
(swallowed exceptions → partial metrics).

## Residual findings (accepted as documented debt)

P25-P3-01 exporter-less sinks · P25-P3-02 retry idempotency unproven ·
P25-P3-03 CLI runs lack request context · P25-INFO-01 double retry log
line. No P0/P1/P2.

## Final decision

```
PRODUCTION_OBSERVABILITY_READY_WITH_DOCUMENTED_DEBT — CONFIRMED
```

STOP — awaiting human review; Phase 26 not started.
