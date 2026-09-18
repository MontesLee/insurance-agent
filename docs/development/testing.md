# Testing Strategy

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](testing.zh-CN.md)

This project treats tests as the evidence that the architecture's claims
are true (fail-closed eval, no self-pass, dependency barriers, deterministic
commits, recovery). Numbers below are a snapshot — every section gives the
command that regenerates them.

## 1. Commands

```bash
pytest tests/runtime -q                             # the pytest suite (current: 227 passed)
PYTHONIOENCODING=utf-8 python tmp/run_regression.py # all standalone suites (52)
python evals/agent-benchmark/run_agent_benchmark.py # 33-case benchmark + safety gates
python evals/agent-benchmark/run_golden_cases.py    # golden-case regression
cd web && npm test                                  # React UI unit tests (vitest)
```

## 2. Two layers of evaluation discipline

| Layer | Location | Question answered |
| --- | --- | --- |
| Skill-level evals | `.trae/skills/<skill>/evals/` | does this skill behave per its contract? |
| System-level evals | `evals/` | how does the assembled agent system perform end-to-end? |

Both apply the same discipline: machine-checkable assertions only; FAIL →
repair → re-run; negative self-probes (a suite that can't fail proves
nothing).

## 3. Test categories (`tests/runtime/`, pytest + dual script mode)

Every suite runs both under pytest and as a plain script (`python
tests/runtime/test_*.py`) via a shared `Checks` accumulator — the repo's
convention predating the pytest harness.

| Category | Suites (examples) |
| --- | --- |
| Unit / contract | `test_agent_tools`, `test_agent_model`, `test_agent_config`, `test_planner` |
| Harness & state machine | `test_harness`, `test_events`, `test_event_bus` |
| Agent executor | `test_specialist_agent_executor`, `test_agent_loop`, `test_agent_intent` |
| **Eval boundary** | `test_eval_boundary` (tool does not evaluate; harness does; bounded repair; no self-pass) |
| A2A / message-driven | `test_agent_communication`, `test_message_handoff`, `test_message_driven_scheduler` |
| Recovery | `test_cross_process_recovery` (new process resumes from disk) |
| **Parallel scheduler** | `test_parallel_scheduler` (T1–T21 + no-worker-self-pass + probe-teeth) |
| **Parallel 4-agent E2E** | `test_parallel_4_agent_e2e` (blocking-probe overlap proof) |
| Sequential 4-agent E2E | `test_true_4_agent_e2e` |
| Web/UI server | `test_server`, `test_sse`, `test_concurrency` |

The parallel tests prove their central claims with **synchronization, not
timing**: a blocking probe releases only when two tasks are simultaneously
inside execution (and a dedicated "probe teeth" test proves the probe
rejects sequential interleaving — the test can fail when the
implementation is wrong).

## 4. Standalone script suites (`tmp/run_regression.py`)

`tests/{contracts,e2e,eval,evidence,structure,workflow}` contain
script-mode suites (module-level `sys.exit` — intentionally NOT
pytest-collectible at the repo root). The runner executes all 52 and
reports `PASS / FAIL / INFRA_ERROR`. Current snapshot: **51 PASS, 0 FAIL,
1 INFRA_ERROR** (pre-existing, below).

## 5. Benchmark & golden cases

`evals/agent-benchmark/` runs 33 cases end-to-end through agent mode with
safety hard gates (no unsupported claims, bounded repairs) plus 9 golden
cases with before/after gating. Results land in `results.json` /
`golden_results.md`. Note: running the benchmark rewrites the
`generated_at` timestamp in `results.json` — restore it
(`git checkout -- evals/agent-benchmark/results.json`) if you don't want
that churn in your diff.

## 6. Known infrastructure issues (pre-existing, verified on a clean tree)

- `step3-mutation` reports INFRA_ERROR in the regression runner (its own
  traceback; unrelated to current runtime code — reproduced with the
  working tree fully stashed).
- cp936 consoles: the runner and some suites print Unicode that GBK cannot
  encode — set `PYTHONIOENCODING=utf-8`.
- Do not run bare `pytest -q` from the repo root: the script-mode suites
  raise `SystemExit` at import and abort collection. Use the commands in
  §1.

## 7. Conventions for new runtime tests

Follow the house style (see any suite header): dual-mode sections with
`Checks`, temp harness roots under `tmp/`, FakeLLMProvider scripts for
deterministic agent behavior, and `cleanup()` of temp dirs in `finally`.
Tests must fail when the property they claim is broken — avoid
`try/except: pass`, avoid sleep-based concurrency proofs.
