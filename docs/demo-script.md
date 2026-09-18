# Demo Script — 5–10 minute interview walkthrough

> Run `python -m demos.demo_portfolio` and narrate. Everything on screen is
> real runtime output. Timing marks are guidance, not hard gates.

## 0:00–0:45 — What problem? (Act 1)

Show the family case. Say: *"This is not a chatbot demo — it's a
long-running advisory task: multiple specialists, real artifacts,
evaluation, and a human who supervises without blocking the work."*
**Proves:** problem framing; why one LLM call is not enough.

## 0:45–2:00 — Architecture (Act 2 + the control diagram)

Walk the task graph on screen, then sketch the control architecture
(`docs/architecture.md`): Planner = WHAT, Agents = HOW, Harness = WHEN,
Eval = QUALITY, Artifacts = TRUTH, Human = above the DAG.
**Proves:** separation of concerns; who is allowed to do what.

## 2:00–4:00 — Live insurance case (Act 3)

The four specialists execute; parallel branches (risk ∥ knowledge) run
concurrently. Point at agents + concurrency.
**Proves:** multi-agent execution on the real scheduler.

## 4:00–5:30 — Collaboration & deliverable (Act 4 + 6)

Walk the T+ timeline (it comes from the durable event log), then the
deliverable: gaps, catalog-backed candidates, 5 sourced evidence items,
lineage verified end-to-end.
**Proves:** observability, artifact provenance, eval-gated quality.

## 5:30–7:00 — Recovery under failure (Act 5)

Replanning: knowledge_search fails → downstream blocked → v1→v2 →
completed work preserved. HOTL: risk rises → safe-barrier PAUSE → human
RESUME. HITL: high-impact replan WAITS for approval.
**Proves:** fail-closed behavior, controlled replanning, HITL vs HOTL
as distinct human roles.

## 7:00–8:30 — Same runtime, different domain (Bonus)

Run `python -m demos.demo_generalization` (or let the portfolio demo's
bonus section show it): a software-engineering workflow completes on the
identical runtime — only the declarative domain catalog changed.
**Proves:** generalization demonstrated, not claimed.

## 8:30–10:00 — Engineering takeaway

The one-liner: *"I built the execution engineering around the LLM —
planning is validated, agents never grade themselves, failures fail
closed, humans supervise from outside the DAG, and all of it is provable
deterministically: 314 tests, 11 benchmark cases, false-pass count 0."*

## Rules for yourself

Never show prompts or chain-of-thought; if asked "is this real?", point at
`events.jsonl`/checkpoints in any demo project dir and re-run the demo
live — it is deterministic and repeatable.
