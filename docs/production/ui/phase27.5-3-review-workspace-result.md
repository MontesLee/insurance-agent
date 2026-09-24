# Phase 27.5-3 — Review Workspace Result (2026-09-24)

Baseline phase26c-productionization-v1.0 (c7ed9c6). Read-only UI
layer: runtime diff 0, backend business diff 0, no approval
actions (those are 27.5-4), no fabricated data.

## Delivered

**Components**
- `web/src/components/review/ReviewWorkspace.tsx` (NEW) — the
  five-section read-only aggregation view:
  - **A 审批摘要** — /api/approvals/{id}: id/type/status (verbatim
    badge)/created/waiting duration/reason/task/project/stage/
    decision; missing fields render "—".
  - **B 案例上下文** — supervisor (/api/projects/{id}/supervisor:
    status/risk_level/updated_at). Customer/case fields render "—"
    with an explicit note (no project/case GET endpoint exists —
    gap G-27.5-3-01).
  - **C Agent 执行时间线** — /api/runs/{id}/events projected into a
    chronological timeline (run_started / stage_started →
    stage_completed | stage_failed rows: actor = skill, run id,
    verbatim status, start/end times, presentation-only duration).
  - **D 生成的产物** — /api/runs/{id}/artifacts list + click-through
    read-only payload viewer (/api/runs/{id}/artifacts/{type});
    harness deliverable ids from the approval context shown when
    present.
  - **E 证据链** — joined from REAL artifact payloads:
    product-recommendation provenance refs (requirement / risk /
    knowledge) → knowledge-evidence entries (content + source).
    Missing knowledge refs are flagged "No evidence linked" and the
    ref id is still shown — never fabricated.
  - Sections C–E are keyed by a persisted run-id selector because
    no approval→run linkage exists in the backend (gap
    G-27.5-3-02).
- `ApprovalDetail.tsx` — upgraded with the "查看 Review Workspace"
  entry (passes project+approval ids).
- `App.tsx` — review-mode navigation extended: Queue → Detail →
  Workspace with back-stack.
- `web/src/api/client.ts` — added `supervisor(projectId)` (existing
  endpoint, previously unconsumed). `types/approval.ts` —
  SupervisorState (verbatim projection).

**APIs consumed (all pre-existing)**: GET /api/approvals/{id} ·
GET /api/projects/{id}/supervisor · GET /api/runs/{id}/events ·
GET /api/runs/{id}/artifacts · GET /api/runs/{id}/artifacts/{type}

**Tests added** — ReviewWorkspace.test.tsx (6): Section A verbatim
status + "—" handling; Section B supervisor fields + gap marks;
Section C timeline ordering + verbatim statuses; Section C error →
retry (no silent empty); Section D artifact list; Section E chain
rendering + missing-evidence flagging without fabrication.

## Quality gates

Frontend: 95 passed / 2 skipped (e2e unchanged precondition) ·
`tsc --noEmit` clean · Backend battery re-run: **596/0** ·
runtime/tests diff: **0**.

## Architecture safety

Runtime modified: NO · Backend modified: NO (client additions only
consume existing endpoints) · Approval workflow modified: NO ·
No fake data (missing → "—" / "No evidence linked") · No approval
action (read-only).

## Known Gaps (recorded; no backend changes made)

- **G-27.5-3-01**: no GET /api/projects/{id} or /api/cases/{id}
  endpoint → Section B customer/case fields unavailable ("—").
  Future: minimal project/case detail endpoint.
- **G-27.5-3-02**: no approval→run linkage (approval context
  carries harness artifact_ids/task_types, never a pipeline run
  id) → sections C–E need a manual run-id selector. Future: run id
  (or case id) in the approval context, or a linkage endpoint.
- Supervisor record is project-level (no per-agent timeline) →
  Section C uses the pipeline run event stream instead.
- Section C "agent name" is the stage skill; harness-runtime
  approvals predate pipeline-run linkage entirely.
- 27.5-4 requirements queued: approve/reject controls + required
  comment + review-time capture + reviewer identity surfacing.

## Next Step

Phase 27.5-4 — Approval Workflow UI (consume POST
/api/approvals/{id}/approve|reject with REVIEWER role; feedback
capture as pilot evidence; auto review-timing).
