# Phase 25 Gate Review — Independent Human Gate (Phase 25 → Phase 26)

Date: 2026-09-21 · Reviewer stance: read-only, evidence-driven,
fail-closed. Probes: tmp/gate25/ (NOT committed). No product, test,
doc or config files were modified; nothing committed.

## 1. Baseline verification

| Item | Verified | Evidence |
|---|---|---|
| Phase 24 commit 131cdb1 | ancestor of HEAD | git merge-base --is-ancestor → yes |
| Phase 24 review de8282a | ancestor | yes |
| RV-P2-01 hotfix 05a84a5 | ancestor | yes |
| HEAD | 254c359 (Phase 25) | git rev-parse; working tree clean |
| Runtime 513 | **513 passed** (re-run) | 4:28 serial run |
| Portfolio 12 | **12 passed + 2 ERRORS** (re-run) | see F-GATE-03 — the Phase 25 claim "Portfolio 12" is INCOMPLETE |
| Benchmark 42/42 | ALL GREEN (re-run) | — |
| compileall | PASS | — |
| p25 suites | 122/122, 33/33 re-executed this review; gate probes 53/53 fresh | tmp/gate25/results.json |

## 2. Phase 25 claim verification

All E25 / failure-injection / probe numbers reproduce. ONE claim does
not: PHASE_25_RESULT.md states "Portfolio 12" without the 2 teardown
ERRORS that the same battery already showed before the Phase 25
commit (the errors were present in the pre-commit battery output).
Evidence-integrity finding recorded (folded into F-GATE-03).

## 3. G1–G12

| Gate | Result | Evidence | Finding |
|---|---|---|---|
| G1 Trace | PASS with finding | E2E run: POST /api/runs logged with req/corr/trc ids; artifacts retrievable; reverse via run registry + per-run trace.jsonl (nested `agentcase-*/trace.jsonl`, task_ids present); LLM/knowledge failures localize to request+task+skill with class+retryable+operator action; zero orphan http.request records | F-GATE-01: `run.completed` (worker thread) carries NO ids — contextvars do not propagate into RunManager worker threads |
| G2 Correlation | PASS | sequential requests distinct ids; nested span inherits + restores; 4 concurrent threads fully isolated (no bleed) | — |
| G3 Structured log | PASS | 105+ synthetic records JSON-parseable; required fields present; error records stay structured (message is a field) | INFO-02: worker crash path prints plain text to STDERR — outside the JSONL sink, no pollution |
| G4 Error taxonomy | PASS | all 17 classes carry the 6 fields; classification independent of message; retryable/safe semantics consistent with gateway behavior (network/timeout retry-safe; governance never) | — |
| G5 Metrics | PASS | counters exact; no negatives (no decrement API); EXHAUSTED re-checked — no double count (2 calls → 1 fail + 1 ok + 1 timeout); UNKNOWN never coerced; unknown names flagged | — |
| G6 Latency | PASS | fresh N=30 rerun: health 2.8ms · readiness 2.7ms · diagnostics 4.3ms · simple 3.4ms · knowledge 0.6ms · LLM 0.04ms · full agent 221ms (median) — labeled engineering baseline, NOT a SLA | — |
| G7 Liveness | PASS | `status:"ok"` Phase-1 contract + `liveness:"LIVE"`; strict mode with dead PG: liveness stays LIVE (dependency never kills process). The mid-phase contract break was fixed against the real contract tests (test_server 10/10) — not bypassed | — |
| G8 Readiness | PASS | A: demo READY · B: strict+dead-PG → 503 NOT_READY (bounded) · C: strict+unreachable-WeKnora → NOT_READY · D: LLM_PROVIDER without key → NOT_READY item · E: all outages leave liveness LIVE. Strict startup itself is fail-closed (AUTHENTICATION_REQUIRED + ENCRYPTION_REQUIRED hit during probing — correct) | — |
| G9 Diagnostics | PASS | all required fields; git commit == actual HEAD (254c359, and fresh-process uptime < 60s proves dynamic); no env dump / credentials | — |
| G10 Security | PASS with finding | injected sk-/ghp_/Bearer-JWT/private-key ALL redacted; structured PII keys dropped; diagnostics/metrics clean; unauthenticated + bad token → 401; OPERATOR → 200; cross-project: aggregate-only, context isolated | F-GATE-02: phone/email/bank-card VALUE shapes pass through free-text fields (unreachable via current call sites — no free text is logged today); F-GATE-04: REVIEWER rank passes OPERATOR-minimum endpoints (read-only aggregates — acceptable, documented) |
| G11 Failure injection | PASS | §11 matrix re-executed 33/33: every failure answers what/where/why/retryable/operator-action | — |
| G12 Runbook | PASS | ≥10 cases, each with symptoms/inspect/safe/unsafe/escalation; every endpoint+metric+log name in the runbook exists in the implementation; zero documentation drift (no Prometheus/OTel/K8s/Redis claimed) | — |

