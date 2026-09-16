# Web UI Backend — Phase 1: Runtime Event Stream (V0.1)

> Status: **implemented + hardened (Phase 1.1) + consumed by the Phase 2 React UI**
> (see [webui.md](webui.md)).

## 1. Goal

Make the existing runtime **observable in real time** without changing what it does.
The Web UI is an *observer of the runtime, never its owner*:

```text
Existing Runtime (orchestrator / eval / repair / checkpoint — UNCHANGED)
      │
      ↓  runtime/trace.py  (the single execution record, unchanged semantics)
      │
      ├── trace.jsonl                        (replay / debug, unchanged)
      │
      └── add_sink → TraceEventAdapter → RuntimeEvent (runtime/events.py)
                                    │
                                    ↓
                          Event Bus (runtime/event_bus.py)
                                    │
                                    ↓
                       FastAPI (runtime/server.py)
                                    │
                                    ├── GET /api/runs/{id}/events   (history / replay)
                                    └── GET /api/runs/{id}/stream   (SSE, resumable)
```

Nothing in the decision path changed: no skill logic, no eval rules, no repair budget,
no CaseState/Artifact schema, no catalog. The only runtime edits are **additive
`trace.emit` instrumentation** (new observer-facing trace events) and a multi-sink hook
in `trace.py` — the demo CLI's single-sink `set_sink` keeps working unchanged.

## 2. The unified event contract (`runtime/events.py`)

One `RuntimeEvent` model shared by the UI stream, replay and the trace:

```json
{
  "event_id": "evt_000021",
  "run_id": "run_3fdcc4e8",
  "timestamp": "2026-09-15T18:20:01.512000+00:00",
  "event_type": "stage_started",
  "stage": "coverage-gap-analysis",
  "skill": "coverage-gap-analysis",
  "status": "running",
  "case_id": "bm-complete-001",
  "artifact_id": null,
  "eval_id": null,
  "repair_attempt": null,
  "message": "stage=coverage-gap-analysis",
  "data": { "trace_id": "TRACE-1A2B3C4D", "attempt": 1, "input_artifacts": ["ART-003"] }
}
```

* `event_id` — per-run, monotonic, zero-padded (`evt_000021`). It is the SSE resume cursor.
* `event_type` — closed vocabulary:

  | Lifecycle | Event types |
  |---|---|
  | run | `run_started` · `run_completed` · `run_failed` |
  | stage | `stage_started` · `stage_completed` · `stage_failed` |
  | eval | `eval_started` · `eval_passed` · `eval_failed` |
  | repair | `repair_started` · `repair_completed` · `repair_exhausted` |
  | artifact | `artifact_created` |
  | checkpoint | `checkpoint_created` · `checkpoint_resumed` |
  | tool / shared service | `tool_started` · `tool_completed` · `tool_failed` |

* `to_dict()` is deterministic (fixed field order) and JSON-safe by construction.
* **Safety**: events carry ids, statuses and short messages only — never artifact
  payloads, prompts, API keys or client-sensitive values; messages are capped at 600 chars.

### Trace → event mapping

`TraceEventAdapter` maps trace records onto the vocabulary:

| trace event | runtime event |
|---|---|
| `SKILL_STARTED` / `SKILL_COMPLETED` / `TASK_FAILED` | `stage_started` / `stage_completed` / `stage_failed` |
| `EVAL_STARTED` | `eval_started` |
| `EVAL_COMPLETED` (eval_status) | `eval_passed` / `eval_failed` |
| `REPAIR_STARTED` / `REPAIR_COMPLETED` / `REPAIR_EXHAUSTED` | `repair_started` / `repair_completed` / `repair_exhausted` |
| `ARTIFACT_STORED` | `artifact_created` |
| `CHECKPOINT_SAVED` / `CHECKPOINT_LOADED` | `checkpoint_created` / `checkpoint_resumed` |
| `TOOL_STARTED` / `TOOL_COMPLETED` / `TOOL_FAILED` | `tool_started` / `tool_completed` / `tool_failed` |

`CASE_*` records are **not** forwarded: the run wrapper emits `run_started` /
`run_completed` / `run_failed` exactly once per run with the true final status, because
only the wrapper knows whether a paused gate will be approved and the run continue.
`TASK_CREATED` records only teach the adapter the `task_id → stage` mapping.

