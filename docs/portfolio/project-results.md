# Project Results — verified numbers

> Every number below was re-verified from the live repository at tag
> v0.1.0 on 2026-09-19 (commands included so anyone can reproduce).

## Test & benchmark evidence

| Metric | Value | Reproduce |
| --- | --- | --- |
| Runtime + portfolio tests | **326 passed** (314 runtime + 12 portfolio) | `pytest tests/runtime tests/portfolio -q` |
| Deterministic benchmark | **11/11 cases PASS**, hard gates all 0 | `python -m evals.benchmark.runner` |
| Fault-injection matrix | **18/18 PASS** | `pytest tests/runtime/test_failure_injection.py -q` |
| False-pass count | **0** (adversarial suite) | `python tests/runtime/test_false_pass.py` |
| Full regression runner | 51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR | `PYTHONIOENCODING=utf-8 python tmp/run_regression.py` |
| Determinism | 3× runs identical (statuses, artifact ids, verdicts) | benchmark suite T20 |
| Parallel consistency | concurrency 1 vs 2 semantically identical (incl. artifact ids) | benchmark suite T9 |

Hard gates (all zero): false_pass · duplicate_execution ·
invalid_transition · unauthorized_command · artifact_lineage_errors ·
provenance_errors.

## Runtime capabilities demonstrated (each test-backed)

Bounded-parallel DAG scheduling with worker isolation · dynamic
replanning (immutable revisions, diffs, budget, no-change guard) ·
harness-owned eval with repair ≤ 2 · checkpoint + cross-process crash
recovery (incl. mid-command) · HITL approval gateway (fail-closed) ·
HOTL control plane (deterministic monitor, audited idempotent commands,
safe-barrier pause/resume) · A2A message bus with policy + ACK-after-PASS
· artifact lineage + provenance (fingerprints, human-input provenance) ·
4-agent E2E (sequential and parallel).

## Domains

- **Insurance** (first adapter): 9 skills, 4 specialists, full pipeline →
  report; realistic fictional case `demo-family-001`.
  `python -m demos.demo_insurance`
- **Software engineering** (generalization proof): 5-task workflow, 3 SE
  agents, 5/5 evals, lineage verified, on the SAME runtime (no fork).
  `python -m demos.demo_generalization`

## Demos (one command each, offline, deterministic)

`demo_basic` · `demo_parallel` · `demo_replan` · `demo_hitl` ·
`demo_hotl` · `demo_four_agent` · `demo_insurance` ·
`demo_generalization` · `demo_portfolio` (the 6-act tour, ~4s).

## Honesty notes

The regression runner's 1 INFRA_ERROR (step3-mutation + GBK console) is
pre-existing, reproduced on a clean tree, and excluded from acceptance.
The product catalog is explicitly demo data. The real-LLM smoke depends
on external API availability and fails closed on outage — SKIP is never
reported as PASS.
