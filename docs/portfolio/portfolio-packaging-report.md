# Portfolio Packaging Report (V0.1)

Date: 2026-09-19 · Base: tag v0.1.0 (95d6b41).

## Portfolio Positioning

**Long-running Multi-Agent Runtime** — plans, executes, evaluates,
repairs, replans and supervises agent workflows. Insurance is the first
domain adapter; software engineering is the second, demonstrated on the
same frozen runtime. The core narrative is the execution layer around the
LLM (validated planning, no self-grading, fail-closed failures, humans
above the DAG), never "an insurance chatbot".

## Agent Developer Positioning

`agent-developer.md`: 7 capability sections (Planner / Harness /
Multi-Agent / Reliability / Runtime control / Runtime evaluation /
Generalization), each mapping claims to specific test files and tamper
evidence. Key proof points: sole-writer deterministic commits, no
self-PASS (three layers + tests), safe-barrier pause proven with an
in-flight parallel run, benchmark anti-cheat via instrumentation +
6 tamper probes.

## Agent PM Positioning

`agent-pm.md`: problem definition (advisory as workflow, not Q&A), skill
boundary table (9 skills × question × artifact), agent boundary
rationale (tool-scope enforcement, deterministic assignment as
governance), HITL vs HOTL as two product primitives, evaluation as
machine-checkable acceptance criteria, 18-row failure-mode matrix as
requirements-writing for probabilistic systems, documented trade-offs.

## README

**PASS** — first screen: one-line runtime description, "why not just an
LLM call" contrast, 5-minute demo command, deterministic Quick Start,
benchmark, generalization, contribution summary, honest limitations.
Phase-by-phase development narrative moved out of the value path into
the history table + docs.

## 5-minute Demo

**PASS** — `python -m demos.demo_portfolio` (6 acts, ~4s wall); scripted
5- and 10-minute narration in `demo-script.md` with per-act "what this
proves".

## Architecture

**PASS** — mermaid system + control diagrams (`../architecture.md`), the
whiteboard version + 12 follow-up answers (`architecture-interview.md`),
authority table, and `design-decisions.md` with 13 Problem/Decision/
Reason/Trade-off/Limitation records.

## Interview Q&A

**30 questions** (10 architecture · 8 agent engineering · 6
evaluation/reliability · 3 HITL-HOTL · 3 generalization) + the 12
architecture follow-ups — each answer 30–60s, conclusion-first.

## Resume Bullets

**4 versions** — English/Chinese × Agent Developer/Agent PM, 3 bullets
each, every number repo-verified (326 tests, 11/11 benchmark, 18/18
injections, false-pass 0, two domains). No fabricated metrics.

## Generalization Evidence

Same runtime, second domain: `demos/demo_generalization.py` (5/5 tasks,
5/5 evals, lineage verified, COMPLETED) + `tests/portfolio/
test_demo_generalization.py` (no-fork structural assertions + a
real-scheduler invocation probe). Friction points documented honestly in
`../generalization.md`.

## Evidence Integrity

**PASS** — all numbers re-verified live during packaging (326 tests,
11/11 benchmark, false-pass 0, 18 injection rows). Pre-existing infra
error labelled and excluded. Demo catalog disclaimers present. LLM smoke
SKIP/FAIL-CLOSED never reported as PASS.

## Runtime Changes

**NONE** — packaging only: docs under `docs/portfolio/`, README rewrite.
Frozen Phase 7–12 semantics untouched (314 runtime tests identical).

## Tests

```text
pytest tests/runtime tests/portfolio -q → 326 passed
python -m evals.benchmark.runner        → 11/11, hard gates all 0
compileall                              → OK
doc links                               → 0 broken
```

## Remaining Issues

- Real-LLM smoke honestly FAILs a behavioral assertion on the current
  model response (recorded; optional, excluded from regressions).
- Known generalization friction points (CaseState schema vocabulary,
  legacy TASK_DEFS, reference-mode orchestrator path) — documented, not
  fixed, per freeze discipline.
- No human-approval UI / external notification channel (persisted
  records + API exist; adapters are future work).

## Final Recommendation

**PORTFOLIO READY**
