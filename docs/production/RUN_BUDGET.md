# Run Budget — Bounded Execution (Phase 26C-3)

One budget per RUN (PG-authoritative, absolute, write-once). The
budget is a CONTROL BOUNDARY beside the 26C-2 lifecycle: it adds NO
run states — exhaustion terminalises the run `FAILED` with reason
`budget_exceeded:<TYPE>` and the task `CANCELLED` with the same
reason (the 26C-2 expiry pattern). Deadline (HOW LONG) and budget
(HOW MUCH) stay independent; a run must satisfy both.

## Dimensions (V0.1)

| Dimension | limit column | metered from |
|---|---|---|
| llm_calls | max_llm_calls | gateway-call settlement (real per-call records) |
| input_tokens | max_input_tokens | provider usage (prompt_tokens) at settle |
| output_tokens | max_output_tokens | provider usage (completion_tokens) at settle |
| estimated_cost | max_estimated_cost | pricing config × real tokens |
| task_attempts | max_task_attempts | queue claim attempts (run-scoped total) |
| repair_attempts | max_repair_attempts | orchestrator stage attempts−1 (per settle) |
| replans | max_replans | replan settlements (0 on the deterministic queue path today) |

`NULL` limit = UNMETERED for that dimension. Used-counters mirror
each; `llm_calls_reserved` carries race-safe reservations.

## Hard rules

* **Absolute** — limits are write-once (`configure` is
  INSERT-only, ON CONFLICT DO NOTHING). Retry, replan, HITL resume,
  worker crash and recovery NEVER reset or raise anything.
* **Reserve before consume** (llm calls): ONE CAS statement
  (`reserved + n <= max`) — concurrent workers can never
  oversubscribe. Tokens/costs cannot be pre-known: they are
  settle-gated at the control points.
* **NO FAKE ACCOUNTING**: tokens come from real provider usage; a
  missing value is the `UNKNOWN` sentinel — recorded as a flag,
  never added as 0. Cost comes from the explicit pricing config
  (`{model: {input_per_1k, output_per_1k}}`); unknown pricing →
  UNKNOWN cost.
* **UNKNOWN fails closed**: with a HARD token/cost limit set, an
  UNKNOWN flag means compliance cannot be proven → the next control
  point STOPS the run (`MAX_USAGE_UNKNOWN_UNDER_HARD_TOKEN_BUDGET`
  / `MAX_COST_UNKNOWN_UNDER_HARD_COST_BUDGET`). UNKNOWN never
  counts as zero.
* **Hard stop**: `RUN_BUDGET_EXCEEDED` — no continue, no retry, no
  repair, no replan; terminal; only a human can start a NEW run.
  No automatic budget increase anywhere.
* **Soft budget** (80% default): a `SOFT_WARNING` ledger event
  (audit/metric only) — never changes behavior.
* **No fabricated success**: a completion whose settled usage
  exceeds a hard limit is converted IN THE SAME TRANSACTION to
  FAILED + budget reason; `result` stays NULL.
* **Idempotent settlement**: every reserve/settle/release appends
  one `agent_run_budget_events` row keyed by a UNIQUE `event_key`;
  replays are visible NO-OPs. First successful results are never
  duplicated.
* **Crash safety**: reservations/usage live in PostgreSQL — a
  killed worker's reservation persists and still bounds new
  reserves (fail-closed); re-settlement after recovery is
  idempotent.

## Control points (no daemon)

`RunControl` enforces the budget at its EXISTING 26C-2 points:
before start (`pre_start`), before settle-success, before retry
(with one extra attempted task-attempt), before HITL
approval-resume. `RunBudget.expire`-style periodic reconciliation
is unnecessary: usage only moves at settlements, so the check is
always current at the next control point.

## API (runtime.queue.RunBudget)

```
configure(run_id, **limits)         # write-once; returns the row
snapshot(run_id)                    # limits + used + reserved + flags
reserve_llm_call(run_id, n, event_key)   # CAS; BudgetExceeded
release_reservation(run_id, n, event_key)
settle(run_id, event_key, *, llm_calls, input_tokens,
       output_tokens, cost, task_attempts, repair_attempts,
       replans)                     # idempotent ledger settlement
estimate_cost(model, in_tokens, out_tokens)  # config pricing / UNKNOWN
check(run_id, extra_task_attempts)  # hard gate (raises) + soft events
```

`AgentTaskWorker(run_control=RunControl(..., budget=RunBudget(...)))`
activates the boundary; without a budget everything behaves exactly
as 26C-2. Executor results may carry `budget_usage:
{repair_attempts, replans}` (the agent executor derives REAL
repair counts from orchestrator state).

## Layering (existing bounds preserved — budget is the total fuse)

provider (none) < gateway retry 1+2 < skill repair ≤2/stage <
run task-attempt budget < task max_attempts ≤3 (local) < run
deadline (26C-2) < run budget (26C-3). No existing retry limit was
expanded.

## Auditability

"Why did this run stop?" = run row (`terminal_reason =
budget_exceeded:<TYPE>`) + task row (`retry_reason`) + the
`agent_run_budget_events` ledger (RESERVE / SETTLE / RELEASE /
SOFT_WARNING with type/limit/used/reserved per event) + the
`run.budget_exceeded` obs event carrying the full detail dict.
Obs/metrics surface: budget limit/used/remaining per check;
`budget_exhausted_total`/`budget_warning_total` class counters fit
the existing Phase-25 metrics seam (llm_calls_total &
tokens_total already exist there).

## Known limits (documented debt)

* LLM-choke-point wiring: the queue path today runs deterministic
  skills (zero LLM calls — a REAL zero, not a faked meter). The
  gateway already emits real usage + cost_status per call; joining
  gateway call logs to run budgets is Future work (would require
  run context in skills — out of scope, business skills frozen).
* No dynamic budget editing, no HTTP API, no dashboard (by phase
  boundary). Human control = start a NEW run.
* Reservation leak on crash: an abandoned reservation stays counted
  until the run ends (strictest fail-closed choice; §15).
