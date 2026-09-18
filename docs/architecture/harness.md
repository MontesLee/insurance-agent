# Long-running Harness

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](harness.zh-CN.md)

Source of truth: `runtime/harness/harness.py`,
`runtime/orchestrator.py`, `runtime/state/`, `runtime/tasks.py`,
`runtime/checkpoint.py`.

## 1. Positioning

The Harness owns **WHEN** and **reliability**: task lifecycle, dependency
enforcement, scheduling (sequential or bounded-parallel), eval invocation,
repair, checkpoints, recovery, handoff consumption. It never makes insurance
judgments and never delegates its authorities:

- Only the Harness may set `PASSED / FAILED / NEEDS_REVIEW / BLOCKED`.
- Only the Harness runs Eval (`_run_eval_and_repair`) and Repair.
- Only the Harness writes checkpoints and task states.
- Agents execute; the MessageBus coordinates; the graph is immutable.

## 2. Project model on disk

```text
<harness_root>/
  projects.json                    # index of all projects
  <project_id>/
    project.json                   # project metadata + task list (statuses, deps, attempts)
    events.jsonl                   # durable, append-only harness event log
    checkpoints.jsonl              # harness-level checkpoint records
    messages.jsonl                 # MessageBus store (A2A)
    case/
      case_state.json              # the CaseState (stages, tasks, artifacts, evals, trace)
      artifacts/<type>.json        # one inspectable file per artifact
```

Everything a running process owns in memory can be reconstructed from this
layout: a **new** `LongRunningHarness` instance (or process) calls
`load_project()` + `resume()` and continues.

## 3. Task state machine (project level)

States (exactly as implemented — `PENDING, RUNNING, PASSED, FAILED,
BLOCKED, NEEDS_REVIEW, COMPLETED`), all transitions performed by the
Harness:

```text
PENDING ──schedule──▶ RUNNING ──eval PASS──▶ PASSED      (terminal-ok)
   │                    │
   │                    ├──agent/eval fail, repairs exhausted──▶ NEEDS_REVIEW (terminal)
   │                    └──worker exception──▶ NEEDS_REVIEW     (terminal)
   │
   ├──dependency FAILED/NEEDS_REVIEW/BLOCKED──▶ BLOCKED          (terminal)
   ├──assignment invalid──▶ BLOCKED                               (terminal)
   ├──unknown task_type──▶ FAILED                                 (terminal)
   └──stage already COMPLETED on disk──▶ COMPLETED                (terminal, skipped)
RUNNING ──process interruption + resume──▶ PENDING                (recovery, never assumed PASS)
```

- Terminal means: never re-executed (idempotency) and checkpointed.
- A `NEEDS_REVIEW`/`FAILED`/`BLOCKED` dependency makes downstream tasks
  `BLOCKED` — failure propagates, it is never converted into a pass.
- Parallel mode adds the same semantics per round; see
  [parallel-scheduler.md](parallel-scheduler.md).

**Stage-level state** (inside CaseState) mirrors this with the vocabulary
`PENDING / RUNNING / COMPLETED / FAILED / NEEDS_REVIEW / SKIPPED`; the task
ledger (`runtime/tasks.py`) mirrors stage status through a single write
path (`set_status`), and `check_mirror()` is a tested invariant.

## 4. Execution modes

### Sequential (`max_concurrency=1`, default — Phase 6 path)

For each task in graph order: deterministic agent assignment +
`validate_assignment` → dependency check → idempotency skip (stage already
COMPLETED, unique-stage dedup) → execute (specialist agent via
`SpecialistAgentExecutor`, or the deterministic reference runtime) →
Harness eval + repair ≤ 2 → terminal state → checkpoint. Afterwards a
bounded handoff loop (≤ 5 rounds) consumes messages and re-runs activated
pending tasks.

### Parallel (`max_concurrency > 1`)

