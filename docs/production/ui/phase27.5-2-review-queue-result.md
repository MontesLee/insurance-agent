# Phase 27.5-2 — Review Queue UI Result (2026-09-24)

Baseline phase26c-productionization-v1.0 (c7ed9c6). UI-layer only:
backend / runtime / agents / skills / schemas ZERO changes
(git-verified). Follows the 27.5-1 plan step 1.

## Implementation

New (web/src):
- types/approval.ts — ApprovalRecord, VERBATIM projection of the
  backend ApprovalRequest dict (runtime/approval/models.py).
- api/client.ts — additions only: approvals(projectId) → GET
  /api/projects/{id}/approvals; getApproval(id) → GET
  /api/approvals/{id}. Both endpoints pre-existed unused.
- components/review/ReviewQueue.tsx — the reviewer entry page:
  persisted project-id selector + queue list (client name / reason,
  project, task, request_type, stage from context, created time,
  waiting duration [presentation arithmetic over backend
  created_at], decision), verbatim status badges
  (PENDING/WAITING_HUMAN/APPROVED/REJECTED/EXPIRED/RESUMED —
  unknown statuses render verbatim, never remapped), actionable-
  first + newest ordering (presentation only), loading state,
  error banner with Retry (no silent fallback), empty state.
- components/review/ApprovalDetail.tsx — PLACEHOLDER detail (per
  phase plan: full Review Workspace is 27.5-3): read-only record
  view via /api/approvals/{id} + back-to-queue.
- App.tsx — added "review" mode + top nav (对话 / 审核队列 /
  Developer). Chat and Developer modes untouched internally.

## API Used (all pre-existing; no backend modification)

GET /api/projects/{project_id}/approvals · GET /api/approvals/{id}

## UI Flow

App → 审核队列(nav)→ 输入/选择项目 ID(持久化)→ 队列列表 →
点击条目 → Approval Detail(占位)→ 返回队列。

## Tests

New: web/src/components/review/ReviewQueue.test.tsx — 5 cases:
(1) 3-item list rendered with verbatim statuses + actionable-first
ordering + count; (2) empty state (not an error); (3) API error →
failure banner + Retry; (4) click → onOpenApproval(approval_id);
(5) unknown backend status renders verbatim (no silent mapping).
Frontend suite: 89 passed / 2 skipped(e2e, unchanged precondition).
tsc --noEmit clean. Backend battery re-run: 596/0 (unchanged).

## Known Gaps (recorded, deliberately not fixed)

- API GAP G-27.5-2-01: no global approvals / project-list endpoint
  (backend can scan harness roots; frontend cannot) → queue is
  project-scoped with a manual project-id selector. Minimal future
  backend addition: GET /api/approvals (aggregate) — needs separate
  authorization.
- Client name / current stage are NOT first-class fields in the
  approval record; shown from context when present, else "—"
  (backend shape unchanged by design).
- Prompt's example status vocabulary (WAITING/CANCELLED) differs
  from the backend's actual vocabulary (WAITING_HUMAN, no
  CANCELLED); UI uses the BACKEND vocabulary verbatim per the
  observes-only rule.
- Detail page is a placeholder (by plan); approve/reject controls
  are 27.5-4.
- Approvals surfaced here belong to the Phase 9 harness runtime;
  the 26C queue-path approvals (QueueOps) are not HTTP-exposed yet
  (pre-existing 26B note).

## Next Step

Phase 27.5-3 — Review Workspace: Case Detail main-document view
(客户画像/需求/风险/缺口/方案/推荐/证据链/报告拼装自现有
cases/runs/artifacts 端点,零后端改动)。
