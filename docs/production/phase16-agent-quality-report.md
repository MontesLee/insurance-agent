# Phase 16 — Agent Quality & Decision Evaluation Report

Date: 2026-09-20 · Input: phase16-p0-quality-eval-audit.md ·
Production code changes: **0** (one EVALUATOR-side harness bug fixed —
see §16/Findings).

## 01 Executive Summary

```text
Phase 16 = PASS
```

Agent business decisions are now independently, mechanically,
repeatably measurable: 30/30 quality cases across 8 groups, 17
deterministic metrics (4 honestly declared NOT_MEASURABLE, never
faked), hard gates all zero, mutation detection 8/8 (the evaluator
provably has teeth), per-case × per-dimension decision matrix with no
averaging — on top of an untouched production pipeline.

## 02 Scope

Quality, not structure (P15's job) and not knowledge (P14's job):
gap-quality states, solution alignment, recommendation explainability,
sufficiency/abstention, contradiction handling, paraphrase semantic
invariance, evidence-boundary behavior, report CONTENT consistency,
calibration tendency, multi-risk capability boundary.

## 03 Audit Result

P0 audit (probed truths): engine gap states map 1:1 to the GQ
vocabulary (SUFFICIENT↔NO_GAP — probed: all-covered ⇒ gaps=[] ⇒
COMPLETED; PARTIAL; NONE↔MATERIAL; UNKNOWN fail-closed by
construction); coverage signal lives on risk.coverage_assessment
(structured beats free text — my earlier "well-covered still
CRITICAL" was a probe artifact, retracted); contradiction semantics
EXIST end-to-end (conflicts[] → CONFLICTING_INFORMATION hand-off with
generated questions at the intake human gate); explainability fields
are built into primary_recommendation.

## 04 Quality Dimensions (implemented)

GQ-01..04 (gap states incl. UNKNOWN≠NO_GAP) · SQ (no gap → no
solution; solution↔gap trace) · PCQ-01..04 (catalog / eligibility /
evidence gating / NO_CANDIDATES) · RQ1..RQ6 (alignment, validity,
14.5 grounding delegation, explainability fields, abstention) · QQ
(question targets = missing_from_upstream + gate questions,
deterministic) · RPT-Q1..7 (report content ⊆/⊆ upstream: gap ids,
risk ids, solution types, recommendation echo, evidence ids,
information gaps).

## 05 Dataset (30 cases, 8 groups)

standard 5 (incl. MD-001 multi-risk + grounded-COMPLETE explainability)
· gap_quality 4 (SUFFICIENT/PARTIAL/NONE/UNKNOWN) · solution 1 ·
sufficiency 5 (AQ-S001..005) · contradiction 5 (age/insurance/income/
marital/children) · paraphrase 5 (housing ×3, children ×2 — semantic
signatures: terminal + gaps(domain,level,status) + solutions + rec
status) · boundary 3 (UNKNOWN-license / expired / empty-KB) ·
recommendation 2 (grounded COMPLETE, NO_CANDIDATES abstention).
Machinery reused from P15 (seed → run → approve-loop → structural
invariants) + risk_edits extension.

## 06 Metrics (17, honest)

requirement/risk precision+recall = **NOT_MEASURABLE** (dialogue-
driven provided stages; F-14 — declared, not estimated). The
remaining 13 (consistency ×2, gap accuracy, solution alignment,
candidate validity, recommendation grounding + decision accuracy,
question target accuracy, report consistency, abstention accuracy,
contradiction detection, semantic invariance, mutation detection)
all PASS with explicit denominators.

## 07 Hard Gates

AQ-HG01..11 mapped onto the P15 structural gates + quality dimensions:
ALL ZERO across 30 real runs. AQ-HG12 (false-pass) proven by wiring:
an injected violation flips the aggregate; the 8/8 mutation suite is
the standing proof.

## 08 Mutation Tests

M01 delete-requirement→HG-B02 · M02 fabricated-requirement→HG-B02 ·
M03 delete-risk→HG-B03 · M04 fabricated-gap→HG-B04 · M05 phantom-
candidate→HG-B11(+B05) · M06 injected-product→HG-B05(+B07) · M07
deleted-evidence→HG-B06(+B07) · M08 tampered-report→HG-B12.
**8/8 detected.**

## 09 Multi-Risk Results (MD-001)

Medical + critical-illness chains form independently and correctly.
**Real capability boundary recorded (not wrapped as PASS)**: the
current business model produces NO solution direction for a life/R4
requirement in this path (F-16) — the multi-risk case passes on the
domains the model serves and the limitation is a finding.

## 10 Sufficiency Results

AQ-S001/S002/S005 → WAITING_FOR_USER with missing-field questions
(existing_insurance is a blocking field) · AQ-S003 → COMPLETED
COMPLETE · AQ-S004 → proceeds with the health UNKNOWN preserved.
Calibration tendency holds (more missing → more WAITING/review).

## 11 Contradiction Results

All five conflict cases stop at the client-intake human gate with
CONFLICTING_INFORMATION + generated questions — never silently
resolved (AQ-HG09 = 0). Recorded nuance F-17 (P3): the stored
client-profile artifact does not retain the conflicts[] detail; the
escalation hand-off DOES carry it (reason/conflicts/next_questions).

## 12 Semantic Invariance

Paraphrase groups (housing ×3, children ×2): identical normalized
signatures across variants — same gaps (domain, level, coverage
status), same solution types, same recommendation state.

## 13 Recommendation Quality

Grounded COMPLETE carries fit + reason_codes + reason + provenance
(requirement/risk/knowledge refs) and stays inside the admissible
candidate set; boundary cases never reach COMPLETE (UNKNOWN-license /
expired / empty-KB); NO_CANDIDATES stays distinct from
INCOMPLETE_EVIDENCE.

## 14 Report Quality

Content-level consistency on every completed case: report gap ids ⊆
produced gaps; risk/solution/evidence sections cite produced ids;
NO_CANDIDATES reports mention no catalog product; information gaps
present. M08 proves tampering is caught.

## 15 Regression

runtime 438 (436→438, +2) · portfolio 12 · 14.1..14.7 suites
52/33/74/52/44/25/21 (+ harnesses) · P15 business eval 15/15 (re-run,
exit 0) + suite 23/23 · full regression 51/0/1 (=) · benchmark 42/42 ·
compileall PASS · quality eval 30/30 + gates 0 + mutations 8/8.

## 16 Production Code Changes

**Zero.** One evaluator-side bug fixed (Phase-15 harness):
`build_seeds` silently ignored the declared `add_conflict` mutation
op — conflicts never reached the seeds, masking the (working)
production conflict handling. Fixed in evals/business; regression:
P15 15/15 re-verified.

## 17 Known Limitations

F-16 (P2, capability): no solution direction for life/R4 in the
current deterministic chain (MD-001 boundary). F-17 (P3): conflicts[]
detail not persisted in the stored artifact (carried in the
escalation hand-off). F-14 (P3): dialogue-layer derivation quality
remains NOT_MEASURABLE deterministically. Prior findings F-02/04/05/
06/08/09/10/11/12/13/15 unchanged, none blocking.

## 18 Final Verdict

```text
Phase 16 = PASS
```

The agent's business judgments can be decomposed, verified, and
caught when wrong — and the evaluator itself is mutation-proven.
