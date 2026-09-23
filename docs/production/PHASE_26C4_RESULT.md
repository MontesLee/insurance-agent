# Phase 26C-4 — Production Recovery & Reconciliation (Result)

Date: 2026-09-22 · Baseline 7ac15aa + frozen 26C-1/2/3 (uncommitted)
· Audit: PHASE_26C4_AUDIT.md · Suite 14/14 (53/53 checks) ·
Regression numbers below.

## Status

```
PHASE_26C4_PASS_WITH_DOCUMENTED_DEBT
```

## What was built

`runtime/queue/recovery.py` (NEW, ~300 lines):
`RecoveryController.reconcile_once()` — pull-based, no daemon, no
scheduler, no execution. Steps: reuse 26A `recover_expired` →
reuse 26C-2 `expire_overdue` → the run/task consistency scan with
the deterministic HEALTHY / RECOVERABLE / STALE / INCONSISTENT /
UNKNOWN classification (see RECOVERY_RECONCILIATION.md for the full
matrix). Every action is a single CAS; every pass is audited to
`recovery_events` (+ obs events, stderr only). Plus `__init__.py`
exports. ZERO changes to any existing runtime file — the boundary
wraps the frozen mechanisms.

## Answers to the phase questions (Q1-Q12, from code + tests)

Q1 crash consistency: lease expiry → recover/reclaim → attempt+1;
run survives (E26C4-02/13, 13 = REAL OS kill end-to-end).
Q2 expired lease + live worker: every write is lease CAS — stale
settle/heartbeat rejected (26A, re-asserted in M26C4-01 mapping).
Q3 dead worker + RUNNING row: recover_expired → PENDING (RECOVERABLE).
Q4 task terminal + run non-terminal: run follows the task
(execution authority), CAS-guarded, reason `task_terminal`
(E26C4-03 — no fabrication).
Q5 run terminal + task non-terminal: task → CANCELLED with the
run's reason; late workers rejected by CAS (E26C4-04/06).
Q6 checkpoints: PHYSICAL attempt isolation (26B) — payload inputs,
never authority; the reconciler is DB-only (boundary decision).
Q7 artifact-before-settle crash: at-least-once re-execution; the
queue row is the business result (existing semantics).
Q8 terminal-without-result / result-without-terminal: never faked —
INCONSISTENT pairs are flagged without mutation (E26C4-05/M26C4-10).
Q9 approval vs terminal run: waiting task cancelled by reconcile;
approval still refused (E26C4-07).
Q10 budget reservation after crash: PRESERVED + reported (26C-3
strict semantics; E26C4-08 — never reset without evidence).
Q11 old lease/worker/attempt returns: rejected at task CAS +
run CAS + checkpoint lineage (E26C4-04 asserts the late settle).
Q12 reconciliation crash: single-action transactions + idempotent
retry; failing steps fail closed and are audited (E26C4-09/10).

## Tests

`tests/runtime/test_p26c4_recovery.py` — E26C4-01..13 (healthy
classification, crash requeue recovery, Case F sync, Case E task
cancellation, Case D fail-closed, TIMED_OUT loop, waiting-vs-
terminal, budget preservation, triple-idempotency, DB-failure fail
closed + retry convergence, audit trail, business invariance with
mid-flight reconcile, REAL subprocess kill end-to-end) +
M26C4-01..10 (resurrection corrected, negative-reservation drift,
expired-approval gate mutation observed, blinded-scan drift
observed then repaired, UNKNOWN-pair never auto-completed, plus
mapped 26A/26B detectors).

## Failure matrix (§23) — all PROVEN

worker crash → recover after expiry (E26C4-02/13) · stale worker
completion → reject (E26C4-04) · stale heartbeat → reject (26A
re-assert) · expired lease → requeue (E26C4-02/06) · DB
unavailable → fail closed (E26C4-10) · commit unknown → idempotent
retry (E26C4-09/10) · terminal run/task + stale worker → reject
(E26C4-04/06) · missing checkpoint → RECOVERY_REQUIRED path
(26B C-matrix) · stale checkpoint → reject (26B) · duplicate
reconciliation/recovery → idempotent (E26C4-09) · artifact missing
→ no fake (E26C4-05/M26C4-10) · approval after timeout/cancel →
reject (E26C4-07 + 26C-2) · budget reservation after crash →
preserve/reconcile (E26C4-08) · inconsistent run/task → fail closed
(E26C4-05) · reconciliation crash → safe retry (E26C4-10).

## Business invariance

Mid-flight reconcile of a healthy run takes NO action; final
business outcome identical with/without reconciliation (E26C4-12).
Skills/Knowledge/LLM/Recommendation/Report untouched (git diff).

## Regression

```
Runtime:     596 passed (582 + 14 new p26c4 tests)
26A 13/13 · 26B 10/10 · 26C-1 12/12 · 26C-2 15/15 · 26C-3 15/15
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS (targeted tracked roots)
```

## Findings

| ID | Severity | Finding |
|---|---|---|
| F-26C4-INFO-01 | INFO | Reconciliation is pull-based (reconcile_once) — no periodic timer; wiring it to worker startup / a future scheduler is deployment work (consistent with 26C-2 INFO-01 / 26C-3 boundary decisions) |
| F-26C4-INFO-02 | INFO | Filesystem-level checks (checkpoint/artifact presence) are deliberately OUT of the controller — the reconciler is DB-authoritative; payloads stay inputs to the proven 26B resume machinery |
| F-26C4-INFO-03 | INFO | INCONSISTENT pairs (corruption/bypass class) are flagged, not auto-repaired — operator attention required by design (fail closed) |

P0 = 0 · P1 = 0 · P2 = 0 · P3 = 0 · INFO = 3

## Scope discipline

NEW runtime/queue/recovery.py + `__init__.py` export line +
tests/runtime/test_p26c4_recovery.py + 3 docs
(PHASE_26C4_AUDIT / RECOVERY_RECONCILIATION / PHASE_26C4_RESULT).
Zero modifications to any existing runtime/test file this phase
(the worktree's prior 26C-1/2/3 changes are unchanged). Frozen
areas clean (skills/agents/knowledge/gateway/orchestrator/store/
model). Exactly-once NOT claimed.

Phase 26C-5 (Production Acceptance): NOT STARTED.
