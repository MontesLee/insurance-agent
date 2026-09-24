# ADR-018: Human Feedback Loop Separation

## Status: APPROVED (design only — Phase 27.6; implementation
awaits Phase 27.7 authorization)

## Context

The Phase 27.5 Governance Layer records human decisions (APPROVE
/ REJECT + reason) as immutable backend records. Phase 27's pilot
produced structured owner-review judgments (12-case workbench,
F01–F18 taxonomy) as hand-written documents. Both are valuable
signals for improving the agent — and the natural temptation is to
let feedback flow straight into prompts, skills, the product
catalog, or the knowledge base.

Phase 27 evidence (F27-02: apparent "recommendation bugs" that
turned out to be catalog content; F27-01: runtime semantics, not
skill issues) shows that human-observed symptoms are a poor guide
to the engineering layer that must change.

## Decision

Human feedback is EVIDENCE, not a control signal. It flows through
an evaluation pipeline and never mutates the runtime directly:

1. Feedback is a separate entity from Decision (Decision = what
   happened, terminal; Feedback = why + how to improve, curated).
2. Feedback is captured at the decision point (governance UI)
   with structured references; normalization and curation happen
   offline in the evaluation domain.
3. Only curated feedback becomes evaluation cases / knowledge
   tickets / product backlog entries; agent improvement happens
   through the normal engineering flow (code/rules/catalog change
   + full regression + human review).
4. The runtime never consumes feedback synchronously; no feedback
   path may modify prompts, skills, workflow, or knowledge at
   execution time.

Entity-model choice (anchor-on-decision with typed references vs
skill- or evidence-owned feedback) and the taxonomy are DESIGN
recommendations in docs/architecture/human-feedback-loop-v0.1.md
— deliberately NOT frozen by this ADR until Phase 27.7 validates
them.

## Consequences

- The evaluation suite (golden cases, benchmark, mutation tests)
  remains the sole gate for agent change; feedback only adds
  candidates to it.
- Feedback tooling can evolve in the governance/eval domain
  without touching runtime (consistent with ADR-017).
- Automatic "feedback → prompt/skill change" is prohibited
  without a new ADR explicitly overturning this decision.

## Alternatives considered

- **Direct feedback-driven tuning (auto-apply)**: rejected —
  bypasses the regression gate and lets noisy human judgment
  mutate production behavior.
- **Feedback as free-text comments only**: rejected — Phase 27
  showed unstructured comments cannot be normalized into
  evaluation inputs; structure (category + refs) is required at
  capture time.