New trace events added in Phase 1 (all additive, mirrored into `trace.jsonl` like any
other record): `ARTIFACT_STORED`, `REPAIR_EXHAUSTED`, `TOOL_STARTED`, `TOOL_COMPLETED`,
`TOOL_FAILED` (the knowledge-search Evidence Provider is the runtime's "tool"), plus
`EVAL_STARTED`/`EVAL_COMPLETED` for seeded and evidence artifacts.

## 3. Event Bus (`runtime/event_bus.py`)

In-memory, one process, thread-safe. **Observability is non-blocking:**

* `publish()` never raises and never blocks — every internal failure is swallowed
  (stderr note only). The bus cannot be a single point of failure.
* A run with zero subscribers behaves identically (history still fills). The Web UI can
  be closed; the agent still runs.
* Subscribers get bounded queues; a slow/broken subscriber has events dropped for *it*
  (flagged `dropped`, recoverable from history) instead of ever delaying the publisher.
* Per-run history is retained (bounded) — the basis for `GET /events`, page refresh,
  replay, and gap-free SSE resume.
* A terminal event (or `finish()`) pushes a `CLOSED` sentinel so every stream wakes up
  and closes.

## 4. The server (`runtime/server.py`, `python -m runtime.server`)

`RunManager` is a **thin adapter**: for each run it invokes the *existing* orchestrator
exactly the way `demo.py` does (seed from the benchmark case → `run(gate_policy="stop")`
→ bounded approve loop ≤ 3), on a background thread, with a trace tap installed. It
never selects skills, evaluates, repairs or touches CaseState semantics.

`Run` is metadata about **one execution** — never a second CaseState:

```json
{
  "run_id": "run_3fdcc4e8", "case_id": "bm-complete-001",
  "status": "completed",            // queued → running → completed | failed | needs_review | waiting
  "started_at": "…", "completed_at": "…",
  "current_stage": "report-generation",
  "event_count": 50,
  "result_status": "COMPLETED",     // the orchestrator report's own status
  "reasons": []
}
```

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | liveness + bus stats |
| `GET /api/cases` | available benchmark cases (id/category/desc/kb) |
| `POST /api/runs` `{ "case_id": "bm-complete-001" }` | create a run; returns `{run_id, case_id, status}`. **409** `{"error":"case_already_running","run_id":…,"case_id":…}` when the case already has an active run (Phase 1.1: the case slot is reserved synchronously under a lock — a second run of the same case can never be created, because trace routing is keyed by case_id) |
| `GET /api/runs/{run_id}` | Run metadata (incl. `stage_order`: the workflow's canonical stages, so the UI never invents them) |
| `GET /api/runs/{run_id}/events?after_event_id=` | full event history (replay/refresh/debug) |
| `GET /api/runs/{run_id}/stream?after_event_id=` | live SSE stream |
| `GET /api/runs/{run_id}/artifacts` | registry summaries + lineage (Phase 2, read-only) |
| `GET /api/runs/{run_id}/artifacts/{type}` | full canonical artifact from the run's own checkpoint dir (Phase 2, read-only) |

### SSE wire format

```text
event: runtime
id: evt_000021
data: {"event_id": "evt_000021", "event_type": "stage_started", …}

: keep-alive
```

* Resume: `?after_event_id=evt_000020` **or** the standard `Last-Event-ID` header
  (the `id:` line makes browsers send it automatically on reconnect). Replay continues
  strictly after the cursor — no duplicates, no gaps; a lagging subscriber is topped up
  from history when the stream closes.
* The stream ends right after the terminal event (`run_completed` / `run_failed`).
* Streaming a finished run replays the full history and closes (page refresh).

## 5. Phase 1.1 hardening — concurrency & event attribution

Fixed before the UI was built (all guarded by `tests/runtime/test_concurrency.py`):

* **M-1** — one active run per case: `POST /api/runs` reserves `case_id → run_id`
  synchronously under the lock **before** the worker thread exists and answers
  **409 `case_already_running`** for a second run; the slot is released in the
  worker's `finally`. Concurrent runs of *different* cases remain fully supported.
* **M-2** — every run gets its **own `TraceEventAdapter`** (task ids like `TASK-001`
  repeat across runs, so a shared adapter cross-contaminated stage attribution).
* **Tap isolation** — each run installs a **distinct per-run closure** as its trace
  sink (equal bound methods collapse in `trace.add_sink`'s list, which double-
  dispatched every record during concurrent runs). The tap filters by the record's
  case **and** checks it still owns the case slot, so a stale tap can never deliver.
* Provenance invariant under concurrency: every event's `run_id`/`case_id` belong to
  the run that produced them; a concurrent run emits exactly as many events as the
  same case run alone (no double-dispatch).

## 6. Tests (`tests/runtime/`)

| Suite | Covers |
|---|---|
| `test_events.py` | contract fields, closed vocabulary, deterministic JSON, safety caps, every trace→event mapping |
| `test_event_bus.py` | delivery, multiple subscribers, ordering, disconnect/slow/broken subscribers, swallowed bus failures, history cursor, terminal close, concurrent publishers |
| `test_server.py` | all endpoints end-to-end through real runs (completed / needs_review / waiting), event coverage, safety audit |
| `test_sse.py` | wire framing, live ordering, close-on-terminal, replay, both resume mechanisms |

All four are wired into `tmp/run_regression.py`.

## 7. Known limitations (V0.1)

* **Phase 1 EventBus is intentionally single-process and in-memory** (no Redis /
  Kafka / Postgres / multi-worker uvicorn — deliberate V0.1 scope). Runs, events and
  subscriptions live in the server process; a restart loses them (trace.jsonl /
  checkpoints on disk remain the durable record), and uvicorn must run with a single
  worker.
* **One active run per case** (Phase 1.1 enforces it with 409): a case may run again
  once its previous run reached a terminal status.
* **No auth/CORS restrictions**: local development server (`127.0.0.1` by default);
  CORS is open for the dev UI.
* `POST /api/runs` only accepts the repository's benchmark/demo cases (the seeded
  full-chain fixture mutated per case); no arbitrary client intake yet.
* Human-review gates are auto-approved by the run wrapper (≤ 3), mirroring `demo.py`;
  a `waiting`/`needs_review` run is terminal for the API until an approve endpoint
  exists (future).
* Completed-run history has no GC (bounded per run at 10k events) — fine for a dev
  server, not for long-running deployments.
* The SSE generator polls its queue at 500 ms — fine for V0.1 scale; not a
  high-throughput feed.
