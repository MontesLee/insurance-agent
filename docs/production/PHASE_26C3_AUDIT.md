# Phase 26C-3 Audit — Current Usage / Retry / Boundary Reality

Date: 2026-09-22 · Method: code-first (grep + read of runtime/llm,
runtime/repair.py, runtime/control/, runtime/orchestrator.py,
runtime/tasks.py, runtime/queue/) · No code was modified for this
audit.

[Outcome note: this audit directly led to the discovery and fix of
F-26C3-P1-01 (store.claim task_types precedence bug) during test
construction — full chain (finding → fix → regression E26C3-14 →
frozen-suite retest) in PHASE_26C3_RESULT.md.]

## Current Usage Accounting

**Per-call, REAL, UNKNOWN-fail-closed — but NOT aggregated per run.**

- `runtime/llm/types.py`: `LLMUsage(prompt_tokens, completion_tokens,
  total_tokens)` with an `UNKNOWN` sentinel default; `LLMCost`
  (input/output/total/currency) with `.status` = "UNKNOWN"/"KNOWN".
  Providers that return no usage leave `UNKNOWN` — never 0, never a
  string-length estimate (glm.py parses GLM's real
  prompt/completion/total tokens; cost stays UNKNOWN without
  pricing).
- `runtime/llm/gateway.py` `_log`/`_observe`: every gateway outcome
  (incl. each retry line and the final EXHAUSTED) logs
  `usage.to_dict()` + `cost_status`; Phase-25 metrics already
  declare `llm_calls_total`, `llm_success_total`, `llm_failure_total`.
- **No pricing configuration exists anywhere** (grep: zero
  price/pricing outside the UNKNOWN comment) → estimated cost is
  always UNKNOWN today. Honest basis for cost dimension:
  config-driven pricing table (new, small) or UNMETERED.

## Current Retry Accounting (verified counts)

| Layer | Where | Bound | Counted where |
|---|---|---|---|
| Provider/Gateway retry | llm/gateway.py `generate` | 1 + max_retries(=2) transient-only | gateway `_log` per attempt |
| Skill repair | orchestrator `_run_stage` + repair.py | per-stage max_attempts=3 (initial + 2 repairs), LOCAL | `state["stages"][sid]["attempts"]` via `tk.begin_attempt` (tasks.py:111) |
| Task retry | queue store.fail(retry=True) | task max_attempts (default 3) | `queue_tasks.attempt` (claim increments) |
| Replan | runtime/planner + control/monitor | max_replans=2, max_repairs=6 — **HARNESS path only** | control/monitor budget dict |
| Per-request token cap | gateway `_check_budget` | request.max_tokens ≤ max_total_tokens preflight | per request only |

**Failure semantics answer (§3, from code):** one gateway call that
times out / is rate-limited / returns malformed output produces at
most **1 + 2 = 3 provider attempts** (retryable-class errors only;
non-retryable → exactly 1). Worst case per task attempt (26B's
verified figure): TaskAttempts(≤3) × SkillExecutions(1+2 repairs) ×
LLMCalls(1+2) = ≤27 provider calls; the provider layer itself has
no retry.

## Current Run Boundary — is agent_runs a suitable Budget Owner?

Yes. 26C-2's `agent_runs` is the business-lifecycle authority keyed
by `run_id`, spanning task attempts, HITL waits and crash recovery
(deadline proven bit-identical across all of them). Budget must be
run-scoped for exactly the same reason (§5/§6: retry/recovery/HITL
must not reset it). Decision: budget lives beside the run row in a
dedicated `agent_run_budgets` table (+ append-only
`agent_run_budget_events` ledger for idempotent settlement and
audit), co-transacted with run/task terminal decisions through the
existing RunControl control points — NO second lifecycle machine,
no new run states.

## Critical path reality (does the queue path even call LLMs?)

**No.** `runtime/orchestrator.py` contains zero LLM references: the
26A/26B/26C queue path drives deterministic skills (engines +
knowledge + eval + repair). LLM calls exist only on the older
webui/harness path (`runtime/agent/`, `runtime/agents/executor.py`,
`runtime/planner/`). Consequences for 26C-3:

- `llm_calls_used` on the queue path is a REAL zero (nothing faked).
- The budget boundary must still exist, be PG-authoritative,
  race-safe and fail-closed for the dimensions that WILL matter
  (tokens/cost) — enforced and proven via the API with real usage
  payloads in tests.
- Metering hooks that are real TODAY: task attempts (queue row),
  repair attempts (orchestrator state `stages[sid].attempts`), replan
  count (0 on this path — planner is not in the queue path).
- LLM-choke-point wiring (gateway → run budget settlement) is
  designed (gateway already logs usage + cost_status per call) but
  deliberately NOT wired into skills — that would require touching
  business skills (forbidden). Recorded as Future/INFO.

## Gaps found (drive the minimal implementation)

1. NO run-level budget object anywhere (grep: none).
2. Usage is per-call only; nothing aggregates per run.
3. Task attempts / repairs are locally bounded but not run-scoped —
   nothing stops layers from stacking within a run beyond a global
   fuse.
4. No reservation semantics (§13 race) exist.
5. No UNKNOWN-usage fail-closed rule (§10) exists at run level.
6. No budget audit trail ("why did this run stop?" — §26).

## Chosen V0.1 dimensions

Metered + hard-limitable: `max_llm_calls`, `max_input_tokens`,
`max_output_tokens`, `max_estimated_cost`, `max_task_attempts`,
`max_repair_attempts`, `max_replans` (NULL = UNMETERED for that
dimension). Used-counters mirror each. UNKNOWN usage under a hard
token/cost limit → run becomes unverifiable → next control point
STOPS it (fail-closed; never treated as 0). Cost is computed from a
config-supplied pricing table (model → in/out price) at settlement;
unknown pricing → UNKNOWN cost → same fail-closed rule.