Round-based (BSP): compute the runnable set → fill up to `max_concurrency`
slots → workers execute agent tasks on isolated CaseState copies (reference
tasks run in the scheduler thread) → round barrier → **commit in graph
order** (merge artifacts, replay worker events, harness eval + repair,
checkpoint). Full detail: [parallel-scheduler.md](parallel-scheduler.md).

## 5. Persistence matrix (verified from code)

| Component | Persistent? | Mechanism |
| --- | --- | --- |
| Project | durable | `project.json` + `projects.json` index |
| Task state | durable | inside `project.json` (status, deps, attempts, assigned agent) |
| CaseState | durable | `case/case_state.json` (written on every checkpoint) |
| Artifacts | durable | `case/artifacts/<type>.json` + inside CaseState |
| Artifact registry / lineage | durable | inside CaseState (`artifact_registry`) |
| Evals / repairs | durable | inside CaseState (`evaluations`, task `repairs`) |
| Checkpoints | durable | `checkpoints[]` in CaseState + `checkpoints.jsonl` records |
| Harness events | durable | append-only `events.jsonl` |
| Trace | durable | `state["trace"]` (+ `trace.jsonl` mirror for run roots) |
| MessageBus | durable | append/rewrite `messages.jsonl` |
| EventBus (SSE) | **in-memory** | publish/subscribe bus; rebuilt from trace on demand |
| RunManager runs | **in-memory** | run registry over durable case dirs |
| Chat sessions | **in-memory** | V0.1 `ChatManager` by design |

## 6. Recovery

- `resume(project_id)` works from a **new process**: load project + validate
  CaseState (`checkpoint.validate`: parse, case-id match, schema, registry
  fingerprint verify, task→stage integrity — any failure is
  `CHECKPOINT_INVALID`, never a silent resume from corrupt state).
- Recorded recovery policy: a task left `RUNNING` by an interrupted run is
  reset to `PENDING` (event `task_recovered`) and re-executed — **never
  assumed PASS**. `PASSED`/`COMPLETED` tasks are skipped without invoking
  agents, evals or artifacts again.
- Honesty note: this is **disk-based, process-independent resume**
  (crash-interruption is simulated in tests by reloading state from disk).
  It is not distributed crash recovery and makes no claim to be.

## 7. Failure model (detection → handling → final state)

| Failure | Detection | Handling | Final state |
| --- | --- | --- | --- |
| Planner output invalid | schema/graph validator | bounded retry ≤ 2, then surface errors | `needs_review` plan (nothing executes) |
| Agent execution fails | executor returns `AGENT_FAILED` (step limit, empty response, LLM error, output invalid) | no eval; task fails | task `NEEDS_REVIEW`, downstream `BLOCKED` |
| Tool fails | structured tool result (`status=failed/needs_review`) | agent sees the structured error; `needs_review` stops the turn | turn `needs_review` (chat) / task `NEEDS_REVIEW` |
| Eval FAIL | harness eval record | repair ≤ 2: re-run agent, re-eval | PASS, or `NEEDS_REVIEW` after exhaustion |
| Repair not applicable | `repair.plan()` returns no action | immediate escalation | `NEEDS_REVIEW` |
| Dependency failed | dependency status check | downstream never starts | `BLOCKED` (cascades) |
| Assignment invalid | `validate_assignment` | task never runs | `BLOCKED` + `agent_validation_failed` |
| Worker crash (parallel) | exception inside worker | converted to one task's result; other tasks unaffected | that task `NEEDS_REVIEW` |
| Artifact collision on merge | fingerprint comparison in scheduler merge | `MERGE_REJECTED` — never overwrite | task fails, state stays consistent |
| Message invalid/self/unauthorized | MessageBus / handoff validators | message `FAILED`; run never breaks | coordination only |
| Process interruption | missing/dangling state on disk | resume: `RUNNING → PENDING`, terminal tasks skipped | consistent continuation |
