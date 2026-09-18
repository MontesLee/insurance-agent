# Generalization Audit — Insurance is a Domain Adapter, not the Runtime

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](generalization.zh-CN.md)

Verified structurally by `tests/runtime/test_generalization.py`: every
module in the generic column below is domain-free at code level (the only
scanned hits are comments/docstrings, plus the documented legacy
`TASK_DEFS` mapping inside `harness.py` kept frozen for Phase-3
compatibility).

## Generic Runtime (domain-free, reusable as-is)

```text
Generic Runtime
├── Planner engine          runtime/planner/{planner,validator,schemas}.py
│     (WHAT: untrusted LLM output → trusted validated graph; retry ≤ 2,
│      fail-closed — knows nothing about which task types exist)
├── Harness + Scheduler     runtime/harness/harness.py
│     (WHEN/CONTROL: task lifecycle, BSP parallel rounds, worker
│      isolation, scheduler-owned commit, recovery)
├── Approval gateway        runtime/approval/ (HITL: fail-closed state
│     machine, deterministic policy, actor allowlist)
├── Control plane           runtime/control/ (HOTL: deterministic monitor,
│     risk levels, intervention policy, audited idempotent commands)
├── MessageBus protocol     runtime/agents/message_bus.py (coordination
│     only — the transport is generic; the communication POLICY table is
│     domain config inside the agents registry)
├── State machine           runtime/state/ (CaseState, guards, store)
├── Checkpoint/resume       runtime/checkpoint.py
├── Artifact lineage        runtime/artifact_registry.py
├── Eval engine mechanics   runtime/eval_engine.py (check families driven
│     entirely by resources/config/eval.rules.json — the rules FILE is
│     domain config; the engine is generic)
├── Replanning              immutable graph revisions, diff, budget,
│     no-change guard (in the harness)
└── Observability           runtime/events.py, event_bus.py, trace.py
```

## Domain Layer (insurance — the first adapter)

```text
Domain Layer
├── Insurance Skills        .trae/skills/* (9 self-contained skills with
│                           contracts + evals)
├── Insurance Contracts    contracts/*.schema.json
├── Insurance Catalog      catalog/product-catalog.v0.1.json (is_demo,
│                           versioned, effective-dated)
├── Insurance Knowledge    knowledge/ (RAG engine + Evidence Provider,
│                           local demo corpus)
├── Insurance Workflow     runtime/insurance-analysis.yaml
├── Task catalog (config)  runtime/planner/registry.py — the trusted
│                           WHAT-list; swap this to change domains
├── Agent catalog (config) runtime/agents/registry.py — specialists +
│                           tool scopes + communication policy
├── Tool surface           runtime/agent/tools.py
└── Eval rules (config)    runtime/resources/config/eval.rules.json
```

## What swapping the domain means

Replacing insurance with another domain (claims, loan advisory, medical
triage…) = replacing the Domain Layer: task registry, agent registry,
workflow YAML, skills, contracts, catalog, knowledge, eval rules. The
Generic Runtime — scheduler, replanning, approval, control plane,
checkpoints, lineage, message protocol — is untouched. The Phase-11
thought-experiment test instantiates the monitor/policy on synthetic
non-insurance project shapes to prove the point.

Known coupling kept frozen (documented, not refactored — Phase 11 changes
no runtime): the legacy `TASK_DEFS`/`TASK_CHAIN` fallback mapping in
`harness.py` (used only when a project is created without a task graph),
and the workflow-loaded `orchestrator.py` which drives the insurance
pipeline stages by declared path.


## Demonstrated, not just claimed: the SE domain adapter (Phase 12)

`demos/demo_generalization.py` runs a SOFTWARE-ENGINEERING workflow
(requirement → risk → solution → implementation plan → test plan) on the
SAME Planner / Harness / Scheduler / Eval / Artifact stack — zero runtime
modules copied or forked. The adapter is ~40 declarative lines:

```text
Domain Adapter (per domain, no runtime changes)
├── task-type catalog    planner registry entries (the WHAT)
├── agent definitions    agents registry entries (the WHO)
├── workflow definition  stages + contracts (the pipeline shape)
├── eval rules           required fields per artifact type
└── domain executors     the HOW (skills/tools per specialist)
```

Verified in that run: same graph validator, same bounded-parallel
scheduler, same harness-owned eval (5/5 PASS), same artifact registry with
verified lineage, same checkpoints, same run summary — `COMPLETED`.

### Generalization friction points (recorded, not fixed)

1. **CaseState schema vocabulary** — `stages/*/executor` is constrained to
   the insurance-era set (`python|provided|service`) and `produces` to a
   single string. Adapters must comply (the SE adapter labels its stages
   `python`); a future schema relaxation would remove the friction.
2. **Legacy `TASK_DEFS` mapping in `harness.py`** — a Phase-3 fallback kept
   frozen; inactive for any project created from a task graph.
3. **`orchestrator.py` drives the insurance pipeline stages by declared
   path** — used only in reference mode; agent-mode projects never touch it.