## 4. §17/§18 observation-only verification

- Deep invariance: governance outcomes deep-equal with instrumentation
  (E25-15 re-executed); random-query stability (probe C1); the demo
  business result (FINAL COMPLETED) unchanged — BUT the demo's
  PRESENTATION channel changed: F-GATE-03.
- Source/AST walk of the four instrumented files: no
  `if observability_enabled` business branching; except-pass wraps
  ONLY observation calls; knowledge failures re-raised after logging.

## 5. R26-01..R26-10 (architecture readiness)

| Gate | Result | Evidence |
|---|---|---|
| R26-01 PostgreSQL authoritative | PASS | strict resolve_backend → postgres (probed); p22 suites green in regression |
| R26-02 Transaction semantics | PASS | p22_pg/p22b cutover suites present + green (atomic save, cascade, concurrency tests) |
| R26-03 Trace → workers | PASS w/ F-GATE-01 | TraceContext is a passable value object (worker adoption is mechanical); current wiring absent — that IS Phase 26 work |
| R26-04 Task identity | PASS | TASK ids in trace records + TASK_CREATED mapping (events.py) |
| R26-05 Terminal state observable | PASS | _TERMINAL map + run.completed + run registry |
| R26-06 Retry observable | PASS | attempt/max_attempts/error_type per try |
| R26-07 Failure → task identity | PASS w/ F-GATE-01 | spans carry task/skill when wired; worker-thread contexts are the gap |
| R26-08 Metrics semantics | PASS | registry behind one swappable seam (set_default_metrics); in-process semantics do not misread business state; distributed aggregation is a Phase 26 implementation of the same facade |
| R26-09 Worker extensibility without touching skills | PASS | zero .trae/skills files import runtime.obs (globbed all) |
| R26-10 Debt assessment | PASS w/ prerequisite | see §6 |

## 6. P3 debt re-judged (not copied)

- P25-P3-01 (no exporter): does NOT block Phase 26 (facade seam
  proven). Defer.
- **P25-P3-02 (retry idempotency unproven): Phase-26 PREREQUISITE
  work item** — the queue/lease/worker design must solve exactly-once
  semantics; deferring INTO Phase 26 is the plan, not a blocker to
  starting it.
- P25-P3-03 (CLI no request context): does not block (workers will
  carry contexts by construction).
- P25-INFO-01 (RETRY+EXHAUSTED double line): metrics already
  de-duplicated; cosmetic.

## 7. Mutation testing (§24)

Simulated defects all detectable: missing trace_id (record lacks the
field), correlation switch (explicit-context probe), cross-project
context (switch is explicit and asserted), retryable flip (semantic
assertions disagree), fake-READY (contradicted by the dead-PG probe),
secret injection (redaction verified with fresh high-entropy keys),
unknown-metric fabrication (flagged counter).

## 8. Clean environment (§23)

Fresh process (`env -i`): health LIVE, readiness READY, metrics
zeroed then counting, diagnostics commit == HEAD with fresh uptime —
no stale contextvar/metrics/readiness/diagnostics state.

## 9. Findings

| ID | Severity | Finding |
|---|---|---|
| F-GATE-03 | **P1** | Portfolio demo-determinism regression: `default_logger` mirrors structured JSONL to STDOUT in DEMO mode, and stdout IS the demo's product output — timestamps/durations now appear in demo output, breaking `test_demo_insurance` "semantically identical across 3 runs" (2 teardown ERRORs). Present since the Phase 25 change; business artifacts/state unchanged (FINAL COMPLETED, deterministic), but a committed acceptance suite is RED and the Phase 25 RESULT's "Portfolio 12" omitted the errors. Fix (NOT applied here — review is read-only): mirror to stderr or behind an explicit env flag, then re-run portfolio. |
| F-GATE-01 | P2 | Worker threads receive no propagated request/correlation ids (`run.completed` and in-run knowledge/llm logs are context-less). Mechanism is ready (passable TraceContext); wiring is Phase 26 work by definition. Phase-26 prerequisite work item. |
| F-GATE-02 | P3 | PII VALUE shapes (phone/email/bank card) are not in the free-text redaction patterns (credential shapes + structured PII keys are). Currently unreachable (no call site logs free text); close when any free-text-logging call site appears. |
| F-GATE-04 | P3 | REVIEWER rank passes OPERATOR-minimum endpoints (/api/metrics, /api/diagnostics) — read-only aggregates; acceptable, documented here. |
| F-GATE-05 | INFO | Worker crash path prints plain text to stderr (separate stream; JSONL unpolluted). |
| F-GATE-06 | INFO | PHASE_25_RESULT "Portfolio 12" claim was incomplete (12 passed + 2 errors) — folded into F-GATE-03's evidence trail. |

