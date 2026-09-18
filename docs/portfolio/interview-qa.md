# Interview Q&A — 30 questions, 30–60s answers

> Format: 结论 → 设计 → 原因 → Trade-off. Practice saying each aloud.
> Architecture deep-dives: [architecture-interview.md](architecture-interview.md).

## Architecture

**1. Why do you need a Harness?**
Agents are untrusted executors; a long-running system needs one owner of
scheduling, state, eval and recovery. The harness is that single authority
— which is what makes determinism and fail-closed behavior provable.

**2. Why separate Planner and Harness?**
The planner proposes WHAT (untrusted, validated as data); the harness
decides WHEN (sole state writer). Mixing them means whoever plans also
grades execution — the self-grading problem again.

**3. What is the Agent Registry?**
Hand-curated agent definitions: allowed task types, allowed tools, prompts.
The trusted source for "who may do what" — assignments are validated
against it before execution, and it's domain config, not runtime code.

**4. Why does A2A need a MessageBus?**
Direct agent calls bypass dependency/eval/audit. The bus persists,
validates (sender, target, policy, artifact refs) and delivers
coordination-only messages; the harness remains the only scheduler.

**5. Why are artifacts the source of truth?**
Chat evaporates; registered artifacts persist with lineage, fingerprints
and provenance. Messages coordinate; artifacts are what eval gates and
what the report is built from.

**6. Why is the scheduler round-based (BSP) instead of continuous?**
Graph-order commits need a barrier: deterministic artifact/eval ids
regardless of thread timing. Trade-off: a slow task holds the round —
bought determinism, stated openly.

**7. What's a safe barrier?**
A point where no worker is running and all results are committed: between
BSP rounds / after the sequential pass. Replanning, pauses and monitor
interventions only ever happen there.

**8. How does checkpoint/resume work?**
Checkpoint per terminal task (CaseState + artifact files + harness log);
a NEW process loads the project, validates the state (5 checks incl.
fingerprint verify) and continues; RUNNING tasks recover to PENDING.

**9. What's the event model?**
Durable per-project events.jsonl (append-only) + CaseState trace; workers'
events are captured and replayed in commit order; SSE observes, never
drives.

**10. Why immutable graph revisions?**
Replanning without revision history is unaccountable. Each revision is a
snapshotted DAG node with parent, trigger, diff; v1 is never mutated;
completed work carries over by task identity.

## Agent Engineering

**11. Why not one agent?**
No enforceable boundaries. Specialists get scoped tools (analyst can't
name products), per-artifact eval, localized failures, parallel execution.
Cost: orchestration — which became the harness.

**12. How do agents collaborate?**
Via validated TASK_HANDOFF messages on the bus; the harness consumes
handoffs and ACKs only after the target task passes. Agents never invoke
each other.

**13. How do you prevent agent overreach?**
Registry-validated assignment + scoped tools + schema-validated arguments
+ no graph/state access + actor allowlists on every control surface.
Structural tests grep the boundaries; behavior tests try to violate them.

**14. Can an agent call another agent directly?**
No — and that's enforced by construction (no code path), not by prompt.
Coordination is messages only.

**15. Why deterministic task→agent mapping?**
Who does the work is governance. Model-chosen assignment is unauditable;
the mapping is registry config a product owner controls.

**16. What's in a task's execution contract?**
Workers receive task + agent + immutable context copy; return a
TaskExecutionResult (status, artifacts, metadata, error) — and can never
set PASS.

**17. How does tool calling stay safe?**
JSON-schema argument validation before execution, per-agent tool scopes,
structured results fed back to the LLM; eval deliberately NOT in the tool.

**18. How do you bound agent loops?**
Specialist executor ≤ 8 steps, chat loop ≤ 12, LLM malformed-output retry
≤ 2 — every limit ends in fail-closed NEEDS_REVIEW, never fake success.

## Evaluation / Reliability

**19. How does eval prevent false passes?**
Deterministic rule-driven checks (schema, fields, contamination,
provenance, cross-artifact, catalog invariants) independent of the
producer; plus an adversarial false-pass suite proving bad inputs are
rejected (count 0).

**20. Why max 2 repairs?**
Three executions bound the cost of a failing producer while surviving
transient artifact problems. Unbounded retry hides systemic failure; two
surfaces it as NEEDS_REVIEW.

**21. Agent crash handling?**
Exception → that task AGENT_FAILED → NEEDS_REVIEW; rest of the round
commits. Process crash → durable resume, RUNNING→PENDING, terminal tasks
never re-executed.

**22. Planner failure handling?**
Bounded retry (3 attempts) then fail-closed with accumulated errors; the
active graph is untouched. Replan attempts are audited records.

**23. External LLM timeout?**
Provider reachability is probed; outage → FAIL-CLOSED (or honest SKIP if
unconfigured) — never a silent deterministic fallback masquerading as a
pass.

**24. How do you prove determinism?**
3× identical runs compared on task statuses, artifact IDs (sequential,
commit-order), eval verdicts, revision. Timestamps/uuids are explicitly
excluded as runtime metadata.

**25. How do you know parallel didn't corrupt anything?**
Concurrency 1 vs 2 compared semantically (identical artifacts AND ids);
registry fingerprints re-verified; duplicate-execution gate = completed
work never restarted.

## HITL / HOTL

**26. HITL vs HOTL?**
HITL: human as decision gate (WAITING_HUMAN → approve/reject) for
high-impact changes. HOTL: human as supervisor above the DAG (monitor →
policy → notify/pause/resume) while execution stays autonomous.

**27. Why can't humans edit CaseState directly?**
Un-audited state mutation breaks every invariant. Human input arrives as
a provenance-carrying human-input artifact with append-only conflict
records; commands go through the validated, idempotent control plane.

**28. Why pause only at safe barriers?**
Mid-commit mutation = half-written state. PAUSING defers to the round
boundary; workers always finish and commit; resume is then clean and
idempotent (with alert acknowledgment).

## Generalization

**29. Why is the runtime generic?**
Generic modules are code-level domain-free (verified by scan); domains
live in declarative adapters. Demonstrated: a software-engineering
workflow completes on the unchanged runtime (5/5 tasks, 5/5 evals,
lineage verified).

**30. Insurance → finance/legal next?**
Replace the adapter: task registry, agents, workflow, contracts,
knowledge, catalog, eval rules. Runtime untouched. Known friction points
(schema vocabulary etc.) are documented in generalization.md.
