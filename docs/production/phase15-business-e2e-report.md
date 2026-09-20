# Phase 15 — Business E2E Validation Report

Date: 2026-09-20 · Input: phase15-p0-business-e2e-audit.md · Zero
production-code changes (audit → dataset → evaluator → demos → tests).

## 01 Executive Summary

```text
Phase 15 = PASS
```

A real client input now flows through the COMPLETE business chain —
intake facts → requirements → risks → gaps → solutions → governed
knowledge → catalog candidates → grounded recommendation → report —
and every hop is machine-verified: 15/15 business cases (10 golden +
5 negative), cross-skill invariants I1–I8 at 100%, all twelve hard
gates (HG-B01..B12) at ZERO violations, all eleven metrics PASS, with
Phase 14 fully intact.

## 02 Current Architecture (audited, probed)

See the P0 audit. Key probed truths this phase builds on: gap engine
emits gap_level CRITICAL/HIGH/MEDIUM with current_coverage evidence;
solution stage is product-NEUTRAL (contamination invariant enforces it
upstream too); candidates come only from the catalog with eligibility
+ evidence gating; recommendation statuses observed in the wild:
COMPLETE (single-domain, grounded) / INCOMPLETE_EVIDENCE (honest
partial grounding) / NO_CANDIDATES / NEEDS_REVIEW; report renderer has
all ten client-facing sections including disclosure, information_gaps,
next_actions. The knowledge stage is the Phase-14 governed service
(provider → governance → evidence → provenance).

## 03 Business E2E Flow (verified end-to-end per case)

seed(provided dialogue artifacts, 5-state fact model) → orch.run →
coverage-gap → solution → knowledge-search service → candidates →
recommendation → (final-review gate, approve loop) → report. Every
case ran the REAL deterministic engines + the REAL governed knowledge
service (registry mutations injected via the composition seam for the
two knowledge-negative cases; empty KB for the evidence-negative).

## 04 Golden Dataset (10 cases)

B001 standard family (multi-requirement honest INCOMPLETE_EVIDENCE) ·
B002 single high-income (missing-field discipline, no life domain) ·
B003 mortgage family · B004 children family · B005 dual-income ·
B006 high medical risk (medical domain guaranteed) · B007
well-covered (gaps must respect existing protection) · B008 severe
insufficient info → WAITING_FOR_USER (never invents) · B009 no
product match (85y) → NO_CANDIDATES ≠ INCOMPLETE_EVIDENCE (R4) ·
B010 multi-risk. Expectations encode business truths from the
contracts, not copies of engine output.

## 05 Negative Dataset (5 cases)

N001 missing critical info → WAITING_FOR_USER, no completed
recommendation (HG-B10) · N002 expired knowledge (all windows closed
via registry mutation) → ZERO evidence items (HG-B08) · N003
UNKNOWN-license medical knowledge → that domain never grounds (HG-B09)
· N004 requested P999 → fabricated id appears NOWHERE (HG-B05) ·
N005 empty KB → blocked/review, recommendation never COMPLETE
(HG-B06).

## 06 Cross-Skill Invariants (I1–I8, 100%)

I1 facts: fields declared missing_from_upstream never asserted KNOWN
downstream · I2 gaps cite only seeded requirements · I3 gaps cite only
seeded risks · I4 solutions cite only produced gaps · I5 primary
recommendation within admissible candidates · I6 candidates ⊆ catalog
· I7 recommendation evidence passes the Phase-14.5 decision validator
· I8 report sections non-empty only when their upstream artifacts
exist. Implemented as structural scans over every case's real
artifacts (plus HG-B05's whole-corpus fabricated-product-id scan).

## 07 Knowledge Grounding

Every recommendation's evidence_refs resolve into the governed
knowledge-evidence artifact and pass validate_business_decision()
(§11) — a thin wrapper over validate_decision_provenance; explicit
NO_EVIDENCE_REQUIRED passes, silence never does. Expired and
UNKNOWN-license acceptance = 0 across all runs.

## 08 Product Recommendation Validation

Layering proven: candidates (discovery: catalog + eligibility +
evidence gating) vs recommendation (final choice grounded in
requirement + risk + evidence, with fit/reason_codes/provenance).
R1 why-fits (reason + reason_codes + provenance refs) · R2 no
score-only picks (provenance required) · R3 missing evidence →
NOT COMPLETE · R4 NO_CANDIDATES ≠ INCOMPLETE_EVIDENCE (B009 asserts
the distinction) · R5 multi-requirement cases keep complementary
solution sets without forcing one product.

## 09 Report Validation

structured_report sections cover all ten §7 client questions
(mapping table in the audit); I8 consistency checks tie each section
to its upstream artifact; disclosure banner (DEMO catalog) and
information_gaps verified present.

## 10 Hard Gates

HG-B01..B12 all ZERO violations across 15 real runs (aggregate JSON:
tmp/business_eval_report.json). Wiring proven: one injected
violation flips the aggregate.

## 11 Full Regression

```text
pytest runtime 436 (433→436, +3 business suite) · portfolio 12
14.1 52/52 · 14.2 33/33 · 14.3 74/74 · 14.4 52/52 · 14.5 44/44
14.6 25/25 (+ harness 50/50 CLEAN) · 14.7 21/21 (+ pilot 26/26 CLEAN)
full regression 51 PASS / 0 FAIL / 1 pre-existing GBK INFRA_ERROR (=)
benchmark 42/42 · compileall PASS · business eval 15/15 + gates 0
```

## 12 Demo Results (display-only, §16)

Demo A standard family: COMPLETED, full report (14 sections + DEMO
disclosure) — note the honest INCOMPLETE_EVIDENCE recommendation for
the multi-requirement persona. Demo B insufficient info:
WAITING_FOR_USER, zero fabricated facts. Demo C empty-KB evidence:
NEEDS_REVIEW, recommendation never forced.

## 13 Findings

- **F-13 (P2, resolved-positive)**: the canonical multi-requirement
  fixture lands INCOMPLETE_EVIDENCE (partial evidence grounding) — an
  honest outcome per §21; the COMPLETE+primary path is proven by
  B002/B006-style cases and probes (single-domain grounding works,
  primary C001 with fit/reason/provenance). No fix needed; recorded
  so nobody "fixes" honesty into a forced pick later.
- F-14 (P3): dialogue-driven B1–B3 fact-discipline is verified at the
  seed-contract + WAITING_FOR_USER level; deterministic re-derivation
  of the dialogue skills stays out of scope.
- No P0/P1. HG violations of any kind: 0.

## 14 Known Limitations

F-02 (startup provider enforcement), F-04/F-05/F-06 (WeKnora infra),
F-08 (engine-cache perf), F-09 (risk/gap/solution evidence_refs
convention), F-10 (ranking corpus), F-11/F-12 (pilot doc coverage:
no CN-BJ local doc, partial copies) — all unchanged, none blocking.
B1–B3 dialogue depth (F-14) as above.

## 15 Final Verdict

```text
Phase 15 = PASS
```

The Insurance Agent turns the Phase-14 knowledge layer into a
complete, verifiable, explainable, deliverable business loop — and
says "I cannot safely recommend" exactly when the evidence says so.
