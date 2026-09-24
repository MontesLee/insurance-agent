# Phase 27.5-4 — Approval Workflow UI Result (2026-09-24)

Baseline phase26c-productionization-v1.0 (c7ed9c6). Human decision
layer on top of the read-only Workspace: UI-only, consuming the
EXISTING Phase 9 mutation endpoints. Runtime diff 0 · backend
business diff 0 · no workflow redesign.

## Delivered

**DecisionPanel** (`web/src/components/review/DecisionPanel.tsx`,
embedded in ReviewWorkspace as section F, after the evidence
chain):

- Current status badge VERBATIM (unknown statuses render exactly —
  e.g. `LEGAL_REVIEW_REQUIRED`); reviewer shown as the backend
  `resolved_by` when present, else "—" (no identity API — gap
  honored, no invented identity).
- **Approve flow**: click → explicit confirmation ("确认批准?此
  操作将记录你的决定") → POST → success note → re-read the
  backend approval record (`onDecided` triggers the workspace's
  approval re-fetch). NO optimistic state flip; the badge only
  changes when the backend says so.
- **Reject flow**: comment REQUIRED (`trim().length > 0`; the
  button stays disabled with a hint until filled) → POST with the
  reason in the existing `reason` body field.
- **Failure**: banner with the backend error + Retry; the status
  badge keeps showing the true prior state (verified by test).
- **Decided approvals**: immutable decision record (decision /
  reviewer / time / status from the backend record) with the
  action buttons REMOVED (no re-submission, no editing).
- Submitting state disables both buttons until the API responds.

**client.ts**: `approveApproval` / `rejectApproval` → the
pre-existing `POST /api/approvals/{id}/approve|reject` (REVIEWER
role enforced server-side; `actor` is overridden by the
authenticated identity when authn is on — backend contract,
unchanged).

## API

Consumed (all pre-existing): GET /api/approvals/{id} ·
POST /api/approvals/{id}/approve · POST /api/approvals/{id}/reject
Missing (documented, NOT invented): current-identity endpoint
("who am I") · multi-entry decision/audit history endpoint (the
record carries a single resolved entry) · per-decision comment
field distinct from the approval `reason` (decision-time comment
rides the existing reason field; noted in the record display).

## Tests (7 new — DecisionPanel.test.tsx)

Panel rendering with verbatim status + "—" reviewer · approve
confirmation gate (no API call before confirm; success → onDecided
re-read) · reject validation (empty comment disabled; valid
comment submitted with reason) · API error → banner + Retry with
NO fake status update · already-decided → immutable history, no
buttons · unknown status verbatim · submitting state disables
buttons mid-flight. Plus one scoped-query fix in the 27.5-3
workspace test (two badges now exist legitimately).

## Safety verification

Runtime modified: NO · Backend business logic modified: NO ·
Approval state machine modified: NO (backend transitions only) ·
Fake approval data: NO · No optimistic approval · No silent
failure · No editing of recorded decisions · No agent/rerun/
output-editing features.

## Quality gates

Frontend: 102 passed / 2 skipped (e2e precondition unchanged) ·
`tsc --noEmit` clean · Backend battery: **596/0** · runtime/tests
diff **0**.

## Known Gaps

- No current-user API → pre-decision reviewer shows "—".
- No audit-history endpoint → the decision record is the single
  resolved entry (decision/reviewer/time/status).
- Decision comment is stored via the existing `reason` channel
  (the record display notes this honestly).
- No Request-Revision / Modify / rerun actions (explicitly out of
  scope by phase rules).

## Next Step

Phase 27.5-5 — Pilot Dashboard (read-only counts: pending/
approved/rejected per project + review progress; frontend
aggregation over existing endpoints).
