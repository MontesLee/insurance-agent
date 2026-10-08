# API Contract Audit — Phase 27.7.6-E (audit) / 27.7.6-F (fix applied)

Date: 2026-09-24 · Method: code map (client.ts ↔ runtime/server.py) +
live matrix (backend :8000 via vite proxy :5173, the exact browser
path) · Evidence run: disk-only `run_9de5882e` (pre-restart, staged
HR pilot) vs in-memory `run_124ec762` (created live, bm-complete-001).

**STATUS: the Cause-A fix landed as Phase 27.7.6-F** (registry OR
persisted-dir gate for the four read endpoints; restored summary for
GET /runs/{id}; deterministic trace.jsonl replay for /events; disk
case-dir resolution for artifacts). After-matrix (live, same disk-only
run): `/runs/{id}` 200 · `/events` 200 · `/artifacts` 200 ·
`/artifacts/{type}` 200 · `/review-card` 200 · unknown id 404 ·
trace-only run (no case_state) `/events` 200. Regression:
`test_run_read_endpoints_survive_restart` proves replayed event ids/
order/length equal the pre-restart stream and stage events are
dict-identical. `/stream` remains registry-bound by design (live-only
consumer; a restored SSE would hang on keep-alive).

## 1. Symptom → dimension mapping

| Reported error | Pages | Network layer meaning |
|---|---|---|
| `Cannot reach the runtime server (TypeError: Failed to fetch)` | Review Queue, Dashboard | fetch never got an HTTP response — **backend process unreachable**, not a route problem |
| `加载失败: API error 404` | Workspace C (timeline), D (artifacts) | Backend REACHED and answered 404 — **run not in the in-memory registry** |

Both were observed in one session because they happened at different
moments: servers were down at queue/dashboard load time; later the
backend was up (all queue/dashboard endpoints 200 — verified), and C/D
still 404 for the staged HR runs.

## 2. Contract audit table (every Web-consumed call)

| UI module | API request | Backend route (server.py) | Live run (in-memory) | Disk-only run (pre-restart) | Restart impact |
|---|---|---|---|---|---|
| health checks | GET /api/health | `health` | 200 | 200 | none |
| Demo case list | GET /api/cases | `list_cases` | 200 | 200 | none |
| Review Queue / Dashboard | GET /api/projects/{id}/approvals | `list_project_approvals` | 200 | 200 | none (disk: ApprovalStore) |
| Dashboard / Workspace B | GET /api/projects/{id}/supervisor | `get_supervisor` | 200 | 200 | none (disk: ControlStore) |
| Workspace A / Detail | GET /api/approvals/{id} | `get_approval` | 200 | 200 | none (disk scan) |
| Decision F | POST /api/approvals/{id}/approve \| /reject | `approve/reject_approval` | 200 | 200 | none |
| **Workspace A2 (card)** | GET /api/runs/{id}/review-card | `get_review_card` | **200** | **200** ✓ | **none — disk-keyed by design (27.7.6-D)** |
| **Workspace C (timeline)** | GET /api/runs/{id}/events | `get_events` | 200 | **404** ✗ | bus history + `_require_run` registry both memory-only |
| **Workspace D (artifacts)** | GET /api/runs/{id}/artifacts[/{type}] | `get_artifacts`/`get_artifact` | 200 | **404** ✗ | gate `_require_run` memory-only — **the data itself is already read from disk** (`mgr.artifacts_of` → `state_store.load(run_dir)`); only the gate blocks |
| Run header / Pipeline | GET /api/runs/{id} | `get_run` | 200 | **404** ✗ | registry-only metadata |
| Live SSE | GET /api/runs/{id}/stream | `stream_run` | 200 | 404 | registry-only (UI uses it for LIVE runs only; not among the 4 symptoms) |
| Chat UI | GET/POST /api/chats[...] | chat handlers | 200 | n/a | ChatManager memory-only (adjacent debt, not in scope) |
| Demo trigger | POST /api/runs | `create_run` | 201 | n/a | creates new run (fine) |

All frontend URLs match backend routes **exactly** — no path drift,
no migrated API. The only failing dimension is the run lifecycle.

## 3. Root cause

**Cause A — C/D `API error 404` (the contract regression):**
`_require_run()` gates `/api/runs/{id}`, `/events`, `/artifacts`,
`/artifacts/{type}`, `/stream` on `RunManager._runs`, a dict that
starts empty in every backend process. Any run whose directory exists
under `tmp/webui-runs/` but was created before the current process
(every staged HR run after a backend restart) 404s — while
`review-card` (keyed by run directory, introduced 27.7.6-D) and all
approval/supervisor reads (disk stores) keep working. Result in the
UI: A2 renders the card, C/D directly below it show 404 — exactly the
reported split. This is the known architecture debt recorded since
27.7.6-C/D ("registry-bound endpoints"), now user-visible.

**Cause B — Queue/Dashboard `Failed to fetch` (process lifecycle, not
contract):** the backend process was not running at page-load time.
Verified: at diagnosis start nothing listened on :8000/:5173; both
listen now and every queue/dashboard endpoint returns 200. The v2
launcher already health-gates before opening the browser; the
remaining exposure is servers started from a shell that later closes
(e.g. my session-parented test runs) — operational, not a code defect.

## 4. Minimal fix plan (PROPOSED — not implemented; awaiting go-ahead)

Constraint-respecting fix for Cause A only (read paths, no
orchestrator/skill/schema change, no mock data):

1. `get_artifacts` / `get_artifact` — replace the `_require_run` gate
   with "in registry OR run dir exists on disk" (`_SAFE_RUN_ID` +
   `isdir(run_root/run_id)`). Data path already disk-based → real
   artifacts for pre-restart runs; unknown ids still 404. ~5 lines.
2. `get_events` — on registry miss with a run dir on disk, REPLAY the
   run's real `trace.jsonl` through the existing
   `events_mod.TraceEventAdapter` (the same mapping used live) with
   deterministic sequence ids, same response shape. Returns recorded
   events, not mock. ~40 lines + tests.
3. `get_run` — on registry miss, reconstruct minimal metadata from the
   persisted case state (case_id, mapped status, timestamps) with an
   explicit `"restored": true` marker and honest nulls for
   registry-only fields. ~20 lines + tests.
4. `/stream` — defer (live-only consumer; restored-run SSE needs a
   terminate-after-history contract change — out of scope).

Cause B needs no code change: keep launching via the v2 .bat
(double-click keeps its console alive; health-gated).

Estimated diff: `runtime/server.py` (+~70), `tests/runtime/test_agent_api.py`
(+1 section). Frontend: zero.

## 5. Verification performed (this audit)

- Code map: all 20+ Web-consumed calls ↔ routes (table above).
- Live matrix via vite proxy: disk-only run → 200/200/404/404/404/200;
  in-memory run → all 200 (evidence run ids in the header).
- Both symptom classes reproduced/explained; queue + dashboard + A2
  card confirmed working while C/D 404 for the same approval.

**STOP — no fixes applied in this phase, per instruction.**
