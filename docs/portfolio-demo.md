# Portfolio Demo Script (5–10 minutes)

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](portfolio-demo.zh-CN.md)

Everything below is real runtime output — every status line comes from
durable events/artifacts/checkpoints produced by the actual harness. No
fake activity, no scripted "AI thoughts".

## Setup (one terminal, ~30s)

```bash
python -m demos.demo_four_agent        # the golden run: 4 agents, parallel, report
```

## Act 1 — the happy path (2 min)

Run `python -m demos.demo_basic`. Narrate the separation of concerns as
the transcript scrolls:

1. **Planner = WHAT** — a validated task graph (10-check validator).
2. **Harness = WHEN** — task lifecycle, dependency barriers, checkpoints.
3. **Agents = HOW** — specialists with scoped tools; they never PASS
   themselves.
4. **Eval = QUALITY** — every artifact gated; repair ≤ 2; artifacts =
   durable truth with lineage.
Point at the RUN SUMMARY: tasks, agents, artifacts, evaluations, risk
level, final status.

## Act 2 — failure is honest (2 min)

`python -m demos.demo_replan`. The solution task fails (the agent refuses
to fabricate). Watch: agent_failed → downstream BLOCKED → deterministic
replan trigger → Planner → validator → graph v2 → diff → accepted →
report completes. Say the sentence that defines the project:

> Nothing faked a success. The failure was preserved, the graph was
> revised under the same validation, and completed work was never re-run.

## Act 3 — humans, two different ways (3 min)

- `python -m demos.demo_hitl` — a high-impact replan pauses in
  WAITING_HUMAN; approve; the Harness (only the Harness) resumes.
  **Human-in-the-loop: a decision gate.**
- `python -m demos.demo_hotl` — the runtime hits trouble, the monitor
  raises the risk, the policy PAUSES at a safe barrier; resume.
  **Human-on-the-loop: a supervisor above the DAG, not a node in it.**

## Act 4 — parallel, provably safe (1 min)

`python -m demos.demo_parallel`. Independent branches run concurrently;
the scheduler is the only writer; artifact ids stay sequential and
deterministic. Mention: same result at max_concurrency=1 (verified by the
benchmark, B007).

## Evidence pack (leave these running or printed)

```bash
python -m evals.benchmark.runner          # 11/11 cases, hard gates all 0
pytest tests/runtime -q                   # 300+ tests
```

`docs/benchmark-report.md` — failure injection (18 scenarios), false-pass
count 0, determinism (3× identical), crash recovery. The interview
one-liner:

> "I built the execution engineering around the LLM: planning is
> validated, agents never grade themselves, failures fail closed,
> humans supervise from outside the DAG — and I can prove all of it
> deterministically."
