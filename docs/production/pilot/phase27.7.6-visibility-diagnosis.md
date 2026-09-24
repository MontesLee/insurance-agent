# Phase 27.7.6 — Pilot Approval Data Visibility Diagnosis

Date: 2026-09-24 · Method: read-only investigation (zero code /
runtime / backend / data changes)

---

## 1. Symptom

User opened the Web UI and found:

- Review Queue: no items visible
- Dashboard: empty

Expected: Phase 27.7.5's R1–R6 approvals should be visible.

## 2. Root Cause

** TWO contributing causes (both user-side, not a code bug):**

### Primary: Project ID not loaded (UI shows IDLE state)

The Review Queue and Dashboard both require the user to enter a
project ID (`pilot-2775-feedback-validation`) and click 加载.
On a **new browser profile** (or after clearing localStorage),
the key `webui:review-project` is empty → the components show
their IDLE state ("输入项目 ID 并点击加载"), which visually reads
as "empty" but is actually a **pre-load state**, not a data
absence.

The AI session used a bridgic-browser profile that had the
project ID persisted; a human opening the app for the first time
in their own browser sees the IDLE state.

### Secondary: All 6 approvals are already RESOLVED

The AI operator session decided all R1–R6 (3 APPROVED, 3
REJECTED). They still appear in the queue list (after actionable
items) and in the Dashboard count cards — but there are **zero
WAITING_HUMAN items**, so a reviewer looking for "something to
do" would find nothing pending.

**Classification: Other (UX onboarding gap, not a data or code
bug).** The data is present, the API works, the environment is
correct — but the UI has no way to discover the project ID
without being told, and the staged data has already been
consumed by the AI session.

## 3. Evidence

### Data on disk (approvals.jsonl)

| id | project_id | status | created_at |
|---|---|---|---|
| appr_770fe375a8 (R1) | pilot-2775-feedback-validation | APPROVED | 2026-09-24T05:07:46Z |
| appr_26515f2eb2 (R2) | pilot-2775-feedback-validation | REJECTED | 2026-09-24T05:07:46Z |
| appr_d6e775f8d2 (R3) | pilot-2775-feedback-validation | APPROVED | 2026-09-24T05:07:46Z |
| appr_c617423da9 (R4) | pilot-2775-feedback-validation | REJECTED | 2026-09-24T05:07:46Z |
| appr_8f8d246c1d (R5) | pilot-2775-feedback-validation | APPROVED | 2026-09-24T05:07:46Z |
| appr_19567833c0 (R6) | pilot-2775-feedback-validation | REJECTED | 2026-09-24T05:07:46Z |

### API verification (live, read-only)

```
GET /api/projects/pilot-2775-feedback-validation/approvals
→ HTTP 200, count: 6, all resolved (APPROVED×3, REJECTED×3)
```

Backend running on 127.0.0.1:8000 ✓ · Frontend on :5173 ✓

### Frontend data flow (code-verified)

```
ReviewQueue / PilotDashboard
  → localStorage.getItem("webui:review-project")
  → if empty → IDLE state (looks like "empty")
  → if set → api.approvals(pid) → renders items
```

No global project-list endpoint exists → the UI cannot discover
projects on its own (G-27.5-2-01, known).

### Environment match

Backend harness root: `tmp/webui-runs/harness-projects/` —
contains `pilot-2775-feedback-validation/` with the 6 records.
Same environment as the AI session. **No mismatch.**

## 4. Recommended Fix (proposed only, not implemented)

1. **For the human session**: stage 6 NEW WAITING_HUMAN approvals
   (the current ones are consumed). Run the staging script, then
   have the human open the UI and enter the project ID.

2. **Product fix (future)**: add a project-list endpoint
   (`GET /api/projects`) so the queue can offer a dropdown
   instead of requiring a memorized ID. This is the highest-value
   UX gap (G-27.5-2-01) for the governance product.

3. **Minor UX**: when there are no WAITING items but resolved
   ones exist, show a summary ("6 已处理, 0 待审") instead of
   what can read as "empty".

## Safety Verification

```
Code changed: NO
Runtime changed: NO
Backend changed: NO
Data changed: NO
```
