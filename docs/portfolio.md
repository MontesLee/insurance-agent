# Portfolio — what this project proves

> For a hiring manager with 2–3 minutes. Deep-dives:
> [architecture.md](architecture.md) · [benchmark-report.md](benchmark-report.md) ·
> [runtime-trace.md](runtime-trace.md)

## One-line summary

A long-running multi-agent runtime that plans, executes, evaluates,
repairs, replans and supervises agent workflows — with insurance as the
first domain adapter and a software-engineering adapter proving the
runtime is generic.

## The problem with "Prompt → LLM → Answer"

Real agent work is long-running, multi-specialist and failure-prone. A
single LLM call has no answer for: dependencies between steps, specialists
that must not grade themselves, failures that must fail closed, work that
must survive a crash, high-impact changes that need a human, and humans
who must supervise without becoming a bottleneck in the workflow. This
project builds exactly that missing execution layer.

## Engineering contributions (all frozen, all tested)

| # | Capability | Where |
| --- | --- | --- |
| 1 | State-driven Agent Runtime (task lifecycle, dependencies) | `runtime/harness` |
| 2 | Planner + validated DAG graphs (10-check, fail-closed) | `runtime/planner` |
| 3 | Multi-agent execution (4 specialists, deterministic assignment) | `runtime/agents` |
| 4 | A2A communication (persistent, policy-enforced MessageBus) | `runtime/agents` |
| 5 | Bounded parallel scheduler (isolated workers, deterministic commits) | Phase 7 |
| 6 | Dynamic replanning (immutable revisions, diff, budget) | Phase 8 |
| 7 | Eval / Repair (harness-owned, bounded, no self-PASS) | `runtime/eval_engine` |
| 8 | Artifact provenance (lineage, fingerprints, human-input provenance) | `runtime/artifact_registry` |
| 9 | Checkpoint / crash recovery (cross-process, idempotent commands) | `runtime/checkpoint` |
| 10 | HITL approval gateway (fail-closed state machine) | `runtime/approval` |
| 11 | HOTL control plane (deterministic monitor + intervention policy) | `runtime/control` |
| 12 | Benchmark + red-team (11 cases, 18 injections, false-pass = 0) | `evals/benchmark` |

## Agent Developer competencies demonstrated

Runtime design · tool/agent boundary design · structured output validation ·
eval-gated execution · failure handling (fail-closed everywhere) · state
management · observability (durable events, SSE) · multi-agent · A2A ·
long-running tasks · crash recovery · parallel scheduling.

## Agent PM competencies demonstrated

Problem definition (advisory as a workflow, not a chat) · workflow
decomposition (9-stage pipeline) · agent/skill boundary design (WHO vs
capability) · product requirements (eval rules as acceptance criteria) ·
failure-mode design (18-row injection matrix) · HITL/HOTL design (decision
gates vs supervision) · trade-off records (7 ADRs) · demo/productization
(one-command portfolio demo, benchmark reports) — defining how agents
deliver an auditable piece of work, not just prompts.

## Evidence

```text
pytest tests/runtime -q            → 314 passed
python -m evals.benchmark.runner   → 11/11 cases, hard gates all 0
python -m demos.demo_portfolio     → the 6-act live demo
```

Honest limits: demo product catalog, single-process scheduler, real-LLM
smoke depends on external API (fails closed), research/portfolio prototype
— not production insurance advice.
