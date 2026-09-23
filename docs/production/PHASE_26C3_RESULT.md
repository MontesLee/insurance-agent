# Phase 26C-3 — Run Budget & Bounded Execution (Result)

Date: 2026-09-22 · Baseline 7ac15aa + frozen 26C-1/26C-2 (uncommitted)
· Audit: PHASE_26C3_AUDIT.md · Suite 15/15 (62/62 checks) ·
Regression numbers below.

## Status

```
PHASE_26C3_PASS_WITH_DOCUMENTED_DEBT
```

## What was built

`runtime/queue/budget.py` (NEW): `RunBudget` — run-scoped, absolute,
PG-authoritative budget boundary (`agent_run_budgets` +
`agent_run_budget_events` ledger). `RunControl(budget=...)`
(optional) enforces it at the EXISTING 26C-2 control points
(pre-start / pre-settle-success / pre-retry / pre-approval-resume).
`AgentTaskWorker` handles the `budget` verdict; the executor result
now carries REAL repair counts (`budget_usage`, derived from
orchestrator state — business skills untouched). No new run states:
exhaustion = run FAILED `budget_exceeded:<TYPE>` + task CANCELLED
(same-reason), the 26C-2 expiry pattern.

## Budget dimensions & semantics

Seven dimensions (max_llm_calls, max_input_tokens,
max_output_tokens, max_estimated_cost, max_task_attempts,
max_repair_attempts, max_replans; NULL = UNMETERED) with
used-counters, an llm-call reservation counter (single-statement
CAS — race-safe), usage_unknown/cost_unknown flags, soft 80%
warnings (ledger event only). See RUN_BUDGET.md for the full
contract.

## Key evidence (tests: E26C3-01..14, C1-C3, M26C3-01..10)

| Claim | Evidence |
|---|---|
| limits write-once; retry/resume/crash never reset | E26C3-01/09/11 |
| reservation race: remaining=1 → exactly 1 winner; 3 of 5 | E26C3-02 (barrier, real PG) |
| idempotent settle/release (event-key ledger) | E26C3-03/11-C2 |
| UNKNOWN never zero; fails closed under hard limits | E26C3-04/05 |
| cost = config pricing × real tokens; unknown → UNKNOWN | E26C3-05 |
| soft warning = audit only | E26C3-06 |
| task-attempt budget stops the third attempt at a control point | E26C3-07 |
| over-budget completion NEVER accepted (no fabricated artifact) | E26C3-08 |
| HITL: exhausted budget refuses approval; no auto-increase | E26C3-10 |
| C1 real kill: reservation survives in PG, still bounds; recovery completes within envelope | E26C3-11 |
| C3 exhausted/terminal: no resurrection | E26C3-11 + 26C-2 suite |
| replan dimension enforced; concurrent settles lossless | E26C3-12 |
| business invariance: generous budget ≡ no budget; exhausted → no fake success | E26C3-13 |
| mutations: gate removal / blind gate / flag-clearing / SQL drift all OBSERVED (detectors fire) | M26C3-01..10 |

## Audit-driven bug found in FROZEN 26A code — FIXED

**F-26C3-P1-01 (P1, fixed)**: `TaskQueueStore.claim`'s SQL had an
operator-precedence bug — `status='PENDING' OR (...expired...) AND
task_type=ANY(...)` parsed the type filter as applying ONLY to the
expired-lease branch, so a typed worker could claim an OLDER
PENDING task of a DIFFERENT type. Every prior suite used one type
at a time, so it never fired; the 26C-3 multi-type scenario exposed
it. Fix: parentheses in the subquery (store.py, one line) — this
RESTORES the 26A/26B documented semantics ("Worker task_types claim
filter (typed isolation)"), it does not change them. Regression
test E26C3-14 pins it; all frozen suites (26A 13/13, 26B 10/10,
26C-1 12/12, 26C-2 15/15) re-ran green after the fix.

## Regression

```
Runtime:     582 passed (567 + 15 new p26c3 tests)
26A 13/13 · 26B 10/10 · 26C-1 12/12 · 26C-2 15/15
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS (targeted roots)
```

## Findings

| ID | Severity | Finding |
|---|---|---|
| F-26C3-P1-01 | P1 | claim type-filter precedence bug (see above) — FIXED with regression coverage |
| F-26C3-INFO-01 | INFO | LLM-choke-point wiring is future work: the queue path runs deterministic skills (real zero LLM calls); the gateway already emits real usage/cost per call — joining it to run budgets requires run context in skills (business skills frozen) |
| F-26C3-INFO-02 | INFO | Reservation leak on crash stays counted until the run ends (strictest fail-closed choice per §15; no inflation, no bypass) |
| F-26C3-INFO-03 | INFO | No dynamic budget editing / HTTP API / dashboard (phase boundary); human control = start a new run |

P0 = 0 · P1 = 1 (FIXED) · P2 = 0 · P3 = 0 · INFO = 3

## Scope discipline

runtime/queue/{budget.py NEW, run_control.py, agent_runtime.py,
ops.py, __init__.py, store.py (one-line precedence fix)} + tests/
runtime/test_p26c3_budget.py (NEW) + PHASE_26C3_AUDIT.md,
RUN_BUDGET.md, PHASE_26C3_RESULT.md (NEW). Skills/knowledge/
gateway/orchestrator/model untouched. No Redis/Kafka/K8s/Prometheus/
OTel/billing. Exactly-once NOT claimed.

Phase 26C-4 (Recovery / Reconciliation): NOT STARTED.
