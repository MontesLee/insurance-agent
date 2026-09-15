# 5-Minute Demo Script

A walkthrough you can run live in an interview. Times are approximate; the point is the narrative,
not the clock.

## 0:00 – 0:30 — The one-liner

> "This project is not about showing a great insurance product recommendation.
> It's about answering one question: **when an agent makes a mistake, how do we make sure it
> doesn't keep talking with confidence?**"

Put the first screen of `README.md` on screen: the one-sentence positioning + core capabilities list.

## 0:30 – 1:30 — Architecture

Walk the diagram in `docs/architecture/portfolio-architecture.svg`:

```
CaseState → Orchestrator → Skills → Artifacts → Eval → Repair → Checkpoint
```

Emphasize the **Reliability Layer** box. The engineering contribution is not any single skill — it
is the *runtime contract* around them: state, artifacts, deterministic eval, bounded repair,
provenance, checkpoint, trace.

## 1:30 – 2:30 — Demo A (success)

```bash
python demo.py demo-a
```

Show a single-medical-need case completing: 8 stages all `PASS`, checkpoints saved, final report
with `is_demo = true`, `catalog_checked = true`, `unverified_products = []`.

Say: *"Every claim in that report is traceable back to a candidate, a solution, a gap, a risk, a
requirement, and ultimately to evidence with `document_id` + `chunk_id`."*

## 2:30 – 3:30 — Demo B (safe failure)

```bash
python demo.py demo-b
```

Seed an **empty knowledge base**. Watch:

```
Eval FAIL → Repair → Eval FAIL → Repair → CASE_NEEDS_REVIEW
```

Say: *"The agent could not find evidence, so it stopped — no product, no fabricated recommendation."*

## 3:30 – 4:15 — Show the trace

Open `tmp/demo/bm-noev-001/.../trace.jsonl` (or the rendered `trace.md`):

```
CASE_STARTED
SKILL_COMPLETED  coverage-gap-analysis   PASS
SKILL_COMPLETED  solution                PASS
TASK_FAILED       product-candidate-provider  EVAL-006
REPAIR_STARTED    product-candidate-provider
TASK_FAILED       product-candidate-provider  EVAL-007
REPAIR_STARTED    product-candidate-provider
TASK_FAILED       product-candidate-provider  EVAL-008
CASE_NEEDS_REVIEW repair_exhausted
```

Point out: the causal chain is readable from the events alone — no log archaeology required.

## 4:15 – 5:00 — The benchmark, and the honest boundary

Show the numbers (real, from `tmp/run_regression.py` and the benchmark):

```
30/30 regression   ·   71/71 full-agent E2E   ·   33 benchmark cases   ·   9/9 golden
false-pass = 0
```

Then **volunteer the boundary**:

> "One thing I keep deliberately honest: the current portfolio validates the Agent Runtime from
> **Structured Client State** onward. Raw natural-language → Client State intake is **not** yet part
> of the executed boundary, so I do **not** present this as a full conversational agent. The
> engineering story is runtime reliability, not NLP intake."

Hand over `docs/interview/stories.md` and `docs/interview/interview-guide.md` for follow-ups.
