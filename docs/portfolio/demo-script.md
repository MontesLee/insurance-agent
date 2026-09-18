# Demo Script — 5-minute and 10-minute interview versions

> Run `python -m demos.demo_portfolio` and narrate. Everything on screen
> is real runtime output (durable events/artifacts/checkpoints). Never
> show prompts or chain-of-thought; if asked "is this real?", re-run it
> live — it is deterministic and repeatable.

## 5-minute version

### 0:00–0:30 — One-sentence framing

> "I didn't build an insurance chatbot — I built a long-running
> multi-agent runtime that plans, executes, evaluates, repairs, replans
> and supervises agent workflows. Insurance is just the first domain."

### 0:30–1:30 — Architecture (Act 2 + control diagram)

Walk the task graph, then the authority table: Planner = WHAT,
Harness = WHEN (sole state authority), Agents = HOW (never PASS),
Eval = QUALITY (harness-owned), Artifacts = TRUTH, Human = above the DAG.

### 1:30–3:00 — Live insurance case (Act 3)

The realistic family case runs: 4 specialists execute, risk ∥ knowledge
branches run concurrently. Point at the agents and the parallelism.

### 3:00–4:00 — Runtime trace + deliverable (Acts 4 & 6)

Walk the T+ timeline (from the durable event log), then the deliverable:
coverage gaps, catalog-backed candidates, 5 sourced evidence items,
lineage verified end-to-end.

### 4:00–4:30 — Recovery + human control (Act 5)

Pick ONE failure story (replan is the strongest): task fails →
downstream blocked → controlled replan v1→v2 → completed work preserved.
Mention in one breath that HITL approval and HOTL supervisor pause/resume
are also demonstrated.

### 4:30–5:00 — Domain swap (Bonus)

The SE workflow completes on the same runtime. Close:
> "Insurance is just the first domain adapter."

## 10-minute version

Same spine, adding at the marked points:

- **1:30** add the core contrast: `Prompt → LLM → Answer` vs this
  runtime's pipeline; why long-running work needs the second shape.
- **2:30** open the CaseState dir of the live project: events.jsonl,
  checkpoints.jsonl, artifacts/ — "everything you saw is durable; I can
  kill the process and resume."
- **4:00** fault injection (pick 2): empty knowledge → no fabricated
  evidence, fail closed; invalid product id → catalog invariant FAIL →
  repair exhaustion → NEEDS_REVIEW.
- **5:00** eval & provenance: show one eval record's checks; explain
  false-pass adversarial testing (count 0) and tamper testing.
- **6:00** crash recovery: pause command persisted → "crash" → resume
  applies it exactly once (idempotent).
- **7:00** HITL vs HOTL side by side (approval gate vs supervisor).
- **8:30** benchmark: `python -m evals.benchmark.runner` — 11/11, hard
  gates 0; explain what a hard gate is.
- **9:30** takeaway one-liner:
> "The engineering contribution is the execution layer around the LLM —
> validated planning, agents that never grade themselves, fail-closed
> failures, humans above the DAG — and it's all provable
> deterministically."

## Rules for yourself

Status-only narration (STATUS / TASK / AGENT / ARTIFACT / EVAL /
REVISION / HUMAN CONTROL / FINAL). All numbers you say come from the
screen. Never claim production readiness — "validated portfolio
prototype" is the honest, stronger framing.
