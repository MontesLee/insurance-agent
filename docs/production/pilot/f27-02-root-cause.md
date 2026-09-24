# F27-02 Root Cause — recommendation outcomes on the demo catalog

## Corrected frequency (this gate re-read the artifacts; the round-1
"12/12 primary={}" summary was over-general)
- product-recommendation PRODUCED on 10/12; status
  INCOMPLETE_EVIDENCE on all 10.
- Primary recommendation EXISTS on 2/12 (C02 single_adult,
  C03 married_no_child — requirement sets the single-domain catalog
  can fit); 8/12 no primary; C08/C11 NOT PRODUCED (see F27-01).

## Engine mechanics (recommendation_engine.py, read-only)
rec_status priority per candidate: hard product-validation block →
not_recommended; evidence insufficient/conflict →
insufficient_evidence; **requirement_fit poor_fit/not_suitable →
not_recommended**; else primary. Top status: primary=None +
eligible-but-unevidenced candidates → INCOMPLETE_EVIDENCE;
primary present + blocking uncertainties → INCOMPLETE_EVIDENCE
(by design, engine L642-660, with named uncertainty reasons and
human_review_required=true).

## Diagnostic (tools/diag_f2702.py, NEW diagnostic only —
zero runtime/skill changes; results in data/diag-f2702.json)
- Case A (full pipeline, keep REQ-MED only, fixture KB): case
  COMPLETED; **primary C001 EXISTS**; status INCOMPLETE_EVIDENCE
  with documented per-coverage uncertainty ("critical_illness
  lacks knowledge backing") + human_review_required=true → PASS
  (primary producible; status downgrade is designed behavior).
- Case B (same artifacts, knowledge evidence stripped, fed to the
  recommendation skill entrypoint): **primary BLOCKED**; 4/4
  candidates insufficient_evidence; status INCOMPLETE_EVIDENCE;
  nothing fabricated → PASS.

## Verdict
**A PASS + B PASS → the recommendation/evidence/grounding runtime
logic behaves as designed.** F27-02 reclassifies from "P1 runtime
suspicion" to **catalog/evidence CONTENT gap**: the demo catalog is
single-domain and the fixture KB lacks backing for most coverage
types, so multi-requirement cases are structurally poor-fit.
Severity stays P1 for pilot VALUE (recommendation quality cannot
be validated on this content), but the owning layer is Product
catalog + knowledge evidence content, NOT runtime.

## Decision
CATALOG FIX (+ evidence content). No runtime change justified by
evidence. Sub-options for the engineering phase: populate a real
multi-domain production catalog + KB backing (unblocks business
validation), or scope the pilot to pre-recommendation stages.
