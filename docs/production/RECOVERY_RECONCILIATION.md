# Recovery & Reconciliation (Phase 26C-4)

A minimal, pull-based `RecoveryController`
(`runtime/queue/recovery.py`) that INSPECTS durable state,
CLASSIFIES it, and applies DETERMINISTIC, CAS-guarded, idempotent
reconciliation — or fails closed. It reuses (never reimplements)
the frozen mechanisms: 26A `recover_expired()` + claim-side expiry,
26C-2 `expire_overdue()`, lease/attempt/run CAS guards, 26C-3
budget ledger semantics. It never plans, executes agents/skills/
LLM, or schedules beyond PENDING.

## reconcile_once() — one pass, three steps

1. **Expired leases** → `store.recover_expired()` (26A verbatim):
   LEASED/RUNNING past expiry → PENDING (lease cleared, attempt
   bumps on the next real claim — recovery never increments).
2. **Overdue runs** → `run_control.expire_overdue()` (26C-2
   verbatim): run+task terminalised TIMED_OUT in one transaction.
3. **Run/task consistency scan** (the 26C-4 boundary) — see below.

## Classification → action (deterministic matrix)

| State pair | Class | Action |
|---|---|---|
| run+task SUCCEEDED · terminal-run + CANCELLED task · non-terminal run + PENDING/in-flight (valid lease) · WAITING_HUMAN + waiting task | HEALTHY | none (audited) |
| run non-terminal + task terminal (SUCCEEDED/FAILED/CANCELLED/waiting) | RECOVERABLE | run ← task-mapped state, reason `task_terminal` — the TASK is the execution authority; CAS-guarded; NEVER fabricates |
| run terminal (FAILED/TIMED_OUT/CANCELLED) + task non-terminal | RECOVERABLE | task → CANCELLED carrying the run's terminal_reason (exactly the one-txn stop's co-write); a late worker's settle is then rejected by the task CAS |
| run SUCCEEDED + task ≠ SUCCEEDED · task SUCCEEDED + run FAILED/TIMED_OUT/CANCELLED | INCONSISTENT | NO mutation — audit event + `recovery.inconsistent`; never downgrades task success, never upgrades a terminal run |
| old worker/lease/attempt observed mutating | STALE | existing CAS rejects (no reconciler action needed) |
| not provable from durable state | UNKNOWN | fail closed (this build has no actionable UNKNOWN beyond INCONSISTENT) |

## Guarantees

* **Idempotent**: every action is one CAS/transaction;
  reconcile();reconcile();reconcile() ≡ reconcile()
  (state-equivalent; the audit trail is append-only by design).
* **Crash-safe** (Q12): a mid-reconcile crash is safely retried by
  re-running reconcile_once(); a failing step propagates (fail
  closed) and is audited as INCONSISTENT before the raise.
* **Terminal protection**: no SUCCEEDED/FAILED/TIMED_OUT/CANCELLED
  run or task ever moves to a non-terminal state through recovery —
  all writes are state-guarded (resurrection attempts get
  re-reconciled back to the terminal truth).
* **No scheduler**: pull-based `reconcile_once()` for worker
  startup / operators / a future timer. No daemon introduced.
* **Budget consistency (Q10)**: reservations are reported and
  PRESERVED (26C-3 strict fail-closed semantics); never reset
  without durable evidence.
* **Approval safety (Q9)**: an orphaned WAITING task under a
  terminal run is cancelled; approval remains refused by the
  status check + gate (26B binding matrix untouched).

## Audit

Every pass writes `recovery_events` rows (reconciliation_id,
classification, run_id, task_id, worker_id, old_state, new_state,
reason) — including HEALTHY observations — plus `recovery.pass` /
`recovery.inconsistent` obs events (stderr only; product stdout
untouched, Phase 25.1). Answers "what did reconciliation do and
why" without event replay: the scan reads current rows directly.

## Boundary decisions

* DB-authoritative only: checkpoint/artifact payloads remain INPUTS
  to the proven 26B resume machinery (attempt-dir isolation,
  newest-first) — the reconciler never touches the filesystem.
* Artifact-before-settle crash (Q7) = at-least-once re-execution
  (existing semantics); the queue row stays the business result.
  Terminal-without-result = INCONSISTENT, never faked (Q8).
