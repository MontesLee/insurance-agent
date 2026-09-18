# Architecture — interview deep-dive guide

> The full diagrams live in [../architecture.md](../architecture.md) and
> [../architecture/overview.md](../architecture/overview.md). This page is
> the whiteboard version plus the追问 (follow-up) answers.

## The whiteboard diagram

```text
                      User
                        │
                        ▼
                    Planner ──(untrusted JSON)──▶ Graph Validator
                        │                            │ fail-closed
                        ▼ (validated task graph)     ▼
                Long-running Harness ◀──────── NEEDS_REVIEW
        ┌───────────────┼────────────────┐
        │               │                │
   DAG Scheduler      Eval/Repair     Checkpoint/Recovery
   (sole writer)      (harness-owned)  (per terminal task)
        │
        ▼
  Specialist Agents (isolated workers on state copies)
        │  tools → artifacts (skip_eval)
        ▼
  Artifact Registry (lineage · fingerprints · provenance)
        │
        ▼
   Eval ──PASS──▶ commit + checkpoint ──▶ next runnable / replan
     └──FAIL──▶ Repair ≤2 ──▶ re-eval ──▶ NEEDS_REVIEW

  MessageBus: agent⇄agent coordination ONLY (never schedules)
  Monitor: observes events/state → signals → InterventionPolicy
  Human: HITL approval gates · HOTL pause/resume/retry/replan
```

Authority table: **Harness = runtime authority · Planner = plan authority
· Monitor = observe only · Agent = execute/request · Human =
approve/intervene (via control plane only).**

## Follow-up questions (30–60s answers)

**An agent crashes — what happens?**
Worker exceptions are caught and become that ONE task's AGENT_FAILED →
NEEDS_REVIEW; the round's other tasks commit normally. A crashed process
leaves durable state: resume resets RUNNING→PENDING and only re-executes
non-terminal tasks.

**A task fails eval — then what?**
Harness-owned repair: the producer re-runs with failed checks as feedback,
≤ 2 repairs (3 executions), re-evaluated each time; exhaustion →
NEEDS_REVIEW, downstream BLOCKED; possibly a deterministic replan trigger.

**The Planner emits a broken DAG?**
It never executes: 10-check validator (schema, registry types, deps,
cycles, artifact/eval contracts). Bounded planner retry ≤ 2, then fail
closed with errors surfaced. Invalid output can't touch the active graph.

**Two agents modify state simultaneously?**
They can't: workers run on deep-copied CaseState; only the scheduler
thread merges/evals/checkpoints, in graph order — deterministic ids, no
lost updates (parallel tests assert identical artifact ids run-to-run).

**Replan while parallel workers are running?**
Never: replanning is evaluated only at safe barriers after the round
fully commits; `_run_replan` refuses if anything is RUNNING. Workers never
see an unapproved/mid-change graph.

**A human asks to pause mid-run?**
PAUSE sets PAUSING; the current round completes and commits; the pause
lands at the barrier. No worker is killed mid-commit (tested with an
in-flight parallel run).

**How do you prevent agent self-PASS?**
Three layers: tools run skip_eval (store-only); the executor returns
ARTIFACT_READY, never PASS; `_commit_agent` maps any non-eval outcome to
failure — a worker returning OK yields NEEDS_REVIEW (F18 + T9b tests).

**How do I know the benchmark isn't fake?**
Instrumentation (the real eval engine/registry/harness were call-counted
during benchmark runs) + tamper testing: six runtime mutations each flip
the benchmark to FAIL. Verification reads durable state, never fixtures.

**How is provenance guaranteed?**
Registered artifacts carry producer + input lineage + fingerprints; eval
resolves evidence/document refs; registry.verify() re-checks fingerprints
on every load — mutated artifacts fail loudly (CHECKPOINT_INVALID).

**Why a harness at all?**
Agents are untrusted executors; someone must own scheduling, state, eval,
recovery and control. Concentrating WHEN in one authority is what makes
determinism, idempotency and fail-closed behavior provable.

**Why not agent→agent direct calls?**
Direct calls bypass dependency/eval/authority: no barrier, no eval gate,
no audit. All coordination goes through the validated MessageBus; the
harness still decides what runs.

**Where's the LLM in all this?**
At the edges: planner proposals (validated), the specialist executor loop
(schema-checked tool calls), chat intent routing. Control flow, state
transitions, eval and scheduling contain zero LLM judgment by design.
