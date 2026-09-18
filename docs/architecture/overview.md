# Architecture Overview

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](overview.zh-CN.md)

This document describes the system as implemented in the repository. Code is
the source of truth; every claim here was verified against it.

## 1. What this project is

An **Agent Runtime / Harness engineering project, demonstrated on an
insurance-analysis domain**. The insurance pipeline (facts → requirements →
risks → gaps → solution → products → report) is the demonstration workload;
the engineering contribution is the execution system around the LLM:

> a reliable, state-driven, eval-gated, observable, resumable,
> bounded-parallel Agent execution system — not a chatbot.

Two entry layers drive the same runtime:

- **Interactive chat** (`runtime/agent/`, `runtime/server.py`): a bounded
  agent loop (`run_agent_turn`) with intent routing and tool calling. This is
  what the React UI exercises.
- **Programmatic long-running projects** (`runtime/harness/`): Planner →
  Task Graph → Harness → specialist agents. This layer is a library driven
  by code/tests (see `tests/runtime/`); it is the part with checkpoints,
  DAG scheduling and A2A coordination.

## 2. The separation that defines the architecture

| Role | Answers | Implemented by |
| --- | --- | --- |
| **Planner** | WHAT should be done | `runtime/planner/` — LLM plan + strict validator |
| **Agent** | WHO / HOW it is performed | `runtime/agents/registry.py` (specialists), `runtime/agents/executor.py` |
| **Skill** | reusable domain capability | `.trae/skills/*` (9 skills, each with contract + evals) |
| **Tool** | executable capability interface | `runtime/agent/tools.py` (agent-facing, schema-validated) |
| **Harness** | WHEN / execution control / reliability | `runtime/harness/harness.py` + `runtime/orchestrator.py` |
| **Eval** | does the result satisfy quality constraints | `runtime/eval_engine.py` (+ `runtime/repair.py`) |
| **Artifact** | durable result / source of truth | `runtime/artifact_registry.py`, `runtime/state/` |
| **Message** | coordination information — never durable truth | `runtime/agents/message_bus.py` |

These are separated **deliberately**:

- The Planner cannot invent capabilities — task types come from a trusted
  registry; untrusted LLM output is validated fail-closed.
- Agents cannot decide parallelism, create tasks, modify the graph, or PASS
  themselves. Only the Harness runs Eval and determines PASS/FAIL.
- Tools do not evaluate in agent mode (`skip_eval=True`); the artifact is
  stored, the Harness evaluates.
- Artifacts are the durable truth; messages coordinate but never replace
  artifacts.

Deep dives: [planner.md](planner.md) · [harness.md](harness.md) ·
[parallel-scheduler.md](parallel-scheduler.md) ·
[dynamic-replanning.md](dynamic-replanning.md) ·
[human-in-the-loop.md](human-in-the-loop.md) · [agents.md](agents.md) ·
[a2a.md](a2a.md) · [eval.md](eval.md) ·
[artifacts-and-provenance.md](artifacts-and-provenance.md) ·
[insurance-domain.md](insurance-domain.md)

## 3. End-to-end flow

```text
USER
 ↓
Intent Routing (agent_decide, first decision of a turn)
 ↓  GENERAL_KNOWLEDGE / GENERAL_GUIDANCE / PRODUCT_LOOKUP → direct answer,
 ↓  no client-intake, no full advisory pipeline
 ↓  CLIENT_ADVISORY → personal planning; TASK_EXECUTION → step on existing data
 ↓
Planner (LLM, bounded retry ≤ 2)          runtime/planner/planner.py
 ↓ strict JSON Task Graph
Graph Validator (10 checks, fail-closed)  runtime/planner/validator.py
 ↓ trusted graph (fields filled from the trusted Task Registry)
Long-running Harness                      runtime/harness/harness.py
 ↓ immutable task graph + project on disk
Scheduler (max_concurrency, default 1)
 ↓ sequential path  |  BSP rounds: runnable set → bounded workers
Specialist Agents                         runtime/agents/
 ↓ tools → artifact candidates (skip_eval)
Scheduler-owned commit (parallel mode)    merge + event replay, graph order
 ↓
Eval (Harness-owned)                      runtime/eval_engine.py
 ↓ PASS → checkpoint, next runnable      FAIL → Repair ≤ 2 → retry → Eval
 ↓ exhausted → NEEDS_REVIEW, downstream BLOCKED
Artifacts + lineage + provenance          runtime/artifact_registry.py
 ↓
Report / user-visible result
```

## 4. Intent routing (verified from `runtime/agent/schemas.py`)

The chat agent classifies every turn through the structured `agent_decide`
decision (enum enforced by JSON Schema):

```text
GENERAL_KNOWLEDGE   what something IS — definitions, differences
GENERAL_GUIDANCE    what to consider / how to choose, in general
CLIENT_ADVISORY     a personal plan/recommendation for the user's own situation
PRODUCT_LOOKUP      a specific product/ID/term
TASK_EXECUTION      execute a specific step on existing data
```

Design intent (from the prompt contract, enforced by tests): general
questions get general answers — they do **not** enter client-intake; product
lookup does not require a complete client profile. Only `CLIENT_ADVISORY`
starts the personal-analysis pipeline, and when facts are insufficient the
agent asks the user (`ask_user`) rather than guessing.

