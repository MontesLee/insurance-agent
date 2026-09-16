# Web UI — Phase 2: Runtime Observability UI (V0.1)

> **Web UI is an observability/control-plane layer over the existing Agent Runtime.**
> It renders what the runtime already produces (RuntimeEvents, Run metadata, artifacts,
> provenance) and can trigger runs. It never re-implements or drives the agent's
> decisions — no skill selection, no eval, no repair, no CaseState writes.
>
> **Honest scope note:** the current portfolio still uses structured Client State as
> the upstream input boundary. Raw natural-language intake is *not* yet the primary
> execution path — the UI runs benchmark cases whose upstream artifacts are seeded,
> exactly like `demo.py` and the agent benchmark do.

## Stack & layout

React 19 + Vite + TypeScript + Tailwind (v4) in `web/`; FastAPI + SSE from
`runtime/server.py` (Phase 1/1.1). Dev: `python -m runtime.server` + `npm run dev`
(vite proxies `/api` → `127.0.0.1:8000`).

```text
┌────────────┬──────────────────────────────┬─────────────────────┐
│ CASES      │ CONVERSATION / OUTPUT        │ RUNTIME INSPECTOR   │
│ (catalog + │ (live progress → rendered    │ RUN / PIPELINE /    │
│  run btns) │  insurance report)           │ EVAL / TRACE /      │
│            │                              │ ARTIFACT+PROVENANCE │
└────────────┴──────────────────────────────┴─────────────────────┘
```

## The one contract that matters

`web/src/types/runtime.ts` mirrors `runtime/events.py` `RuntimeEvent.to_dict()`
field-for-field (`event_id … data`, no `any`). Everything the UI shows about a run
is a projection of that event sequence through ONE explicit transition table
(`web/src/state/runReducer.ts`):

| event | UI transition |
|---|---|
| `run_started` / `run_completed` / `run_failed` | Run status (terminal status comes verbatim from the event's `status`) |
| `stage_started` / `stage_completed` / `stage_failed` | pipeline ○ / ● / ✓ / ✕ (+attempts, artifact link, duration) |
| `eval_started` / `eval_passed` / `eval_failed` | EVAL rows (paired by stage) |
| `repair_started` / `repair_completed` / `repair_exhausted` | repair badges; `repair_exhausted` → stage ⚠ |
| `artifact_created` | stage → artifact_id link (content fetched on demand) |
| `checkpoint_*`, `tool_*` | timeline only — never move pipeline state |
| unknown stage ids | recorded in timeline, ignored by pipeline |

Stage **order/labels come from the server's `stage_order`** (the workflow definition,
exposed via `GET /api/runs/{id}`) — the UI never invents stages or progress.

## SSE with resume (`web/src/hooks/useRunStream.ts`)

* On attach: `GET /api/runs/{id}` (skeleton + authoritative status) → `GET …/events`
  (replay) → live `GET …/stream` only if the run hasn't terminated.
* The last received `event_id` is persisted per run (`sessionStorage`) and used as
  `?after_event_id=` when reopening — **browser refresh rebuilds the identical
  timeline** (replay and live events go through the same reducer). The browser's own
  `Last-Event-ID` reconnect is also honoured server-side.
* Defensive: events from another `run_id` are dropped; event ids ≤ the cursor are
  dropped (no duplicates on resume); the stream self-closes on the terminal event
  (a finished run never opens a stream at all).

## Artifacts & provenance (read-only)

`GET /api/runs/{id}/artifacts` (registry summaries + lineage) and
`GET /api/runs/{id}/artifacts/{type}` (full canonical artifact) expose exactly what
the runtime persisted in the run's own checkpoint directory — there is no second
provenance structure. Clicking a pipeline stage opens the inspector: registry
metadata (artifact_id / producer / created_at / inputs), the lineage chain from the
artifact registry, a structured summary and the raw JSON.

## Control actions

Exactly one: `POST /api/runs {case_id}`. A second concurrent run of the same case is
rejected by the runtime with `409 case_already_running` — the UI surfaces the banner
"This case is already running — Run: run_xxx" with an **Open active run** action
instead of creating a duplicate. Human-review gates inside a run are auto-approved by
the server's run wrapper (≤3), mirroring `demo.py`; a `waiting`/`needs_review` run is
terminal for the UI.

## Tests

* `npm test` — vitest + Testing Library (33 tests): event parsing, the transition
  table (stage/eval/repair/terminal), replay==live equivalence, SSE resume cursor +
  dedupe + close-on-terminal, pipeline/run-status rendering, 409 conflict handling,
  report wiring regression (fetch by artifact type, not stage id).
* `E2E_RUNTIME=1 npm test` — spawns the **real** python server, streams a full run
  and folds it through the same reducer: asserts run_id identity (UI === SSE ===
  RunManager), all-8-stage pipeline, eval surface, artifacts, and the rendered
  report (see `web/src/e2e/runtime-chain.e2e.test.ts`).

## Known limitations (V0.1)

Single-user local dev tool: no auth, no persistence beyond the runtime process (a
server restart loses run history — trace.jsonl/checkpoints on disk remain), no
multi-worker uvicorn (the event bus is intentionally single-process and in-memory),
run history lives only for the current browser session. See also
[webui-event-stream.md](webui-event-stream.md) §6.
