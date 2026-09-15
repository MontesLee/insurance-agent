> 🌐 **Language:** 🇨🇳 [中文版](ADR-002-orchestrator-over-pipeline.zh-CN.md) · 🇺🇸 English

# ADR-002 · Orchestrator instead of hard-coded pipeline

## Context
With 8 Skills in place, something must decide "who runs next, can it run, was the result correct,
and what to do on failure." The most direct approach: write 9 sequential calls in one script.

## Decision
Build an Orchestrator (**`runtime/orchestrator.py`**) that contains **zero insurance business
judgment**, driven by the **declarative** `runtime/insurance-analysis.yaml` (stage order /
production-consumption / executors / gates all externalized).

## Alternatives
- Hard-coded sequential calls: adding/reordering stages means editing code; sequencing logic
  scatters.
- General-purpose workflow engines (Airflow / Temporal class): too heavy at this stage; violates
  "no complex infrastructure".
- Let Skills find the next Skill themselves: scatters orchestration logic across 8 places.

## Why
Orchestration is a **cross-domain** concern, unrelated to insurance, so it must be decoupled from
business Skills. The declarative YAML makes "what the chain looks like" **readable** (instead of
inferred from code), and lets tests directly assert "execution order == declared order"
(self-eval SE-2).

## Trade-offs
- YAML and code can become two sources of truth (e.g. the `index` field) — eliminated by "list
  order is the index; never hand-written".
- Declarative expressiveness is limited; complex conditional branches (different chains per case
  type) need extra machinery — currently covered by gates + repair.
- Debugging requires reading YAML and Python together; slightly higher onboarding cost.
