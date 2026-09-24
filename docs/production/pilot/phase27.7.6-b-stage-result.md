# Phase 27.7.6-B — Human Reviewer Pilot Cases With Full Evidence Context

Date: 2026-09-24 · All data created through REAL pipeline execution
(POST /api/runs → orchestrator → artifacts/events) + REAL harness
approval creation (create_request → ApprovalStore.append →
ApprovalManager.wait). Zero code/runtime/backend changes.

## Case Table

| case | approval | run | artifacts | evidence |
|---|---|---|---|---|
| HR-R1 (9df166) | pilot-2776-human-reviewer | run_9de5882e | 9 artifacts (incl. product-recommendation with primary C001 + 7 provenance refs) | ✓ full chain |
| HR-R2 (6f2dd6) | pilot-2776-human-reviewer | run_84f63c7c | 6 artifacts (needs_review: no primary, insufficient evidence) | ✓ evidence-absent path |
| HR-R3 (a409d2) | pilot-2776-human-reviewer | run_447ccd4b | 9 artifacts (high-risk family, medical gap 200万) | ✓ full chain |
| HR-R4 (3ca5af) | pilot-2776-human-reviewer | run_381c2836 | 6 artifacts (needs_review: empty KB → fail-closed) | ✓ fail-closed path |
| HR-R5 (2b4e60) | pilot-2776-human-reviewer | run_48cc028f | 0 artifacts (waiting: 3 blocking fields → WAITING_FOR_USER) | ✓ ask-not-guess path |
| HR-R6 (c7fb43) | pilot-2776-human-reviewer | run_dad25ef1 | 9 artifacts (no candidates boundary) | ✓ boundary path |

All 6 approvals: **WAITING_HUMAN** (verified via API, count=6).

## How each case was created

1. **Pipeline run**: `POST /api/runs {"case_id": "<benchmark-case>"}` →
   real orchestrator execution → real artifacts/events stored
2. **Approval**: `create_request(request_type=APPROVAL_FINAL_REVIEW,
   context={"slot": ..., "run_id": ..., "case_id": ...})` →
   `ApprovalStore.append` → `ApprovalManager.wait()` → WAITING_HUMAN

The approval context carries `run_id` + `artifacts_hint` so the
reviewer can find the run in Workspace section C/D/E.

## Coverage matrix

| Slot | Pipeline case | Run status | Business scenario |
|---|---|---|---|
| HR-R1 | bm-complete-006-single-medical | completed | Happy path: primary recommendation exists |
| HR-R2 | bm-noev-001 | needs_review | Evidence insufficient: no primary |
| HR-R3 | bm-highrisk-001 | completed | High-risk family risk analysis |
| HR-R4 | bm-noev-002 | needs_review | Knowledge unavailable: fail-closed |
| HR-R5 | bm-insufficient-004 | waiting | Missing info: ask-not-guess |
| HR-R6 | bm-nocand-001 | completed | Boundary: no candidates |

## Known UI gap (G-27.5-3-02, unchanged)

The Review Workspace does NOT auto-populate the run_id from the
approval context. The reviewer must copy the run_id from section
A (审批摘要, visible in the context block) and paste it into the
run selector to activate sections C/D/E. This is a known gap; the
approval context at least makes the run_id DISCOVERABLE.

## Safety

Code changed: NO · Runtime changed: NO · Backend changed: NO ·
Data created: 6 real pipeline runs + 6 real WAITING_HUMAN approvals
(through the runtime's own code paths; no manual JSON edits)
