# Phase 15 P0 — Business E2E Audit (read-only, 2026-09-20)

Baseline at audit: Phase 14.7 enriched (10 real docs); runtime 433 ·
portfolio 12 · regression 51/0/1 · benchmark 42/42. Probe-runs below
were executed against the REAL pipeline (seed → orchestrator run →
artifacts), not read from stale docs.

## 1. Skill / stage inventory (as wired in runtime/insurance-analysis.yaml)

| Stage | Executor | Engine | Output artifact | Real statuses (probed) |
|---|---|---|---|---|
| client-intake | provided (dialogue) + gate human_review | PS1 dialogue skill | client-profile | payload = 5-state field model (KNOWN/UNKNOWN/ESTIMATED/ASSUMED/INFERRED + missing_from_upstream) |
| requirement-analysis | provided | PS1 | requirement-analysis | analysis_status COMPLETE; requirement_type ∈ {medical, critical_illness, life, accident, savings}; boundary=requirement_only |
| risk-analysis | provided | PS1 | risk-assessment | risk_category R1–R5 |
| coverage-gap-analysis | python deterministic | rules-externalized | coverage-gap-analysis | status COMPLETE; gap fields: gap_id/domain/subject/gap_level{CRITICAL,HIGH,MEDIUM}/current_coverage{status,evidence_refs}/target_coverage/reason/related_*_ids |
| solution | python deterministic | rules | solution-plan | COMPLETE; solution_type ∈ {MEDICAL, CRITICAL_ILLNESS, ACCIDENT, SAVINGS}; product-NEUTRAL fields (coverage_direction/trade_offs/constraints; no product fields) |
| knowledge-search | SERVICE (evidence provider) | KnowledgeService (14.4+): provider→governance→evidence | knowledge-evidence | success/partial/insufficient; items carry full citation tuple (14.5) |
| product-candidate-provider | python deterministic | catalog + eligibility + evidence gating | product-candidates | COMPLETE/NO_CANDIDATES/...; payload at TOP level (skill/version/status/candidates/admissible_candidate_ids/rejected); 10 candidates on the standard fixture |
| product-recommendation | python deterministic | grounding rules | product-recommendation | INCOMPLETE_EVIDENCE on the standard 5-requirement fixture (evidence grounds part of the requirement set — honest, no primary forced); evidence_refs resolve; derivation/strategy_trace/tradeoffs present |
| report-generation | python renderer | fixed sections | insurance-report | success; structured sections: client_profile, financial_profile, risk_exposure, coverage_gaps(+derivation), solution_strategies, recommended_directions, evidence_summary, information_gaps, next_actions, disclosure |

Report-section mapping to the Phase-15 §7 ten client questions: 01→
client_profile/financial_profile · 02→risk_exposure · 03→coverage_gaps ·
04→coverage_gap_derivation · 05→solution_strategies/recommended_directions ·
06/07→recommended_directions + recommendation artifact derivation/
strategy_trace (rendered via evidence_summary context) · 08→
evidence_summary + disclosure · 09→information_gaps · 10→next_actions.
All ten are answerable from the current contract — no report rewrite
needed.

## 2. Orchestrator / runtime

orch.seed_case(wf, case_id, seeds, provided_by) → orch.run(state, wf,
gate_policy="stop", kb_dir, checkpoint_root) → PAUSED_NEEDS_REVIEW
approve-loop (final-review gate). Deterministic engines only — no LLM
on this path. Checkpointing, repair (≤2), replanning all test-proven.

## 3. Existing E2E / eval assets to REUSE (not duplicate)

- tests/e2e/fixtures/case-full-chain.json — proven seed set
  (client-profile + requirement + risk).
- test-cases/e2e/full-agent — 5 cases incl. WAITING_FOR_USER on
  UNKNOWN existing insurance (N001 semantics), empty-KB evidence
  failure → repair → NEEDS_REVIEW (N005), age-85 → NO_CANDIDATES
  (N004). Mutation machinery: set_unknown/set_value/add_conflict/
  set_risk/set_all_risks.
- eval invariants: schema / required_fields / required_non_empty /
  contamination (upstream must not leak products — B5) /
  provenance_evidence_document_chunk / provenance_recommendation_
  evidence / catalog_exists + R-03 governance / candidate_known /
  catalog_has_primary_product.
- Phase 14 validators: validate_provenance / validate_decision_
  provenance (B7 / I7 / §11 binding).
- 14.6/14.7 knowledge + pilot harnesses (metrics + hard-gate
  patterns to mirror).

## 4. Gap analysis → what Phase 15 must ADD

1. A business golden dataset (10 client cases) + 5 business negatives
   with per-stage business expectations (current e2e asserts pipeline
   mechanics, not the B1–B5/I1–I8 business invariants).
2. A deterministic business evaluator (evals/business/run_business_
   eval.py) with 11 metrics + 12 hard gates (HG-B01..B12).
3. validate_business_decision() — thin wrapper over the 14.5
   validators (eval-side; NO new governance).
4. Cross-skill invariants I1–I8 as machine checks over produced
   artifacts (incl. report-claims-traceability I8).
5. Three demos (display, explicitly NOT gate evidence).

## 5. Findings from the probe (recorded, not fixed)

- **F-13 (P2, behavioral)**: on the canonical full-chain fixture the
  recommendation terminal status is INCOMPLETE_EVIDENCE (no primary
  product) — evidence grounds only part of the multi-requirement set.
  Per Phase-15 §21 this is an acceptable honest outcome; the golden
  set must ALSO contain a fully-commendable case (single-requirement)
  to prove the COMPLETE path still exists. (Verified during dataset
  authoring; if unreachable, escalate to P1.)
- F-14 (P3): client-intake/requirement/risk are dialogue-driven
  `provided` stages — B1–B3 fact-discipline is verified at the SEED
  contract level (5-state statuses, missing_from_upstream) and via
  the existing WAITING_FOR_USER semantics; re-deriving dialogue
  behavior deterministically is out of Phase-15 scope.
- Existing e2e already proves N001/N004/N005 mechanics — the business
  eval reuses those scenarios with business-level assertions added.
