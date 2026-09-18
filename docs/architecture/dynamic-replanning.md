# Phase 8 — Dynamic Replanning V0.1

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](dynamic-replanning.zh-CN.md)

Source of truth: `runtime/harness/harness.py` (replanning section),
`runtime/planner/planner.py` (`replan`), `runtime/planner/prompts.py`
(`build_replan_prompt`), `tests/runtime/test_dynamic_replanning.py`.

## 1. Why replanning exists

Before Phase 8, a task graph was fixed for the lifetime of a project: a
repair-exhausted task or a structural dead-end could only end the project
in `NEEDS_REVIEW`. Real runs reveal information the original plan could
not know (a step that cannot succeed, a blocked path). Phase 8 lets the
**Harness** ask the Planner for a new graph — under strict control:

> Harness-controlled, bounded dynamic replanning with immutable graph
> revisions and deterministic validation. Not autonomous self-modification.

The central rule is unchanged: **agents execute the graph and never own
it; the Harness owns execution; the Planner owns planning; a replan is a
controlled Harness → Planner operation.**

## 2. Trigger policy (deterministic)

`_evaluate_replan_trigger` — the LLM never decides `should_replan`:

- budget remains (`len(replans) < max_replans`, default 2)
- no task is `RUNNING` (safe barrier, R1)
- **TASK_BLOCKED**: at least one structurally dead-end `BLOCKED` task
- **TASK_NEEDS_REPLAN**: a repair-exhausted `NEEDS_REVIEW` task **with
  downstream dependents** — a failed leaf stays `NEEDS_REVIEW`;
  `NEEDS_REVIEW` never automatically means replan (§9)
- ordinary eval failures are NOT triggers — they follow the normal
  Repair path first; only repair exhaustion can qualify
- `MISSING_REQUIRED_INFORMATION` / `EXTERNAL_RESULT_CHANGED` are
  representable categories, not auto-produced in V0.1

## 3. Safe barrier (§7)

A replan is evaluated **only after the current scheduler round has fully
completed**: in parallel mode after `_run_parallel` returns (all workers
joined, all results committed, eval/repair done); in sequential mode
after the main pass and handoff loop. `_run_replan` additionally refuses
(`UNSAFE_BARRIER`) if any task is `RUNNING` — belt-and-braces on top of
the barrier (tested in T3).

## 4. The replan operation

```text
safe barrier → trigger → ReplanContext (ids, statuses, artifact summary,
                                          trigger, history — no raw dump)
                       → planner.replan(provider, context)     # SAME strict
                       → JSON schema + Graph Validator           # pipeline,
                       → bounded retry ≤ 2                      # fail-closed
                       → structural fingerprint (sha256, canonical JSON)
                            == current graph → REPLAN_NO_CHANGE (loop stop)
                       → apply as immutable revision v2 (merge semantics)
                       → graph diff recorded + events
                       → execute the new PENDING tasks
```

- **Graph revision / lineage**: `project.graph_revisions[]` — immutable
  snapshots `{revision, parent_revision, trigger, planner_run_id, status,
  created_at, tasks, diff}`; revision 1 is snapshotted at project creation.
  v1 is never mutated into v2 (R5, tested by snapshot equality).
- **Merge semantics**: same `task_id` + terminal-ok (`PASSED`/`COMPLETED`)
  → preserved verbatim, never re-executed (R6); same id + non-terminal →
  reset to `PENDING` under the new revision (audited in `diff.rerun`);
  new id → `PENDING`; v1 task absent from v2 leaves the active list and
  survives in its snapshot + `diff.removed`.
- **Task identity**: task ids across revisions (the replan prompt
  instructs the Planner to reuse ids of completed tasks it keeps and mint
  new ids otherwise). New tasks carry `graph_revision_introduced`.
- **Artifacts** live in CaseState, not in the graph: they survive the swap
  unchanged and remain consumable by v2 tasks (R7, tested via lineage).
- **Diff** (`_graph_diff`): machine-computed `{added, removed, preserved,
  rerun, dependency_changes}` — never LLM text.

## 5. Budget, loops, failure

- `max_replans` (default 2, `0` disables, validated ≥ 0): every replan
  attempt counts; exhaustion leaves the project `NEEDS_REVIEW`.
- Identical-structure guard: canonical fingerprint of the candidate vs
  the active graph → `REPLAN_NO_CHANGE` (deterministic hash, no LLM).
- Planner failure (bounded retries exhausted or provider error):
  `replan_failed`, fail-closed — **no fallback graph, no silent revert**;
  the active graph and its state stay intact (R12).
- Crash during a replan: the attempt is persisted `in_progress` *before*
  the planner runs; recovery marks it `failed` (`INTERRUPTED…`) and never
  assumes success (R11). The active graph only ever swaps inside one
  `project._save()`.

## 6. Events

`replan_triggered` → `replan_started` → (`graph_validation_*` from the
planner) → `graph_revision_created` → `replan_completed` | `replan_failed`.
All carry `project_id` plus `replan_id` / `graph_revision` /
`parent_revision` / `trigger` / diff summaries — structured data only,
no chain-of-thought. `graph_revision_created` also fires once at project
creation (`trigger=INITIAL`).

## 7. Authority boundaries (unchanged)

- Agents: no planner access, no graph mutation, no `graph_revision` or
  `max_replans` reach (structural tests). The MessageBus remains
  coordination-only — it cannot create/mutate tasks or trigger replans.
- Only the Planner produces candidate graphs; only the Graph Validator
  makes them trusted; only the Harness applies them.
- Eval ownership is untouched: replanning never bypasses eval; new tasks
  go through the same Harness-owned eval + repair.

## 8. Compatibility

`max_concurrency=1` keeps the Phase 6 sequential path (replan evaluated
after the handoff loop); `max_concurrency>1` evaluates replans between
parallel passes. Phase 6/7 test suites all pass unchanged (248 runtime
tests).

## 9. Current limitations

- Replan happens **between** scheduler rounds, not mid-round (by design).
- Trigger categories auto-produced in V0.1 are `TASK_BLOCKED` and
  `TASK_NEEDS_REPLAN` only.
- The merge recognizes completed work by `task_id` — a v2 task that
  re-specifies the same work under a new id will re-execute it.
- No human-approval gate on replans yet; no replan for
  `MISSING_REQUIRED_INFORMATION` (future work, see roadmap).
