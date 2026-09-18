# Phase 7 — DAG-aware Bounded Parallel Scheduler

Phase 7 upgrades the Harness from a **sequential scheduler** to a
**DAG-aware scheduler with bounded concurrency**, on top of the frozen
Phase 6.2.2 runtime. It changes scheduling only — not responsibility
boundaries:

```text
Planner      = WHAT          (immutable Task Graph, unchanged)
Harness      = WHEN/CONTROL  (the ONLY scheduler / concurrency controller)
Agent        = HOW           (executes; never decides parallelism or PASS)
Artifact     = TRUTH         (canonical schema unchanged)
MessageBus   = COORDINATION (never starts workers, unchanged protocol)
Eval         = QUALITY       (Harness-owned, unchanged strictness)
Checkpoint   = RECOVERY      (per terminal task, disk-based)
```

## Configuration

```python
LongRunningHarness(root, agent_executor=..., max_concurrency=1)   # default
```

- `max_concurrency=1` (default) — the Phase 6 **sequential** path runs,
  byte-for-byte unchanged. All Phase 6 behavior (message-driven handoffs,
  eval boundary, repair, checkpoint/recovery, 4-Agent E2E) is preserved.
- `max_concurrency >= 2` — independent tasks in the task graph execute
  **concurrently** (thread-based worker pool). Invalid values (`0`, `-1`,
  non-int) fail fast at construction.

## Scheduler model

Round-based (BSP) loop inside `Harness.run()`:

1. **Runnable set** — `PENDING` tasks whose dependencies are all
   `PASSED`/`COMPLETED`, in stable graph order. A task whose dependency is
   `FAILED`/`NEEDS_REVIEW`/`BLOCKED` becomes terminally `BLOCKED`.
2. **Bounded fill** — up to `max_concurrency` slots per round; a task is
   never in two workers at once (`running_task_ids` ledger + `RUNNING`
   status).
3. **Isolated execution** — agent tasks run in worker threads on deep
   copies of the CaseState; reference (deterministic-runtime) tasks run in
   the scheduler thread on the main state (the Phase 6 code path). Workers
   never write the shared project/state/checkpoints.
4. **Graph-order commit** — after the round barrier the scheduler (the only
   writer) commits in graph order: merge artifacts through the canonical
   `put_artifact` + `artifact_registry` path (sequential, unique
   `ART-`/`EVAL-` ids regardless of thread timing), replay worker events,
   run the Harness-owned Eval + Repair (≤ 2), set the terminal status, and
   checkpoint every terminal state.
5. **Messages** — handoffs are consumed after execution exactly as in
   Phase 6; the MessageBus still never starts a worker. Handoff-activated
   tasks go through another bounded parallel pass.

Crash recovery: a task left `RUNNING` by an interrupted process is
recovered to `PENDING` (recorded as a `task_recovered` event) — never
assumed `PASS` — and already-terminal tasks are skipped, not re-executed.

Known asymmetry: in parallel mode `force_rerun` overrides only the
stage-completed skip, never already-`PASSED`/`COMPLETED` tasks —
idempotency outranks force-rerun (a deliberate, documented limitation,
not a bug).

## Honest scope

This is a **single-process, thread-based, bounded scheduler**. It is not
distributed execution, not a production-grade cluster scheduler, and not a
fault-tolerant distributed system: no distributed workers, no dynamic
replanning, no external/persistent queue; recovery remains disk-based
(JSON checkpoints under the harness root).

Tests: `tests/runtime/test_parallel_scheduler.py` (T1–T21 + no-self-pass)
and `tests/runtime/test_parallel_4_agent_e2e.py` (true parallel 4-agent
E2E, overlap proven by a blocking probe inside the LLM loop).
