# Phase 14.6 — Knowledge Evaluation & Quality Gate Report

Date: 2026-09-20 · Scope: evaluation harness ONLY — zero production code
modified this phase (verified by diff audit).

## 1. Objective

Prove BEHAVIORAL CORRECTNESS of the 14.1–14.5 knowledge layer under a
deterministic, independently runnable golden-dataset harness with
explicit-denominator metrics and safety hard gates that no averaging
can mask.

## 2. Evaluation Architecture

```text
evals/knowledge/dataset/*.json   golden cases (expected outputs, gates)
evals/knowledge/run_knowledge_eval.py   harness: run_case → evaluate →
  aggregate_metrics → apply_hard_gates; exit 0 only if ALL cases pass
  AND all safety gates clean; JSON report → tmp/knowledge_eval_report.json
tests/runtime/test_p14_knowledge_eval.py   gate wrapper + isolation/
  determinism/one-way-dependency assertions (dual-mode)
```

Dependency direction: evals → production ONLY (production never
imports evals/ — asserted). Deterministic: fixed clock, fixed as-of
per case, exact/field/rule comparison; no LLM judge, no similarity
scores, no network/Docker/WeKnora/DB/keys.

## 3. Dataset (50 cases — high-signal, not volumetric)

| Category | Cases | Content |
|---|---|---|
| retrieval | 6 | exact-target, ranking (rank-1 section), irrelevant query → abstention, jurisdiction-scoped retrieval |
| governance | 17 | ALLOW/DENY pairs across window (current/expired/future/before), authority (conflict/missing), jurisdiction (match/national-applies-local/mismatch), license (ALLOWED/RESTRICTED/UNKNOWN), version (missing/conflict), hash mismatch, registry miss, unregistered chunk |
| provenance | 6 | complete lineage ×2, missing hit/document/retrieved_at, jurisdiction swap |
| decision | 5 | bound-valid, missing ref (D002), empty-required (D001), NO_EVIDENCE_REQUIRED, tampered evidence (D003) |
| abstention | 5 | empty KB, expired-only corpus, unknown-license-only, provider error → fail-closed, wrong-jurisdiction |
| mutation | 5 | 1-char hash flip, 2026→2024 version swap, UNKNOWN→ALLOWED license forgery, expired→active metadata claim, authority flip |
| parity | 3 | Provider A (Mock) vs Provider B (deterministic contract-fixture provider — NOT WeKnora) ×2; Tool vs Orchestrator ×1 |
| grounding | 3 | SUPPORTED / UNSUPPORTED(required) / NOT_CHECKABLE over the existing 5-attribute policy |

Majority negative/adversarial (31/50 carry safety gates).

## 4. Retrieval Metrics

hit@5 = 6/6 applicable cases · miss_rate = 0.0 ·
irrelevant_retrieval = 0/1 (the quantum-hardware query abstains).

## 5. Governance Metrics (confusion matrix, denominator 17)

true_allow 8 · true_deny 9 · **false_allow 0** · **false_deny 0**.

## 6. Provenance Metrics

complete_lineage_rate 6/6 · broken_lineage_detection_rate 6/6 (every
invalid mutation caught at the exact P-rule).

## 7. Abstention Metrics

correct_abstention_rate 5/5 · **unsafe_accept 0** (expired-only,
unknown-license-only, wrong-jurisdiction corpora all yield ZERO
evidence; provider error fails closed).

## 8. Provider Equivalence

contract_equivalence_rate 3/3 — Mock vs the deterministic
contract-fixture provider produce identical lineage values on every
compared field per shared governed chunk; Tool vs Orchestrator
identical. **Claimed: provider CONTRACT equivalence — NOT a WeKnora
result** (14.2 remains BLOCKED).

## 9. Mutation Tests

5/5 detected at the precise rule (P007 hash / P004 version / P009
license forgery / WINDOW_EXPIRED despite active-claiming metadata /
P006 authority). The registry stays authoritative in every case.

## 10. Hard Gates (§20 wiring)

false_allow 0 · unsafe_accept 0 · fabricated_evidence 0 ·
invalid_provenance_pass 0 · expired_knowledge_accepted 0 ·
UNKNOWN_license_accepted 0 · jurisdiction_violation 0 ·
hash_mismatch_accepted 0 · contract_equivalence 0 failures.
Wiring proven by test: injecting ONE synthetic failure flips the
verdict to FAIL. **OVERALL = PASS (50/50 + gates CLEAN, exit 0).**

## 11. Runtime / Portfolio / Regression (Before → After → Delta)

```text
pytest tests/runtime -q       427 → 430  (+3 eval-suite)      PASS
pytest tests/portfolio -q     12  → 12   (=)                 PASS
14.1 provider                 52/52 (=)   14.2 POC   33/33 (=)
14.3 governance               74/74 (=)   14.4 runtime 52/52 (=)
14.5 provenance               44/44 (=)   14.6 eval    25/25 (new)
knowledge harness             50/50 cases, HARD GATES CLEAN, exit 0
full regression (workbuddy)   51 PASS / 0 FAIL / 1 pre-existing GBK
                              INFRA_ERROR (= baseline)
benchmark                     42/42 (=)   compileall  PASS
```

Mid-phase calibration (all harness/dataset-side, no system rule
changed): RET-002/005 re-targeted to phrases the deterministic corpus
actually contains (the governed corpus has no 重疾 doc); PAR-003
reused the canonical query; GRD-002 fixed the constraint field name
(`renewal` per the rules file); GRD/GOV harness bugs fixed. The
system's business rules were never adjusted to pass.

## 12. Files Changed

```text
NEW  evals/knowledge/__init__.py
NEW  evals/knowledge/run_knowledge_eval.py (harness)
NEW  evals/knowledge/dataset/{retrieval,governance,provenance,decision}_cases.json
NEW  tests/runtime/test_p14_knowledge_eval.py (25 checks)
NEW  docs/production/phase14-p6-knowledge-eval-report.md
MOD  — NONE in production code (diff audit: all tracked M files are
       uncommitted 14.4-era changes; benchmark timestamp only)
```

## 13. Findings

- **F-10 (P3, informational)**: hit@1 is currently only asserted via
  the rank-1-section case (RET-003); a graded ranking benchmark needs
  a relevance-labeled corpus — NOT MEASURABLE with today's fixtures;
  recorded rather than estimated.
- F-02/F-04/F-05/F-06/F-08/F-09 unchanged (per §35/§36 — none blocks
  the quality gate).
- No P0/P1. No false-allow/unsafe-accept of any kind.

## 14. Deferred Items

Real WeKnora live POC (F-06 + operator infra); real-source pilot
(Phase 14.7 scope, pending approval); ranking-graded corpus (F-10);
F-09 decision-convention extension.

## 15. Acceptance Gates

G1 dataset ✓ · G2 retrieval ✓ · G3 governance ✓ · G4 freshness ✓ ·
G5 authority/jurisdiction ✓ · G6 license ✓ · G7 grounding ✓ ·
G8 provenance ✓ · G9 abstention ✓ · G10 provider equivalence ✓ ·
G11 tool/orchestrator parity ✓ · G12 mutation ✓ · G13 hard gates ✓ ·
G14 full regression ✓ · G15 no external infrastructure ✓

## 16. Final Recommendation

```text
Phase 14.6 = PASS
```

The knowledge layer now has a verifiable correctness and failure
boundary at every hop. Next (on human approval only): Phase 14.7 —
Real Knowledge Pilot — over operator-verified sources.
