# Phase 27.5-5 — Pilot Dashboard Result (2026-09-24)

Baseline phase26c-productionization-v1.0 (c7ed9c6). Read-only
OPERATIONAL visibility layer (not analytics): frontend aggregation
over the existing project-scoped approvals endpoint. Runtime diff
0 · backend business diff 0 · no new APIs.

## Delivered

**PilotDashboard** (`web/src/components/dashboard/
PilotDashboard.tsx`, new top-level "Dashboard" nav entry):
- **A 审批总览** — status count cards grouped by the EXACT backend
  status string (`countByStatus`): WAITING_HUMAN / PENDING /
  APPROVED / REJECTED / EXPIRED / RESUMED and ANY unknown status as
  its own verbatim card (e.g. `LEGAL_REVIEW_REQUIRED: 1`).
  Never merged, never renamed.
- **B 等待快照** — Waiting Human count, Oldest Waiting (backend
  created_at), Average Waiting (presentation arithmetic over
  created_at; "—" when not computable).
- **C 最近决定** — latest 5 resolved approvals: time, decision,
  approval id, reviewer (resolved_by), verbatim.
- **D 快速入口** — Open Review Queue / Open Pending Reviews →
  navigation only (no approve/reject/workflow triggers).
- Project-scoped selector (shared persisted key with the Review
  Queue — no global approvals endpoint, gap honored).
- Loading / Error(+Retry, never fake zeros — the overview is
  absent, not zeroed) / Empty ("No approval records available")
  states.

**App.tsx** — fourth mode `dashboard` + nav button; navigation to
the Review Queue resets detail/workspace state.

**API consumed (pre-existing)**: GET /api/projects/{id}/approvals
(frontend aggregation only). No new endpoints, no analytics
backend, no statistics tables.

## Tests (6 new — PilotDashboard.test.tsx)

countByStatus exact-grouping with unknown preserved verbatim ·
overview cards correct values + verbatim unknown card + recent
decisions · empty state distinct from error · API error → banner +
Retry, overview NOT rendered (no fake zeros) · quick-action
navigation · waiting snapshot (count + computed average).

## Safety verification

Runtime modified: NO · Backend modified: NO · New analytics
backend: NO · Fake metrics: NO · Workflow changed: NO ·
No reviewer ranking / productivity / SLA / scoring (explicitly out
of scope).

## Quality gates

Frontend: 108 passed / 2 skipped (e2e precondition unchanged) ·
`tsc --noEmit` clean · Backend battery: **596/0** · runtime/tests
diff **0**.

## Known Gaps

- No global approvals endpoint → project-scoped aggregation only
  (same G-27.5-2-01).
- No historical trend data (single snapshot per load).
- No reviewer identity statistics (by design — out of scope).
- Average waiting is session-clock arithmetic, not a backend SLO.

## Next Step

UI V0.1 MVP (27.5-2..5) is now functionally complete: Queue →
Detail → Workspace(+Evidence) → Decision, plus Dashboard. Awaiting
authorization for: commit of the whole 27.5 UI track, and/or the
next phase (e.g. feedback capture / review-form integration, or
the minimal backend gaps: global approvals + project/case detail +
approval→run linkage).
