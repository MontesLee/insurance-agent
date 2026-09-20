# Phase 16 P0 — Agent Quality Eval Audit (read-only, 2026-09-20)

Baseline: Phase 15 PASS (15/15 business cases, HG-B zero). All claims
below were PROBED on the real pipeline this round.

## 1. What already exists and is REUSED (never re-implemented)

- Phase 14 evidence/provenance/governance + validators
  (validate_provenance / validate_decision_provenance) — Phase 16
  CALLS them; copies nothing.
- Phase 15 business harness (evals/business/run_business_eval.py):
  seeding machinery (orch.seed_case → run → approve-loop), registry
  mutation injection, validate_business_decision, structural
  invariant scans (I1–I8 / HG-B01..12). The quality runner IMPORTS
  this harness.
- Phase 15 dataset (15 cases) stays as the structural gate; Phase 16
  adds a quality-focused dataset (30 cases) on the same machinery.

## 2. Probed business-truths the quality dimensions build on

### Gap engine vocabulary (coverage_gap_engine.py:44–83)

PRIMARY signal = risk.coverage_assessment{protected_amount,
unprotected_amount} → SUFFICIENT / NONE / PARTIAL numerically;
FALLBACK = keyword scan of risk.existing_protection free text;
default = UNKNOWN ("现有保障信息不足，无法判定覆盖程度").

Mapping to the Phase-16 GQ states (current contract, per §3/§6 of
the brief — use the existing model, do not invent):

| brief state | engine state | proven behavior |
|---|---|---|
| NO_GAP | SUFFICIENT (protected>0, unprotected=0) | probed: all risks SUFFICIENT → **gaps = []**, terminal COMPLETED (GQ-01 engine-built) |
| PARTIAL_GAP | PARTIAL | probed: fixture CI/accident risks → PARTIAL |
| MATERIAL_GAP | NONE | probed: medical risk (protected=0) → CRITICAL/NONE |
| UNKNOWN | UNKNOWN | fail-closed by construction — never treated as covered (GQ-04) |

IMPORTANT correction to my own earlier probe: the coverage signal
lives on EACH RISK (coverage_assessment), not on
client-profile.existing_protection — profile-level edits correctly do
NOT change gaps (the engine trusts the structured assessment over
free text; feeding contradictory inputs does not fabricate coverage).

### Contradiction semantics (§18) — ALREADY BUILT

client-profile.conflicts[] + the field set UNKNOWN → the run STOPS at
the client-intake human_review gate (terminal WAITING_FOR_USER,
stopped_at=client-intake) — probed with an age 30-vs-35 conflict.
Contradictions are never silently resolved. AQ-HG09 is testable by
REUSING this exact semantic.

### Sufficiency / questions (§13)

Critical-field UNKNOWN (existing_insurance) → WAITING_FOR_USER at
client-intake; missing_from_upstream carries field+reason. The gap
engine ALSO emits information_gaps and the candidate provider emits
next_information_needed — deterministic question targets exist at
three layers; QQ evaluation uses expected_missing_fields vs these
records (no LLM judge).

### Recommendation explainability — ALREADY BUILT

primary_recommendation carries {candidate_id, fit, reason_codes,
reason("因为…所以作为主推荐"), provenance[requirement/risk/knowledge
refs]}. RQ5 is a structural assertion over these fields.

## 3. What Phase 16 must ADD

- evals/agent_quality/: 30-case quality dataset (standard 5 · gap
  quality 4 · solution 1 · sufficiency 5 · contradiction 5 ·
  paraphrase 5 · boundary 3 · recommendation 2), decision matrix
  (per-case × per-dimension, no averaging), 13 metrics with
  NOT_MEASURABLE honesty, AQ-HG01..12 hard gates, 8 mutation tests,
  exit codes 0/1/2.
- Quality runner reusing the P15 harness + 14.5 validators.

## 4. Measurability honesty (§22/§25)

Requirement/Risk derivation quality (client dialogue → requirements /
risks) runs in the dialogue-driven provided stages — NOT
deterministically re-derivable in-repo (F-14). Requirement/Risk
Precision & Recall are therefore **NOT_MEASURABLE** and will be
reported as such (consistency-only assertions apply). Every other
dimension has a deterministic measurement over produced artifacts.

## 5. Findings from the audit probes

- **F-15 (P3, informational)**: gap coverage recognition relies on
  the structured coverage_assessment produced upstream; the free-text
  fallback is weaker (PARTIAL at best, no SUFFICIENT from text
  alone). Correct per contract; recorded so quality cases seed the
  structured field.
- No new P0/P1. The earlier suspected "well-covered still CRITICAL"
  was a probe artifact (wrong layer), not a defect — verified.
