# Phase 27.7.6-C — Approval Context Auto-Link Result (2026-09-24)

Read-only linkage of **approval → run → artifacts → evidence** so the
Human Reviewer never sees or types an internal run id. Scope guard:
the linkage is a projection of data the approval already carries at
creation time — no state machine change, no Runtime change, no
automatic decision.

## 1. Problem

Phase 27.7.6 Human Reviewer Pilot confirmed gap G-27.5-3-02: the
Review Workspace sections C/D/E (timeline, artifacts, evidence chain)
were keyed by a **manual run-id input** persisted in localStorage.
Reviewer flow was:

```
Approval → 人工寻找 Run → 加载证据 → 审核
```

Even though every approval created via
`create_request(context with run_id)` already stores `run_id`
(and optionally `artifact_ids`) in `approval.context`
(`runtime/approval/models.py` — `context` field), the API exposed
none of it and the UI demanded the reviewer reconstruct it.

## 2. Before / After architecture

Before:

```
GET /api/approvals/{id}
  → { project_id, approval }          # context opaque to reviewer

ReviewWorkspace
  → manual "workspace-run-input" + localStorage run id
  → sections C/D/E inert until reviewer types run id
```

After:

```
create_request(context with run_id)          (unchanged)
  → ApprovalStore.append / ApprovalManager.wait (unchanged)
GET /api/approvals/{id}
  → { project_id, approval,
      review_context: { run_id?, artifact_ids? } }   # read-only projection

ReviewWorkspace
  → reads review_context.run_id (falls back to approval.context.run_id)
  → auto-loads /api/runs/{id}/events, /api/runs/{id}/artifacts,
    evidence chain — zero reviewer input
```

Backend projection is data-source-faithful: it copies fields already
present in the stored approval context — nothing is recomputed,
looked up by time, or guessed.

## 3. API changes

`GET /api/approvals/{approval_id}` (`runtime/server.py` —
`get_approval`):

```json
{
  "project_id": "pilot-2776-human-reviewer",
  "approval": { "...": "stored record, verbatim" },
  "review_context": {
    "run_id": "run_9de5882e",
    "artifact_ids": ["art_1", "art_2"]
  }
}
```

- Absent run/artifact context → `review_context` is `{}` (empty object,
  never guessed).
- `GET /api/projects/{id}/approvals` (list) is **unchanged** — the
  projection lives on the detail endpoint the Workspace consumes.
- No new endpoints, no status codes, no request-body changes.
  Approval POST endpoints (`/approve`, `/reject`) untouched.

Frontend types: `ApprovalDetailResponse.review_context?`
(`web/src/types/approval.ts`).

## 4. UX improvement (`web/src/components/review/ReviewWorkspace.tsx`)

- Manual run-id input and its localStorage persistence **removed**;
  no reviewer-facing ID entry remains.
- Section A area now shows a linkage indicator:
  `已自动关联运行: run_xxx`（来自审批上下文，审核者无需输入）
  or, when unlinkable, `Run information unavailable` — never a guess.
- Sections C/D/E auto-load once the approval resolves; a
  "Run context unavailable" per-section fallback replaces the old
  manual gate and never demands input.
- Section D lists `review_context.artifact_ids` (raw context as
  compatibility fallback).
- Errors are loud: timeline or artifact fetch failure renders
  `加载失败: …` + **Retry** (retry recovers without re-entering
  anything). No silent-empty path exists; with no run context no
  `/api/runs/*` request is issued at all.
- Section E keeps the existing provenance join
  (recommendation → requirement/risk/knowledge evidence); missing
  links render `No evidence linked` verbatim — no generated
  explanation.

Reviewer flow is now:

```
Approval → 自动展开 Review Context → 证据链完整呈现 → 审核
```

## 5. Tests

Backend (`tests/runtime/test_approval.py` —
`test_api_approval_review_context`):

1. approval with `run_id` + `artifact_ids` → `review_context` projected
   verbatim;
2. approval without `run_id` → `review_context == {}`;
3. repeated GET leaves the stored approval byte-identical
   (status still `WAITING_HUMAN`, context/decision/resolved_*
   unchanged) — projection is read-only;
4. 404 for unknown approval still works (existing test).

Frontend (`web/src/components/review/ReviewWorkspace.test.tsx`,
rewritten — it still drove the removed manual input):

1. workspace auto-loads timeline/artifacts/evidence with **no manual
   run-id input** (asserts `workspace-run-input`/`workspace-run-load`
   are gone);
2. legacy approval without `review_context` still auto-links via
   `approval.context.run_id` (compatibility);
3. missing run context → `Run information unavailable` in C/D/E and
   **zero** `/api/runs` requests;
4. timeline error shows `加载失败` + Retry, retry recovers;
5. artifacts error shows `加载失败` + Retry (not silent empty);
6. evidence chain flags missing refs as `No evidence linked`; empty
   recommendation → `No evidence linked`;
7. section A/B read-only rendering assertions retained.

## 6. Verification

| Gate | Result |
| --- | --- |
| `npx vitest run` (web) | 120 passed / 2 skipped (e2e) |
| `tsc --noEmit` | clean |
| `python -m pytest tests/runtime -q` | **597 passed / 0 failed** (596 baseline + 1 new) |

Safety confirmation:

```
Runtime modified (execution logic):        NO  — only the read-only
   GET projection in server.py touched; harness/run_manager/bus untouched
Agent skills modified:                     NO
Approval state machine modified:           NO  — runtime/approval/* unmodified
Automatic decision (approve/reject):       NO
Stored approval records reshaped:          NO  — projection only at response time
```

Diff scope: `runtime/server.py`, `web/src/components/review/ReviewWorkspace.tsx`,
`web/src/components/review/ReviewWorkspace.test.tsx`,
`web/src/types/approval.ts`, `tests/runtime/test_approval.py`.

## 7. Remaining gaps (recorded; out of scope here)

- **G-27.7.6C-01** — Harness-generated final-review approvals
  (`runtime/harness/harness.py`, `context={"artifact_ids", "task_types"}`)
  do not yet include `run_id`; only staged pilot approvals carry it.
  Closing this requires touching the approval *creation* context,
  which this phase deliberately excludes (禁止改变 Runtime 执行逻辑).
- **G-27.7.6C-02** — Replan-type approvals have no run/artifact
  context by nature; reviewers see
  `Run information unavailable` for them (correct, not a bug).
- **G-27.7.6C-03** — Approvals list endpoint does not project
  `review_context` (detail-only); queue-level run badges would need it.
- G-27.5-3-01 (section B case fields `—`, no project/case GET
  endpoint) remains open and unchanged.

## 8. STOP

Phase complete. NOT started (awaiting authorization):
new reviewer data staging, Phase 27.7.6 Human Reviewer Validation
re-run, Phase 27.8.
