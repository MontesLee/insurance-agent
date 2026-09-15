> 🌐 **Language:** 🇨🇳 [中文版](ADR-001-skill-based-architecture.zh-CN.md) · 🇺🇸 English

# ADR-001 · Skill-based architecture

## Context
The insurance-advisor task decomposes naturally into judgment layers: client facts, requirements,
risks, coverage gaps, solution strategies, evidence, product candidates, recommendations, and the
report. The naive approach — one big Prompt / one big function doing everything in sequence — means
any change to one layer shakes the whole chain.

## Decision
Each layer becomes an **independent Specialist Skill** declaring: which Canonical Artifacts it
consumes, exactly one Canonical Artifact it produces, and which contract it follows.
Skills **never call each other directly**; they collaborate only through Artifacts.

## Alternatives
- Monolithic Prompt (generate all conclusions at once): no per-layer validation; one hallucination
  contaminates the whole chain.
- Monolithic Python function: testable but not evolvable; changing one layer means touching the
  whole file.
- Chained Skills calling each other (A does `import B`): burns the dependency into code.

## Why
Layering lets the correctness of each layer be defined, validated, and repaired **independently**.
A mistake in the risk layer does not corrupt the fact layer; changing the gap layer does not force
re-training the recommendation layer. One artifact per layer also means every change is diffable,
traceable, and reproducible on the same sample.

## Trade-offs
- Requires maintaining a contract layer (9 schemas + adapters) — higher upfront cost.
- Risk of **semantic drift** between layers (the same concept defined twice) — suppressed by
  "contract as the single source of truth + canonical-first", but needs ongoing discipline.
- One run takes more steps (more artifacts on disk), but for **high-stakes decisions**,
  explainability > step count.
