# Phase 11 Pre-Implementation Audit

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](phase11-audit.zh-CN.md)

Date: 2026-09-18 · Baseline commit: `c294a33` (Phase 10 frozen, pushed).

## 1. Runtime architecture (as found)

All four frozen capabilities present and tested:

- **Phase 7** — bounded parallel DAG scheduler (`_run_parallel`, BSP rounds,
  worker isolation, scheduler-owned commit); `max_concurrency=1` keeps the
  sequential path.
- **Phase 8** — dynamic replanning (deterministic triggers, immutable graph
  revisions, diff, budget, no-change guard).
- **Phase 9** — HITL approval gateway (`runtime/approval/`, fail-closed
  state machine, Harness-owned resume).
- **Phase 10** — HOTL control plane (`runtime/control/`, deterministic
  monitor + intervention policy, audited idempotent commands).

## 2. Current test counts

`pytest tests/runtime -q` → **293 passed** (248 pre-Phase-9 baseline grew
through Phases 9/10). Full regression runner: **51 PASS / 0 FAIL /
1 pre-existing INFRA_ERROR** (step3-mutation; reproduced on a clean tree in
the Phase-7 housekeeping session; GBK console issue on cp936 without
`PYTHONIOENCODING=utf-8`).

## 3. E2E capability

Parallel and sequential 4-agent E2Es exist (`test_parallel_4_agent_e2e`,
`test_true_4_agent_e2e`) with real executors/engines; a replanning E2E and
an approval E2E exist (Phase 8/9 suites). No *unified* benchmark harness
existed before Phase 11 — that is this phase's deliverable.

## 4. Demo capability

`demo.py demo-a/demo-b` (deterministic pipeline, pre-agent era) and the
web chat UI. No per-phase demos; no status-only trace summary. Phase 11
adds `demos/` with six one-command runners.

## 5. Benchmark capability

`evals/agent-benchmark/` (33-case agent benchmark + golden cases, skill
mutation language) predates the multi-agent runtime — it exercises the
deterministic pipeline, not Planner/Harness/Replan/HITL/HOTL. Phase 11
adds `evals/benchmark/` for the runtime itself.

## 6. Failure injection

Scattered across per-phase test suites (repair, approval, crash, actor
authority). Phase 11 consolidates a declarative matrix
(`failure-injection/matrix.json`, 18 rows) with machine-verified
expectations.

## 7. Trace capability

Durable per-project `events.jsonl`, CaseState trace, checkpoints,
approvals/commands/alerts JSONL — all present. No human-readable run
summary; Phase 11 adds `run_summary()` derived purely from durable state.

## 8. README readiness

Bilingual README + full doc suite exist with quick start, but no
benchmark/demo instructions and the first screen under-sells the runtime
(vs the chatbot). Phase 11 refreshes the first screen and adds
run-it-yourself sections.

## 9. Insurance coupling points

Domain vocabulary lives in: `.trae/skills/*`, `contracts/`, `catalog/`,
`knowledge/`, `runtime/insurance-analysis.yaml`,
`runtime/planner/registry.py` (task catalog), `runtime/agents/registry.py`
(specialists), `runtime/agent/tools.py`, plus the legacy `TASK_DEFS`
mapping inside `harness.py` (kept frozen, documented). The generic
modules (control, approval, state, checkpoint, artifact registry, event
bus, planner engine/validator) are domain-free at code level — verified
structurally by `test_generalization.py`.

## 10. Reusable generic runtime

Ready to reuse outside insurance as-is: scheduler, state machine,
checkpoints, artifact lineage, eval-engine mechanics (rule-config
driven), message bus protocol, approval gateway, control plane,
observability. Swapping the domain = replacing the registry/workflow/
skills/contracts/catalog/knowledge pack. See `generalization.md`.
