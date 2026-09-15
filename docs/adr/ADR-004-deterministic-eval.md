> 🌐 **Language:** 🇨🇳 [中文版](ADR-004-deterministic-eval.zh-CN.md) · 🇺🇸 English

# ADR-004 · Deterministic eval

## Context
Whether an artifact produced by a Skill is "trustworthy" needs a criterion. The laziest approach:
let the producer self-declare `"status": "ok"`, or have another LLM grade it.

## Decision
Eval is a **deterministic engine independent of Skills** (`runtime/eval_engine.py`) executing 6
machine-judgeable check families:
`schema / required_fields / required_non_empty / contamination / provenance / cross_artifact / invariant`.
Rules are externalized in `runtime/resources/config/eval.rules.json` and can be negatively injected
via `-RulesPath`.
**Any check that cannot be evaluated is recorded as FAIL — never as MANUAL/UNKNOWN pass.**

## Alternatives
- Skill self-eval: the inspected party grades its own paper; not credible.
- LLM-as-judge: unstable and irreproducible for high-stakes domains; masks deterministic problems.
- Schema validation only: misses semantic errors like "the conclusion cites a nonexistent
  evidence".

## Why
"An insurance agent is a high-stakes decision scenario" — the criterion must be **reproducible,
regressable, and falsifiable**. Deterministic eval turns "did the change actually improve things"
into a comparable question (Before/After) instead of intuition.

## Trade-offs
- Deterministic checks cannot cover subjective dimensions like "is the tone too salesy" /
  "is the wording easy to understand" (intentionally out of scope for now).
- Externalized rules add one indirection layer, and rules themselves can be wrong — verified in
  reverse with negative probes (tampered rule copies).
- Strictness yields "better FAIL than pass": some scenarios that should be human-judged will be
  FAIL → `NEEDS_REVIEW`, trading automation rate for correctness.
