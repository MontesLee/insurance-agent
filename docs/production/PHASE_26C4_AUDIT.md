# Phase 26C-4 Audit — Existing Recovery Reality & Gaps

Date: 2026-09-22 · Method: code-first re-verification of
runtime/queue (store/worker/agent_runtime/run_control/budget/ops),
runtime/state checkpoint machinery, and the frozen-suite evidence
(26A/26B/26C-1/2/3 closures). No code modified for this audit.

## What ALREADY detects/recovers (reuse — do not reimplement)

| Concern | Mechanism (code) | Q covered |
|---|---|---|
| crash mid-flight | lease expiry → claim picks expired (attempt+1, new lease) or store.recover_expired() → PENDING | Q1, Q3 |
| expired lease, live worker | every write is lease CAS (DB clock); stale settle/heartbeat rejected | Q2 |
| old lease/worker/attempt returns | lease_id+status+expiry CAS; attempt-bound checkpoint dirs (newest-first, forward-only) | Q11 |
| checkpoint ambiguity | PHYSICAL attempt isolation — a stale attempt only writes its superseded dir; resolver is dir order, never mtime guessing | Q6 |
| artifact-before-settle crash | at-least-once re-execution; per-attempt artifacts are lineage, queue row is the business result | Q7 |
| overdue runs | rc.expire_overdue() — run+task terminalised in ONE txn (pull-based, no daemon) | Q5 (partial) |
| approval vs terminal run | approve_resume_gate refuses terminal/expired/budget-exhausted; 26B marker binding (project,run,task,stage) | Q9 (guard only) |
| budget reservation after crash | PG ledger; reservation persists and still bounds (strict fail-closed, 26C-3 INFO-02) | Q10 |
| DB failure / commit unknown | OutcomeUnknown → RECOVERY_REQUIRED; single-txn run/task terminal decisions cannot half-commit | Q12 (partial) |

## Gaps (drive the minimal 26C-4 boundary)

1. NO unified detect→classify→reconcile scan for run/task drift:
   a task settled through a bypassed layer (or SQL drift) can leave
   run RUNNING + task terminal, or run terminal + task non-terminal
   (a terminal run's task stays claimable→released forever).
2. No audit trail answering "what did reconciliation do and why".
3. No single idempotent entrypoint (reconcile_once) an operator /
   worker-startup / future scheduler can call safely.

## Chosen classification (§7) with deterministic actions

* HEALTHY — consistent pair (or in-flight with a valid lease): no
  action.
* RECOVERABLE — deterministic, one-directional, CAS-guarded sync:
  - run NON-terminal + task terminal: run ← task-mapped state
    (SUCCEEDED / FAILED / WAITING_HUMAN / CANCELLED; reason
    task_terminal). Task = execution authority (26C-2 authority
    split) — Case F resolved WITHOUT fabricating anything.
  - run terminal (FAILED/TIMED_OUT/CANCELLED) + task non-terminal:
    task → CANCELLED carrying the run's terminal_reason (exactly
    what _budget_stop/_expire would have co-written). Late workers
    are then rejected by the task CAS (Q11). Never SUCCESS.
  - expired leases: reuse recover_expired()/claim semantics.
* STALE — old worker/lease/attempt attempting mutation: existing
  CAS rejects (no reconciler action needed; classification
  surfaces in events when observed).
* INCONSISTENT — run SUCCEEDED + task not SUCCEEDED (impossible
  via the API; corruption/bypass), or task SUCCEEDED + run
  FAILED/TIMED_OUT/CANCELLED: NO mutation, audit event, operator
  attention (fail closed — never downgrade task success, never
  upgrade a terminal run).
* UNKNOWN — cannot be proven from durable state: no auto-complete;
  surfaced as INCONSISTENT/fail-closed (this system's durable
  state is the queue+run rows; nothing actionable is UNKNOWN
  beyond the INCONSISTENT class — kept as an explicit outcome for
  future filesystem-level checks).

## Boundary decisions

* The controller is DB-authoritative ONLY: checkpoint/artifact
  payloads stay INPUTS to the existing resume machinery (26B
  proven); the reconciler never reads/writes the filesystem, never
  executes agents/skills/LLM, never schedules (it may set PENDING —
  execution stays queue+worker).
* Every reconcile action is a single CAS/transaction → a
  mid-reconcile crash (Q12) is retried idempotently by re-running
  reconcile_once().
* Audit: recovery_events table + obs events (stderr; product
  stdout untouched per Phase 25.1).
