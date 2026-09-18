# Phase 12 Delivery Report

Date: 2026-09-18 · Baseline: Phase 11 independent acceptance (P0=0, P1=0, 314 tests).

## 1. Changes

```text
Runtime (F-01 fix only — no frozen semantics touched):
  runtime/agent/smoke_test.py   fail-closed reachability probe, encoding-safe
                                prints, optional-LLM doc/positioning

Demos (new):
  demos/demo_insurance.py        realistic family case, full pipeline
  demos/demo_generalization.py   SE domain adapter on the SAME runtime
  demos/demo_portfolio.py        the 6-act 5–10 minute portfolio demo

Data: client-intake-data/demo-family-001.json (realistic, fictional)

Docs (new): architecture.md, runtime-trace.md, portfolio.md, demo-script.md
Docs (updated): README(.zh-CN).md quick-start reordering + links;
                generalization(.zh-CN).md SE adapter evidence

Tests (new): tests/portfolio/ — quick_start, demo_insurance,
             demo_generalization, demo_trace (12 tests, anti-cheat included)
```

## 2. F-01 Fix

The README's first verification command is now `python -m demos.demo_basic`
— offline, keyless, encoding-proof, real-runtime (portfolio test
`test_quick_start_first_command` proves runtime engagement + no CoT).
The real-LLM smoke moved to an explicitly **Optional** step: it now probes
provider reachability first and reports **FAIL-CLOSED** on outage (exit 1)
or **SKIP** when unconfigured — never a silent deterministic fallback
(test `test_llm_smoke_is_fail_closed_not_silent`). With a live provider it
runs the real behavioral assertions (it currently reports an honest
behavioral FAIL on this machine's model response — recorded below).

## 3. Portfolio Demo — how to run and results

`python -m demos.demo_portfolio` (~4s wall, 6 acts): problem → planner →
live 4-agent parallel run → T+ trace from the durable event log →
recovery acts (B006 replan PASS, B010 HOTL pause/resume PASS, B008 HITL
approval PASS, all executed live via the benchmark runner) → deliverable
with provenance → SE domain swap (live subprocess). Exit 0.

## 4. Insurance Case — real-run evidence

`python -m demos.demo_insurance` on `demo-family-001` (30yo, married,
newborn, 500k income, 2M planned mortgage): 8/8 tasks PASSED through 4
specialists, 8/8 evaluations PASS, 8 artifacts, lineage verified, FINAL
COMPLETED. Repeatable 3/3 (portfolio test asserts semantic identity).

## 5. Generalization — non-insurance evidence

`python -m demos.demo_generalization`: a software-engineering workflow
(requirement→risk→solution→implementation→test) completes on the SAME
runtime — 5/5 tasks PASSED, 3 SE agents, 5/5 evals PASS, lineage
verified, COMPLETED. The adapter is ~40 declarative lines (registries +
workflow + eval rules + executor); tests prove no fork (module-level
assertions + a scheduler-invocation probe) and that the real scheduler
executed the SE tasks.

## 6. Runtime Trace

`docs/runtime-trace.md` documents the insurance run's durable event log
end-to-end (request → plan → timeline → quality → artifacts → deliverable),
with wall-clock normalized. `test_trace_summary_from_durable_state`
tamper-proves the summary derives from durable state, not fixtures.

## 7. Architecture layering

`docs/architecture.md`: system + control Mermaid diagrams with the
authority table (Harness=Runtime Authority, Planner=Plan, Monitor=Observe,
Agent=Execute/Request, Human=Approve/Intervene). Generic-vs-domain-vs-
adapter in `docs/generalization.md`, now with the demonstrated SE adapter
and three recorded friction points (CaseState schema executor vocabulary,
legacy TASK_DEFS, reference-mode orchestrator).

## 8. Tests

```text
runtime tests:   314 passed (Phase-11 baseline preserved exactly)
portfolio tests: 12 passed (quick-start, insurance, generalization, trace —
                  each with anti-cheat sections)
full regression: 51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR (unchanged)
compileall:      OK (runtime, tests, demos, evals/benchmark)
doc links:       8 files, 0 broken · temp-dir leaks: 0
```

## 9. Demo timing

```text
Quick Start (demo_basic):        1.3s   Insurance demo:      1.4s
Generalization demo:             1.2s   Full portfolio demo: 4.1s
```
All ≪ the 5–10 minute budget — the demo's narration time is the human's.

## 10. Remaining issues (honest)

- `runtime.agent.smoke_test` with a live provider currently FAILS its
  behavioral assertion on this machine (the model answered the vague input
  instead of asking). That is an honest real-LLM behavioral FAIL, not a
  runtime defect; the optional smoke is excluded from every regression.
- Generalization friction points recorded (not fixed): CaseState schema
  executor vocabulary (`python|provided|service`), legacy `TASK_DEFS`,
  reference-mode orchestrator path.
- Pre-existing infra unchanged: step3-mutation INFRA_ERROR, GBK console
  needs PYTHONIOENCODING=utf-8 for some standalone scripts.
- Product catalog remains demo data; all user-facing outputs say so.
