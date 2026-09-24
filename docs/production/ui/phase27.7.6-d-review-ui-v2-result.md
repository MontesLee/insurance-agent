# Phase 27.7.6-D — Human Review UI v2 (Risk-based Review Console)

Date: 2026-09-24 · Adapts the Human Review Console to the Phase
27.7.6 v2 Review Card layer. Zero changes to Chat UI, Agent runtime
UI, Developer Mode, orchestrator, skills, or the approval state
machine.

## 1. UI flow (before → after)

```
BEFORE (artifact-centric)             AFTER (task-centric)
Queue: approval rows                  Queue: RISK TASK rows
  ↓ open                                ↓ open (level visible BEFORE the click)
Detail placeholder                    Detail placeholder (unchanged)
  ↓ workspace                           ↓ workspace
Workspace A..G                          Workspace A · 审批摘要
  reviewer hunts the run,                 A2 · Review Card  ← NEW (risk entry)
  reads raw artifacts                      B · 案例上下文
                                           C/D/E · evidence drill-down (kept)
                                           F · 决定 (now 3 actions)
                                           G · 反馈
```

The reviewer's first read is now the **card** (level, validation,
findings); artifacts C/D/E remain one scroll away as evidence
drill-down — nothing was removed, only re-ranked.

## 2. Backend addition (read-only)

`GET /api/runs/{run_id}/review-card` (`runtime/server.py`):

- Loads the evaluation-layer generator once (importlib — same idiom
  as the bench runner; `evaluation/human-review/` is hyphenated, not
  a package) and computes the card **in memory**. Nothing is written
  to the run dir (tested).
- Keyed by the run **directory**, not the in-memory run registry —
  cards survive backend restarts (deliberate difference from the
  registry-bound `/events` + `/artifacts` endpoints).
- Path-traversal guard `_SAFE_RUN_ID` (run ids are
  `[A-Za-z0-9_-]{1,64}`; anything else 404s before touching disk).
- No state change, no new decision semantics, approval endpoints
  untouched.

## 3. Frontend changes

| File | Change |
|---|---|
| `web/src/types/reviewCard.ts` | NEW — verbatim card types |
| `web/src/api/client.ts` | + `reviewCard(runId)` |
| `web/src/components/review/ReviewCardView.tsx` | NEW — shared `RiskLevelBadge` / `ValidationChips` / `topIssue` / `ReviewCardDetail` |
| `ReviewQueue.tsx` | Risk-task rows (level badge, 4 validation chips, top issue, sampling marker) + filters **All / High Risk / Need Review / Random Audit**. Cards fetched per linked run (`Promise.allSettled` — one failure never blocks the list); no run context → "无 Review Card"; fetch failure → "加载失败" hint. Filter semantics: high = DEEP_REVIEW or HIGH flag; need = backend ACTIVE status (authority); audit = `sampling.triggered`. |
| `ReviewWorkspace.tsx` | NEW section **A2 · Review Card** (auto-linked via `review_context.run_id` from 27.7.6-C; loud error + Retry on fetch failure; "无 Review Card" placeholder without run context). C/D/E untouched. |
| `DecisionPanel.tsx` | NEW action **Request Fix 退回修正** (comment required + confirm gate). Recorded via the EXISTING reject endpoint with reason prefix `REQUEST_FIX: ` — the V0.1 approval state machine has no NEED_FIX state (ADR-017 frozen), so the semantic lives in the auditable reason. GAP-27.7.6D-01 recorded. |

Reviewer action records (section 5 of the proposal): decisions land
in the immutable backend approval record (actor/reason/timestamp);
structured feedback stays in G 节 — both unchanged, both future
eval-dataset sources.

## 4. Tests

Backend (`tests/runtime/test_agent_api.py` →
`test_review_card_endpoint`): finished run → 200 with closed
vocabulary + internal consistency (validation_status ⇔ 4 dims;
required ⇒ not AUTO_PASS); repeat GET stable; **run dir untouched**
(no `human_review_card.json` written); unknown run 404; path
traversal refused.

Frontend: queue +6 (verbatim card chips/issues, 3 filters,
filtered-empty, card-failure degradation), workspace +3 (A2 verbatim
render, loud card error, no-card placeholder), decision +1
(request_fix: comment gate + confirm gate + REJECT-with-prefix call).
All pre-existing tests unchanged and green.

| Gate | Result |
|---|---|
| `npx vitest run` (web) | **130 passed / 2 skipped** |
| `tsc --noEmit` | clean |
| `pytest tests/runtime -q` | **598 passed / 0 failed** (597 + 1 new) |
| `pytest tests/eval -q` | 12 passed (unchanged) |

## 5. Live verification (real browser, real pilot data)

Backend + vite restarted clean; project `pilot-2776-human-reviewer`
(HR-R1..R6, all WAITING_HUMAN) loaded through the real UI:

- Queue rendered all 6 cards from the real runs: SUMMARY_REVIEW rows,
  a DEEP_REVIEW · VALIDATION FAIL row (Evidence FAIL chip + issue
  line + evidence ref), a fail-closed card row (all four FAIL,
  未落盘), one sampling-hit marker. Filters present.
- Workspace for the empty-KB case rendered A2 fully: DEEP badge,
  Evidence FAIL chip, customer context (nulls as —), "主推荐:无(见
  风险标记)", HIGH/MEDIUM findings with evidence refs, failed-checks
  panel, 触发依据 reasons, run-linked indicator, and the 3-action
  decision panel.
- Screenshots: `docs/production/ui/phase27.7.6-d-screenshots/`
  (`review-queue-risk.png`, `review-workspace-card.png`).

Known interaction (pre-existing, not a regression): `/events` and
`/artifacts` are bound to the in-memory run registry, so after a
backend restart sections C/D for pre-restart runs show a loud
Retry-able error; the card endpoint is disk-keyed and unaffected.

## 6. Gaps recorded

- **G-27.7.6D-01** — Request Fix reuses REJECT + reason prefix; a
  native NEED_FIX approval state needs a state-machine change
  (out of scope under ADR-017 freeze).
- **G-27.5-2-01** (no project-list endpoint) and
  **G-27.7.6C-01** (harness approvals lack run_id) unchanged.
- Queue fetches one card per linked approval (N requests); a batch
  projection would be nicer at pilot scale >50 items.

## 7. STOP

Phase complete. Not started: human reviewer session, Phase 27.8.
