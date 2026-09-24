# UI Current State Audit — Phase 27.5-1 (2026-09-24)

Baseline: phase26c-productionization-v1.0 (c7ed9c6). Method:
code-first (web/src + runtime/server.py + runtime/auth.py), zero
modifications. Evidence hierarchy: code > tests > runtime evidence
> docs.

## What exists (verified in code)

**Stack**: React 18 + TypeScript + Vite (`web/`), Tailwind-style
classes, no router (single page, localStorage mode switch), Vitest
component tests + 2 e2e flows (chat-flow, runtime-chain).
**Backend**: FastAPI (`runtime/server.py`), API-Key auth
(Authorization header; production modes refuse unauthenticated
start), CORS configured. Roles OWNER/REVIEWER/OPERATOR exist in
runtime/auth.py; `_require_role` guards only diagnostics/metrics.

**App shell (App.tsx)**: header + two modes — chat (default) /
developer. Tagline: "chat-first agent system · 同一 Runtime,两种视
图". UI-observes-only rule is stated in code comments and honored:
frontend state = projection of SSE RuntimeEvents (useRunStream +
runReducer), no local business-state derivation.

**Chat mode (User)**: ChatSidebar (history) → WelcomeScreen /
Conversation (streaming replies, Markdown, embedded ArtifactCards)
→ Composer (POST /api/chats/{id}/messages[/stream]) + collapsible
AgentInspectorPanel (agent activity, tools, artifacts). Drives the
multi-agent chat runtime (runtime/agent/, planner + tools +
FakeLLM test mode).

**Developer mode**: CasesSidebar (case list + Start Run → POST
/api/runs) → main RunOutput (final report stage output) →
RuntimeInspector right panel containing Pipeline (8 stages),
EvalPanel, TraceTimeline, ArtifactInspector — all fed by SSE
(`/api/runs/{id}/stream` + events/artifacts polling).

**API surface the UI actually consumes** (web/src/api/client.ts,
107 lines): health, cases, agent/config, chats CRUD+messages,
createRun/getRun/events/artifacts/stream. That is ALL.

## Capability Matrix

| Capability | Current | Evidence | Pilot need | Gap |
|---|---|---|---|---|
| Chat intake | ✅ works | ChatLayout+Composer+client.ts | medium (advisors) | none for pilot |
| Case management | ⚠️ list+start only | CasesSidebar; no create/edit/close | high | no case CRUD, no status/owner columns |
| Run visibility | ✅ per-run live | SSE + Pipeline | high | no runs LIST per case/history (sidebar = runs, not cases, in practice) |
| Pipeline view | ✅ 8-stage live | Pipeline.tsx in RuntimeInspector | high | buried in right panel; not the primary reading surface |
| Artifact view | ✅ inspector | ArtifactInspector | high | JSON-ish presentation; no business-friendly rendering |
| Evidence view | ⚠️ indirect | artifact cards / knowledge-evidence artifact | HIGH (reviewer core) | no dedicated evidence-chain view; no source linking UI |
| Recommendation review | ❌ none | rec artifact raw only | HIGH | no fit/reason/uncertainty presentation, no primary-vs-not-rec comparison |
| Approval | ❌ NOT IN UI | server endpoints exist (/api/approvals, approve/reject) — client.ts never calls them | HIGH (pilot gate) | **biggest gap**: no review queue, no approve/reject buttons |
| Human feedback | ❌ none | — | HIGH (Phase 27 packet!) | no review form/comment capture — currently markdown files |
| Report view | ⚠️ RunOutput | final stage output | medium | raw; no export/print |
| Dashboard | ❌ none | — | medium | no pilot overview |
| Metrics | ❌ not consumed | /api/metrics exists, role-guarded | low-med | not wired |
| Runtime status | ⚠️ health only | /api/health | low | — |
| Queue status | ❌ none | queue APIs not behind HTTP at all | low (internal) | backend wiring absent (26B note) |
| Budget visibility | ❌ none | budget in PG, no API | low (pilot) | backend wiring absent |
| Recovery visibility | ❌ none | reconcile_once is operator-side | low | — |
| User permission | ⚠️ API-key + roles | auth.py; only 2 endpoints role-guarded; no UI login/role display | medium | no identity in UI; some endpoints unguarded (known P1-02) |
| Audit trail | ❌ not surfaced | queue_ops_events/recovery_events in PG | medium | no API/UI |

## Key structural finding

The UI was built for the CHAT runtime + harness runs. The pilot's
core loop (open case → read analysis → check evidence →
approve/reject → leave feedback) has **no dedicated UI**: approvals
exist only as backend endpoints, and the Phase 27 review packet is
markdown files filled by hand. Developer mode is an ENGINE DEBUG
view (right-panel inspector), not a business review workspace.