## 5. Execution models

| Mode | Path | Who evaluates |
| --- | --- | --- |
| Chat agent (`run_agent_turn`) | bounded loop, ≤ 12 steps, LLM retry ≤ 2, fail-closed | tools run the deterministic skills (eval inside the stage runner); eval-driven `needs_review` stops the turn |
| Reference (deterministic) | `orchestrator._execute_stage` — the pre-agent runtime | the stage runner itself (eval + repair inside) |
| Specialist agent | `SpecialistAgentExecutor` → `ARTIFACT_READY` | **the Harness** via `_run_eval_and_repair` |

The Eval-ownership boundary is uniform: the executor produces an artifact
candidate and stops; PASS is decided only by the Harness. See
[eval.md](eval.md).

## 6. Phase history (engineering evolution)

| Phase | Delivered | Frozen artifacts |
| --- | --- | --- |
| V2 Steps 0–4 | contracts, core skills, orchestrator, deterministic eval + repair, checkpoints | `contracts/`, `.trae/skills/`, `runtime/orchestrator.py`, ADR-001..007 |
| 2.5 / 2.6 | runtime observability (event stream, SSE), chat-first agent, real LLM mode | `runtime/events.py`, `runtime/event_bus.py`, `runtime/agent/`, `web/` |
| 3 | long-running harness | `runtime/harness/` |
| 4 | planner + registry + validator | `runtime/planner/` |
| 5 | multi-agent: specialist executors, deterministic assignment | `runtime/agents/executor.py`, `registry.py` |
| 6 | A2A: MessageBus, handoffs, communication policy | `message_bus.py`, `handoff.py` |
| 7 | bounded parallel DAG scheduler + housekeeping freeze | `harness.py` (`_run_parallel`), `tests/runtime/test_parallel_*` |
| 8 | Harness-controlled bounded dynamic replanning | `harness.py` (replanning section), `runtime/planner/` (`replan`), `tests/runtime/test_dynamic_replanning.py` |
| 9 | Human-in-the-loop approval gateway | `runtime/approval/`, `harness.py` (approval section), `tests/runtime/test_approval.py` |

Layers froze in order; each phase's regression still runs today
(`max_concurrency=1` executes the Phase 6 sequential path unchanged).

## 7. Repository layout (architectural boundaries)

```text
runtime/       the Agent runtime
  agent/       chat agent loop, LLM provider abstraction, tools, intent
  planner/     planner, trusted task registry, graph schema, validator
  harness/     long-running harness + parallel scheduler
  agents/      specialist registry, executor, message bus, handoff
  state/       CaseState container, store, transition guards
  (root files) orchestrator, eval engine, repair, artifact registry,
               checkpoints, events/event bus, FastAPI server
.trae/skills/  9 insurance Skills — each self-contained (SKILL.md, CONTRACT.md,
               evals, entrypoints); loaded by the orchestrator by declared path
contracts/     canonical JSON Schemas for every artifact type
adapters/      native dialogue format → canonical artifact adapters
knowledge/     RAG engine + shared Evidence Provider (provenance, fail-closed)
catalog/       demo product catalog (versioned, effective-dated, is_demo)
tests/         tests/runtime = pytest suite; other dirs = standalone script
               suites executed by tmp/run_regression.py
evals/         system-level benchmark (33 cases) + golden cases
web/           React/Vite chat UI (SSE stream, developer console, inspector)
docs/          this documentation system + ADRs + dev notes
```

## 8. Current limitations

- Single process, thread-based bounded parallelism; no distributed workers,
  no external queue, no multi-node coordination.
- Parallel scheduling is round-based (BSP): a slow task holds its round's
  next dependents until the round barrier — the tradeoff for deterministic
  graph-order commits.
- Persistence is JSON-on-disk; recovery is process-independent resume from
  disk (simulated crash recovery in tests), not distributed crash recovery.
- Dynamic replanning is bounded and Harness-controlled (V0.1): deterministic
  triggers, immutable graph revisions, validator-gated; agents and messages
  still cannot touch the graph. See [dynamic-replanning.md](dynamic-replanning.md).
- Demo product catalog (`is_demo`, fictional insurers) and a small local
  knowledge corpus — no live insurer data or external insurance databases.
- Known pre-existing test-infra issues: `step3-mutation` suite reports
  INFRA_ERROR (reproduces on a clean tree); the regression runner needs
  `PYTHONIOENCODING=utf-8` on cp936 consoles. See
  [development/testing.md](../development/testing.md).

## 9. What this project is NOT

- Not a distributed Agent platform.
- Not a production insurance recommendation system or a live insurer product
  database.
- Not a fully autonomous, unrestricted Agent — every extension point is
  validated, eval-gated and fail-closed.
- Not a Kubernetes-scale scheduler, not Raft, not a distributed message
  queue.

## 10. Future directions (NOT implemented)

See [roadmap.md](../roadmap.md) — dynamic replanning, durable external
queues, distributed workers, human-in-the-loop approval UI, richer knowledge
sources. All explicitly future work.