P0 = 0 · **P1 = 1** · P2 = 1 · P3 = 2 · INFO = 2

## 10. Final decision

```
BLOCKED_FOR_PHASE_26
```

Rationale: one P1 — a committed portfolio acceptance suite is red
because Phase 25's stdout mirror leaks observability output into the
demo's business output channel. The fix is small and squarely inside
observability scope, but this review is read-only: it must be applied
(and the portfolio suite re-verified green) before the gate re-opens.
Everything else — trace, correlation, logging, taxonomy, metrics,
latency, health/readiness, diagnostics, security, failure injection,
runbook, and all ten R26 architecture-readiness gates — PASSES on
fresh evidence, and the remaining P2/P3 findings are documented,
non-blocking, and (where relevant) explicit Phase 26 work items.

Unblock path (for the implementer, not this review): fix the stdout
mirror destination → portfolio 12/12 with 0 errors → re-run this
gate's G-block (fast) → READY_FOR_PHASE_26_WITH_DOCUMENTED_DEBT
expected (F-GATE-01 becomes the documented Phase 26 prerequisite).

STOP — nothing fixed, nothing committed, Phase 26 not started.

---

# Appendix — Phase 25.1 narrow recheck (F-GATE-03)

Date: 2026-09-21 · A **narrow** recheck ordered by the Phase 25.1 hotfix; the full
independent review above is **not** re-run. Primary evidence is the **pre-existing,
independent** Portfolio acceptance suite (`tests/portfolio/`, Phase 12) plus a
separate reproduction script — not the implementer's new test file.

Recheck scope: F-GATE-03 · stdout/stderr separation · Portfolio · business output
determinism · observability availability · security/redaction · Phase 26 readiness.

| Probe | Result | Evidence |
|---|---|---|
| Defect reproduced BEFORE fix | CONFIRMED | demo stdout carried 2 obs JSONL records (`knowledge.search`); portfolio **12 passed / 2 errors** |
| stdout is product-only AFTER fix | PASS | demo stdout obs records = **0**; no `event`/`duration_ms`/`timestamp`/ids |
| stderr carries observability AFTER fix | PASS | demo stderr obs records = **2** (`knowledge.search`) |
| Portfolio (independent suite) | PASS | `pytest tests/portfolio -q` → **12 passed, 0 errors** (was 12/2) |
| Business output determinism | PASS | product stdout identical across 3 runs; identical obs ON vs OFF; E25-15 invariance green |
| Observability availability | PASS | records retained on stderr with request/task/skill/event/status identity |
| Security / redaction | PASS | `sk-`/`ghp_`/Bearer-JWT/private-key + structured PII keys redacted on stderr; no new leak path |
| Regression | PASS | 51 PASS / 0 FAIL / 1 INFRA_ERROR (env: GBK test-encoding bug — 9/9 under UTF-8) |
| Scope | PASS | `runtime/obs/log.py` + one new test + the two doc corrections only |
| Phase 26 readiness | UNBLOCKED | F-GATE-03 closed; F-GATE-01 remains the documented Phase 26 prerequisite |

## Updated decision

```
F-GATE-03_CLOSED — READY_FOR_PHASE_26_WITH_DOCUMENTED_DEBT
```

Rationale: the sole P1 (stdout contamination) is fixed and independently
reproduced as closed; the independent Portfolio acceptance suite is green
(12/0); business results are unchanged; observability remains available (now on
stderr); redaction is intact; scope is clean. F-GATE-02/04/05/06 remain
unchanged documented debt; F-GATE-01 is the Phase 26 prerequisite work item.

STOP — Phase 25.1 fix committed (see the `fix: isolate observability from demo product output` commit); Phase 26 not started.
