---
description: Periodic product/architecture drift audit against the North Star (read-only) — v2 PASS/FAIL + GREEN/WARNING/BLOCKED verdict
---

# /product-audit — Product Alignment & Drift Audit (v2)

You are auditing this repository for product-direction and
architecture drift. **Read-only: no code modification.**

## Inputs (read in this order)

1. `CLAUDE.md` — Project Identity & Architecture Guardrails
   (alignment check, drift detection, forbidden actions)
2. `docs/production/architecture/PRODUCT_VISION.md` (canonical,
   FROZEN)
3. `docs/production/architecture/ARCHITECTURE_PRINCIPLES.md`
   (canonical, FROZEN)
4. `docs/production/governance/product-direction-audit.md` (drift
   baseline — diff against it)
5. ADRs: `docs/adr/ADR-001..007` (founding), `docs/production/
   ADR-008..018` (in force), `docs/adr/ADR-019..024` (PROPOSED —
   design, not license, until approved)

## Audit the repository (code over docs — never trust a design doc
over the tree; every verdict needs file:line evidence)

1. **Product Alignment** — default user entry is Chat; business
   capabilities (QA / product QA / planning / plan modification)
   reachable from Chat; no developer-page-only business flow;
   anti-goals held; user-facing output free of run_id / artifact_id
   / eval_id / approval_id / dashboard / developer mode.
2. **Agent Architecture** — Intent Layer: intent truth in schema +
   externalized rules + runtime events (prompt is auxiliary only;
   fail-closed unknown). Router: pure validated-intent→agent
   lookup; no LLM in routing; no business logic/workflow/retrieval;
   no agent-calls-agent outside declared mechanisms. Registry:
   single source of truth for agent identity (intents/tools/
   workflow/output types), startup-validated; no undeclared agents
   on production paths.
3. **Knowledge Grounding** — insurance facts (clauses, coverage,
   waiting period, exclusions, sum insured, premium, eligibility)
   come only from Catalog (deterministic) or governed WeKnora
   evidence; answers evidence-gated in code (not prompt-only);
   missing evidence → fail-closed refusal; no param-memory facts.
4. **Space Separation** — User / Operator / Developer spaces
   separated (routing/gating where applicable); developer surface
   not exposed to users; internal GAP notes not on user faces.
5. **Runtime Integrity** — single runtime: orchestrator + event +
   artifact reused; no new parallel workflow engine / artifact
   store / agent execution model / run registry (the 7-store
   count is legacy debt that must shrink, not grow).
6. **ADR Drift** — run `git status`/`git diff`; list changed files
   that touch ADR-governed areas (runtime/agent execution/
   artifact lifecycle/eval/approvals/knowledge); verify each is
   covered by an in-force ADR + approved phase, and that ADR files
   themselves were not silently modified.

Also diff findings against the drift baseline: baseline P0/P1/P2
items must be unchanged/improved/resolved — any new drift or P0
regression is the headline finding.

## Output (mandatory format)

Write the full report to
`docs/production/governance/product-audit-YYYY-MM-DD.md`, then
summarize in chat with EXACTLY this verdict block:

```
## Product Alignment
Chat-first: PASS/FAIL

## Agent Architecture
Intent Layer: PASS/FAIL
Router: PASS/FAIL
Registry: PASS/FAIL

## Knowledge Grounding
Insurance Fact Evidence: PASS/FAIL

## Space Separation
User/Operator/Developer: PASS/FAIL

## Runtime Integrity
Single Runtime: PASS/FAIL

## ADR Drift
Changed ADR related files: <list or "none">

Final: GREEN / WARNING / BLOCKED
```

Verdict rules: **GREEN** = all PASS, no new drift, ADR files
untouched. **WARNING** = any FAIL on a not-yet-built layer that is
on the approved roadmap (known gap, converging) OR minor new drift
— name the owner action. **BLOCKED** = a forbidden action pattern
confirmed in code (parallel runtime, LLM routing, unevidenced
insurance facts on a live path, developer UI exposed to users,
silent ADR edit) OR a baseline P0 regressed — stop and escalate.

Then **STOP** (no code modification).
