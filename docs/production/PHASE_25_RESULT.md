# Phase 25 Result — Production Observability & Reliability Foundation

Date: 2026-09-21 · Baseline c7312bb verified before start (11-point
check). Regression 513/12/42 · p25 suites 122/33/8 · audit 16/16.

> **Correction (Phase 25.1, 2026-09-21):** the portfolio leg of "513/**12**/42"
> was recorded as a clean **12**, but the actual pre-hotfix result was
> **12 passed + 2 teardown ERRORS** — Phase 25's observability mirror wrote to
> stdout and contaminated demo output, breaking the two repeatability suites.
> This is the historical record and is preserved, not rewritten. Closed by
> [PHASE_25_1_RESULT.md](PHASE_25_1_RESULT.md) (F-GATE-03): the portfolio is now
> **12 passed / 0 errors**.

## Status

```
PRODUCTION_OBSERVABILITY_READY_WITH_DOCUMENTED_DEBT
```

## Deliverables

| Piece | Where |
|---|---|
| Trace context (25A) | runtime/obs/context.py — request/correlation/trace/project/case/task/skill/tool, contextvar-scoped, prefixed ids |
| Structured logging (25B) | runtime/obs/log.py — JSONL, redaction by construction (PII-key denylist + credential-shape rewrite) |
| Error taxonomy (25C) | runtime/obs/errors.py — 17 classes, deterministic table, retryable/safe_to_retry/operator_action/user_visible |
| Metrics (25D/25E) | runtime/obs/metrics.py — declared counters, percentile latencies, UNKNOWN-honest tokens; NO PostgreSQL schema added |
| Health/Readiness (25F) | runtime/obs/health.py + /api/health (backward-compatible `status:"ok"` + `liveness:"LIVE"`) + /api/ready (READY/NOT_READY/DEGRADED, 503 on NOT_READY) |
| Diagnostics (25G) | runtime/obs/diagnostics.py + /api/diagnostics (OPERATOR RBAC; scrubbed; file-read git commit — no subprocess) |
| Instrumentation | server middleware (X-Request-Id, request metrics/log), KnowledgeService.search (knowledge metrics), LLMGateway._log→_observe (single choke point), RunManager._observe_run (task/skill metrics) |
| Failure injection (25H) | tests/runtime/test_p25_failure_injection.py — 33/33 |
| Evaluation (25I) | tests/runtime/test_p25_observability.py — E25-01..15 + §18 mutations, 122/122 |
| Perf baseline (§21) | tmp/p25_perf_baseline.json (N=30 each) |
| Docs (25J) | OBSERVABILITY.md (rewritten as-implemented, supersedes the Phase 21 design note with lineage), OPERATIONS_RUNBOOK.md (10 cases) |

## §27 — the twenty answers

Architecture: (1) one observation-only package + four instrumentation
choke points (server middleware, knowledge search, LLM gateway log,
run completion); (2) the trace flows request→span(task/skill/tool)
via contextvars, logs carry the ids, the case trace.jsonl stays the
per-run record; (3) logs join on ids, metrics are aggregate-only by
design, diagnostics snapshots both; (4) liveness = process answers
(downstream never kills it); readiness = mode-aware dependency checks
(strict: PostgreSQL + real WeKnora REQUIRED).

Reliability: (5) retryable = NETWORK/TIMEOUT/RATE_LIMIT/
PROVIDER/LLM/KNOWLEDGE/PERSISTENCE/CONCURRENCY; (6) never retry
GOVERNANCE/EVIDENCE/PROVENANCE/CONFIG/AUTH/VALIDATION/INTERNAL —
`classify()` answers with retryable + safe_to_retry separately; (7) a
retry loop is visible as repeated `llm.call` RETRY records with
attempt/max_attempts/error_type plus llm_failure counters by error;
(8) dependency failures surface as readiness check states + PST-/KNW-/
LLM- codes in the error log.

Security: (9) PII: key-name denylist drops prompt/client_profile/
content payloads (fact retained, payload dropped); (10) secrets:
credential-shape value rewrite in every string + secret-named string
fields scrubbed in diagnostics; (11) /api/diagnostics and /api/metrics
require the OPERATOR role when identities are configured (401
anonymous/bad token, verified); local-dev no-keys mode passes.

Operations: (12–16) the runbook's ten cases, each with symptoms →
inspect → safe/unsafe → escalation, anchored to the actual metric and
log names.

Production: (17) production-ready now: trace ids, structured logs,
taxonomy, metrics, health/readiness separation, RBAC'd diagnostics,
runbook; (18) engineering baseline: all latency numbers (N=30, single
host, mock LLM/knowledge); (19) NOT_MEASURABLE: production-scale SLA,
real-LLM token cost at load, concurrent throughput; (20) the real
next-stage blockers are infrastructural, not observability: Redis/
queue/workers for multi-process, backup scheduling + restore
verification (RV-P3-02), exporter backend if metrics must leave the
host.

## Hard gates

HG25-01..25 verified: no P0/P1; trace complete; correlation
consistent; logs parseable; secret/PII redaction proven (incl. random
keys); taxonomy deterministic; no fabricated metrics; UNKNOWN stays
UNKNOWN; health/readiness semantics correct incl. the
fake-READY mutation; diagnostics authenticated/authorized; cross-
project isolation (aggregate-only + contextvar isolation); failure
injection observable; retry behavior observable; no mock fallback in
production (unchanged, re-verified); no business-skill regression
(513/12/42 — see the Phase 25.1 Correction above); governance/evidence/provenance UNCHANGED (diffs are pure
instrumentation — verified line-by-line; E25-15 deep-equality on
governance outcomes); LLM Gateway contract unchanged (only _log
extension); PostgreSQL authoritative behavior unchanged (zero schema
changes); regression green; no secrets committed.

One backward-compatibility defect was introduced and FIXED during the
phase: /api/health briefly returned `status:"LIVE"`, breaking the
Phase-1 API contract — restored to `status:"ok"` with `liveness:"LIVE"`
alongside (test_server green again).

## Findings

| ID | Severity | Finding |
|---|---|---|
| P25-P3-01 | P3 | In-process metrics/log sinks only — no exporter (deliberate: OTel/Prometheus deferred until a deployment needs them) |
| P25-P3-02 | P3 | Retry duplicate-execution safety beyond checkpointing is unproven (observed, documented — not fixable inside Phase 25 scope) |
| P25-P3-03 | P3 | Request ids assigned for HTTP traffic only; offline CLI runs have empty request context |
| P25-INFO-01 | INFO | gateway retry logs emit RETRY for the final failed attempt before EXHAUSTED (double log line, single provider call — metrics de-duplicated, greppers see two lines) |

P0 = 0 · P1 = 0 · P2 = 0 · P3 = 3 · INFO = 1

## Independent audit

tmp/review25/audit_probes.py — 16/16 with fresh random data
(correlation single-value, span scoping, random-credential redaction,
message-independent classification, percentile correctness, UNKNOWN
honesty, health back-compat, readiness vocabulary, diagnostics
secret-freeness, aggregate-only isolation, behavior stability under
random queries, no forbidden frameworks). Report:
PHASE_25_INDEPENDENT_REVIEW.md.

STOP — no Phase 26, no Redis/Queue/Worker/K8s/HA/multi-tenant.
