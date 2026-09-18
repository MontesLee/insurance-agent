# Agent PM / AI Product Manager — the product thinking behind the runtime

> For PM interviews. This is not a code tour; it's the product reasoning
> that produced the architecture. Everything here is realizable in the repo.

## Problem definition: insurance advisory is not a Q&A bot

A chatbot answers questions. A family advisory engagement delivers a
**work product**: a personalized analysis report grounded in the client's
facts, current knowledge, and a vetted product catalog. That means a
pipeline, not a conversation:

```text
Client facts → Requirements → Risk → Coverage gap → Solution
            → Knowledge evidence → Product candidates → Report
```

The product question was never "how do we answer insurance questions" —
it was "how does an agent system reliably complete this multi-step,
evidence-bound, failure-prone workflow, and how do we prove it didn't
hallucinate success?"

## Workflow decomposition & skill boundaries

Nine skills, each owning one question and one artifact (why split: each has
a distinct contract, eval rules, and failure mode; a monolith has none of
those):

| Skill | Owns the question | Artifact |
| --- | --- | --- |
| client-intake | what are the facts? (never judgment) | client-profile |
| requirement-analysis | what does the client need? (product-agnostic) | requirements |
| risk-analysis | what are they exposed to? | risk-assessment |
| coverage-gap | how much is unprotected? | gap analysis |
| solution | what strategy fits? (still product-agnostic) | solution-plan |
| knowledge-search | what does the evidence say? | sourced evidence |
| product-candidates | which vetted products fit? | catalog-backed candidates |
| report-generation | what do we deliver? | final report |

The product-agnostic vs product-backed split (analysis may never name
products; only the catalog-backed layer may) is an **eval-enforced content
policy**, not a prompt suggestion.

## Agent boundary design

Four specialists (analyst / knowledge / product / report) instead of one
agent, because: scope-limiting tool access per agent (the analyst
physically cannot recommend products), independent eval per artifact,
auditable responsibility, and parallelizable execution. Deterministic
task→agent assignment — never LLM-decided — because who does the work is a
product/governance decision, not a model preference.

## Human control as two distinct product primitives

- **HITL — human as decision gate**: high-impact graph changes pause in
  WAITING_HUMAN; approve or reject; rejection fails closed. The human is
  *in* the process at defined gates.
- **HOTL — human as supervisor**: the runtime runs autonomously; a
  deterministic monitor surfaces risk; the human is notified, or the
  runtime pauses at a safe barrier and resumes. The human is *above* the
  workflow, never a node in it.

Conflating these is a classic agent-product failure: either the human
becomes a latency bottleneck (all HITL) or loses control (all HOTL).

## Evaluation = the product's acceptance criteria

"Looks like a good answer" is not acceptance. This project defines
acceptance as machine-checkable contracts: structured artifacts with
schemas, deterministic eval rules (required fields, no product leakage
into analysis, provenance resolvable, catalog invariants), provenance on
every fact, bounded repair, and a benchmark with **false-pass adversarial
testing** (prove the system does NOT pass bad work — count 0). The PM
deliverable here is the eval rubric itself.

## Failure-mode product design

An 18-row failure-mode matrix (planner garbage, empty knowledge, invalid
products, eval exhaustion, blocked tasks, rejected approvals, crashed
commands, unauthorized actors…) each with expected state/event/terminal
behavior — this is requirement-writing for a probabilistic system: define
what must happen when things go wrong, then test it.

## Trade-offs & productization

Deliberate scope decisions, all documented (ADRs + design-decisions.md):
single-process durable-JSON runtime over distributed infra (transparent,
reproducible portfolio prototype); deterministic benchmark kept strictly
separate from real-LLM smoke (LLM wording may never move acceptance
criteria); demo product catalog clearly labelled as demo data. Productized
as one-command demos, bilingual docs, and a portfolio release (v0.1.0).

## Success metric for this product

For a portfolio: does the system complete real multi-agent work with
evidence — 11/11 benchmark, 18/18 fault injections, 0 false passes,
second domain on the same runtime. For production, the next product
milestones would be: real catalog integration, human-approval UI, and
external notification channels — all already architected as adapters.
