# Phase 27.7 — Human Feedback Capture MVP Result (2026-09-24)

Baseline a57e006 (v0.3 Governance Layer pushed). Capture ONLY —
no learning loop, no runtime consumption. Runtime/tests diff 0.

## Delivered

- **Feedback capture UI** — `web/src/components/review/
  FeedbackPanel.tsx`, section G of the Review Workspace (after
  the Decision Panel). Anchored on the Decision per ADR-018 /
  design v0.1 Option A: the form appears once the approval is
  decided (undecided → gate message, no form). Closed category
  set (REASONING / MISSING_INFORMATION / WRONG_RECOMMENDATION /
  EVIDENCE_ISSUE / KNOWLEDGE_GAP / UX_ISSUE — no free input),
  required description, optional evidence-refs (comma/newline) +
  expected-behavior. Submit disabled until valid; submit → await
  store → re-read list (no optimistic update); failure keeps the
  user's input with Retry. Feedback is OPTIONAL — reject without
  feedback remains allowed.
- **Feedback record model + storage** — `web/src/api/
  feedbackClient.ts`: the v0.1 design entity (id, decision_id
  `approval#decision`, approval_id, category, description,
  evidence_refs[], expected_behavior?, status="captured",
  created_by="local", created_at, provenance="governance-ui")
  behind a `FeedbackStore` interface. **GAP-27.7-01**: no backend
  feedback API exists and none was added (backend unchanged per
  phase rules) → first implementation is a browser-localStorage
  store (the "file-based storage abstraction" the rules allow);
  single-browser/single-reviewer MVP scope; a future POST/GET
  feedback endpoint is a drop-in swap of the client
  implementation.
- **Feedback read view** — existing records listed verbatim
  (category / id / created_by / created_at / description / refs /
  expected / anchor / status / provenance). No AI summary, no
  auto-attribution. Empty state "暂无反馈记录".

## Not Delivered (by design)

- Evaluation-case generation / curation (27.8 pipeline)
- Agent improvement / learning loop (nothing consumes feedback)
- Auto training / auto KB edits / auto skill suggestions
- Analytics / reviewer ranking / KPI
- Backend endpoint / DB schema (see GAP-27.7-01)

## Tests (5 new — FeedbackPanel.test.tsx)

Closed category set render + submit gating (category AND
description required) · valid submission persists + list re-renders
verbatim after the store round-trip (no optimistic update) + form
clears · failure keeps input + Retry (category selection
preserved) · capture gated on Decision (no form while
WAITING_HUMAN) · **SAFETY**: submitting feedback performs ZERO
HTTP calls, never mutates the approval record, and the stored
record is inert (status "captured", provenance governance-ui).

## Verification

Frontend: 113 passed / 2 skipped (e2e unchanged) · `tsc
--noEmit` clean · Backend battery: **596/0** · runtime/tests
diff **0** · Backend / workflow / approval state machine:
UNCHANGED.

## Gaps

- **G-27.7-01** No feedback backend API — localStorage capture
  (browser-local, not shared, not server-audited). Upgrade path:
  POST/GET feedback endpoint (backend work, separate
  authorization), client swap-in.
- G-27.5-4 identity gap carries over: created_by="local" until a
  who-am-I API exists.
- created_by/created_at trust boundary: local timestamps until
  the backend endpoint exists (acceptable for MVP validation
  goal: "will reviewers produce structured feedback?").

## Next Step

Phase 27.8 — Feedback → Evaluation Dataset Pipeline (curation of
captured records into eval-case candidates / knowledge tickets /
product backlog), contingent on 27.7 MVP validation with real
reviewers.
