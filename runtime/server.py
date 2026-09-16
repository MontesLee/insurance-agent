"""Web UI Backend — Phase 1 (Backend Event Stream + FastAPI + SSE).

A THIN adapter over the existing runtime. It does not re-implement any agent workflow:
it invokes the existing orchestrator exactly the way `demo.py` does (seed -> run with
gate_policy=stop -> bounded approve loop) and makes what happens observable:

    POST /api/runs                -> create run, invoke existing orchestrator (background)
    GET  /api/runs/{id}           -> Run metadata (NOT CaseState — the state stays in runtime/)
    GET  /api/runs/{id}/events    -> full event history (refresh / replay / debug)
    GET  /api/runs/{id}/stream    -> live SSE (`event: runtime`, resumable via id /
                                     ?after_event_id / Last-Event-ID)
    GET  /api/health, /api/cases  -> liveness, available demo cases

Design rules (spec §17 — the UI observes the runtime, it never drives it):
  * no business logic here: no skill selection, no eval decisions, no repair policy;
  * the orchestrator is invoked unchanged, in a worker thread, exactly like the demo;
  * events are tapped from `runtime/trace.py` (the single execution record) and mapped
    to `runtime/events.py` RuntimeEvents — one event model for UI, trace.jsonl and replay;
  * observability is non-blocking: a closed browser, a dead subscriber or a bus failure
    cannot affect a run (see runtime/event_bus.py).

Run it:  python -m runtime.server [--port 8000] [--host 127.0.0.1]
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import queue as queue_mod
import sys
import threading
import traceback
import uuid
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime import trace as tr  # noqa: E402
from runtime import events as events_mod  # noqa: E402
from runtime import artifact_registry as reg  # noqa: E402
from runtime.state import store as state_store  # noqa: E402
from runtime.event_bus import CLOSED, EventBus, default_bus  # noqa: E402

BENCH_DIR = os.path.join(REPO_ROOT, "evals", "agent-benchmark")
BENCH_RUNNER = os.path.join(BENCH_DIR, "run_agent_benchmark.py")
DEFAULT_RUN_ROOT = os.path.join(REPO_ROOT, "tmp", "webui-runs")
MAX_GATE_APPROVALS = 3   # mirrors demo.py / run_agent_benchmark.py behaviour

# report status -> (terminal event type, Run status)
_TERMINAL = {
    "COMPLETED": ("run_completed", "completed"),
    "NEEDS_REVIEW": ("run_completed", "needs_review"),
    "PAUSED_NEEDS_REVIEW": ("run_completed", "needs_review"),   # gate not approved in budget
    "WAITING_FOR_USER": ("run_completed", "waiting"),
    "FAILED": ("run_failed", "failed"),
    "BLOCKED": ("run_failed", "failed"),
}


def _load_bench():
    """Reuse the benchmark's mutation language (same as demo.py — no duplication)."""
    spec = importlib.util.spec_from_file_location("webui_bench_runner", BENCH_RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BENCH = _load_bench()


# --------------------------------------------------------------------------- #
# Run registry — metadata about ONE execution of a case (never a second CaseState)
# --------------------------------------------------------------------------- #
class RunManager:
    def __init__(self, bus: Optional[EventBus] = None, run_root: Optional[str] = None):
        self.bus = bus or default_bus
        self.run_root = run_root or DEFAULT_RUN_ROOT
        self._runs: dict = {}          # run_id -> Run metadata dict
        self._lock = threading.Lock()
        self._active: dict = {}        # case_id -> run_id of THE active run (trace routing)
        self._wf = None
        self._base = None
        self._cases: dict = {}
        self._kb_empty: Optional[str] = None

    # ---------------- case catalog (read-only, from the benchmark manifest) ---- #
    def _ensure_loaded(self) -> None:
        if self._wf is not None:
            return
        with self._lock:
            if self._wf is not None:
                return
            with open(os.path.join(BENCH_DIR, "manifest.json"), encoding="utf-8") as f:
                manifest = json.load(f)
            with open(os.path.join(REPO_ROOT, manifest["seeds_file"]), encoding="utf-8") as f:
                self._base = json.load(f)
            self._kb_empty = os.path.join(REPO_ROOT, manifest["empty_kb"])
            self._cases = {c["id"]: c for c in manifest["cases"]}
            self._wf = orch.load_workflow()

    def cases(self) -> list:
        self._ensure_loaded()
        return [{"id": c["id"], "category": c.get("category"), "desc": c.get("desc"),
                 "kb": c.get("kb")} for c in self._cases.values()]

    def case_by_id(self, case_id: str) -> Optional[dict]:
        self._ensure_loaded()
        return self._cases.get(case_id)

    # ---------------- run lifecycle ------------------------------------------- #
    def create_run(self, case: dict) -> tuple:
        """Start a run for `case`. Returns (run, None) on success.

        M-1: when the case already has an ACTIVE run, returns (None, active_run_id)
        and creates nothing — trace routing is keyed by case_id, so a second
        concurrent run of the same case would mis-attribute the first run's events.
        The reservation happens synchronously under the lock, before the worker
        thread exists, so two rapid POSTs can never both win.
        """
        self._ensure_loaded()
        case_id = case["id"]
        with self._lock:
            active = self._active.get(case_id)
            if active is not None:
                return None, active
            run_id = "run_%s" % uuid.uuid4().hex[:8]
            run = {
                "run_id": run_id,
                "case_id": case_id,
                "status": "queued",
                "started_at": None,
                "completed_at": None,
                "current_stage": None,
                "event_count": 0,
                "result_status": None,
                "reasons": [],
                # the canonical pipeline (order + skills + outputs) straight from the
                # workflow definition — the UI renders it verbatim, never invents stages
                "stage_order": [{"id": st["id"], "skill": st.get("skill"),
                                 "produces": st.get("produces")}
                                for st in self._wf.get("stages", [])],
                # M-2: a run-scoped TraceEventAdapter. Its task_id->stage table is
                # run-specific (task ids like TASK-001 repeat across runs), so a
                # shared adapter would cross-contaminate concurrent runs.
                "_adapter": events_mod.TraceEventAdapter(),
            }
            self._runs[run_id] = run
            self._active[case_id] = run_id
        threading.Thread(target=self._worker, args=(run_id, case), daemon=True,
                         name="run-%s" % run_id).start()
        return self.get_run(run_id), None

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None

    def _set(self, run_id: str, **kw) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is not None:
                run.update(kw)

    def _next_seq(self, run_id: str) -> int:
        """Next event position = current history length + 1 (contiguous published ids)."""
        return self.bus.event_count(run_id) + 1

    # ---------------- event plumbing ------------------------------------------ #
    def _make_tap(self, run_id: str, case_id: str):
        """Build THIS run's trace sink (a distinct closure per run).

        A per-run closure (not the shared bound method `self._tap`) is required:
        equal bound methods collapse in `trace.add_sink`'s list, so two concurrent
        runs would double-dispatch every record — duplicating events on both runs.
        The `_active` ownership check additionally guarantees a stale tap can never
        deliver into a run that no longer owns the case slot.
        """
        def tap(rec: dict) -> None:
            try:
                if rec.get("case_id") != case_id:
                    return                  # route by the RECORD's case, not just the slot
                if self._active.get(case_id) != run_id:
                    return                  # stale tap: this run no longer owns the slot
                with self._lock:
                    adapter = (self._runs.get(run_id) or {}).get("_adapter")
                if adapter is None:
                    return
                # M-2: the adapter is run-scoped (never shared), so no run-specific
                # task_id->stage mapping state can leak between concurrent runs.
                event = adapter.to_event(rec, run_id, self._next_seq(run_id))
                if event is None:
                    return
                self.bus.publish(run_id, event.to_dict())
                self._after_publish(run_id, event.to_dict())
            except Exception:  # noqa: BLE001 — observability must never break the run
                pass
        return tap

    def _emit(self, run_id: str, event_type: str, **kw) -> None:
        """Emit a run-level event (run_started / run_completed / run_failed)."""
        event = events_mod.RuntimeEvent(
            event_id=events_mod.event_id_for(run_id, self._next_seq(run_id)),
            run_id=run_id, event_type=event_type, **kw)
        self.bus.publish(run_id, event.to_dict())
        self._after_publish(run_id, event.to_dict())

    def _after_publish(self, run_id: str, event: dict) -> None:
        update = {"event_count": self.bus.event_count(run_id)}
        if event.get("event_type") == "stage_started" and event.get("stage"):
            update["current_stage"] = event["stage"]
        self._set(run_id, **update)

    # ---------------- artifact / provenance reads (Phase 2 UI support) -------- #
    def _load_state(self, run_id: str) -> Optional[dict]:
        """Read-only load of the run's persisted CaseState (its own checkpoint root).

        This is the SAME state the runtime produced (no copy, no second truth):
        artifacts on disk + the artifact registry with its lineage edges.
        """
        run = self.get_run(run_id)
        if run is None:
            return None
        try:
            return state_store.load(os.path.join(self.run_root, run_id), run["case_id"])
        except Exception as e:  # noqa: BLE001 — unreadable/absent checkpoint
            print("[server] artifact read failed for %s: %r" % (run_id, e), file=sys.stderr)
            return None

    def artifacts_of(self, run_id: str) -> Optional[list]:
        """Registry view of every artifact the run produced (metadata + lineage)."""
        state = self._load_state(run_id)
        if state is None:
            return None
        out = []
        for art_type, rec in (state.get("artifact_registry") or {}).items():
            out.append({
                "artifact_id": rec.get("artifact_id"),
                "artifact_type": art_type,
                "producer_stage": rec.get("producer_stage"),
                "producer_skill": rec.get("producer_skill"),
                "created_at": rec.get("created_at"),
                "status": rec.get("status"),
                "input_artifacts": list(rec.get("input_artifacts") or []),
                "evidence_refs": list(rec.get("evidence_refs") or []),
                "lineage": [{"artifact_id": aid,
                             "artifact_type": reg.type_of(state, aid)}
                            for aid in reg.lineage(state, art_type)],
            })
        out.sort(key=lambda r: r["artifact_id"] or "")
        return out

    def artifact_detail(self, run_id: str, artifact_type: str) -> Optional[dict]:
        """One artifact: registry metadata + the full canonical artifact JSON."""
        state = self._load_state(run_id)
        if state is None:
            return None
        rec = (state.get("artifact_registry") or {}).get(artifact_type)
        if rec is None:
            return None
        return {
            "artifact_id": rec.get("artifact_id"),
            "artifact_type": artifact_type,
            "producer_stage": rec.get("producer_stage"),
            "producer_skill": rec.get("producer_skill"),
            "created_at": rec.get("created_at"),
            "status": rec.get("status"),
            "input_artifacts": list(rec.get("input_artifacts") or []),
            "evidence_refs": list(rec.get("evidence_refs") or []),
            "lineage": [{"artifact_id": aid,
                         "artifact_type": reg.type_of(state, aid)}
                        for aid in reg.lineage(state, artifact_type)],
            "artifact": state.get("artifacts", {}).get(artifact_type),
        }

    # ---------------- the worker: invoke the EXISTING orchestrator ------------- #
    def _worker(self, run_id: str, case: dict) -> None:
        case_id = case["id"]
        self._set(run_id, status="running", started_at=events_mod.now_iso())
        # NOTE: _active[case_id] was reserved by create_run() under the lock (M-1);
        # the worker only releases it here in `finally`.
        remove_tap = tr.add_sink(self._make_tap(run_id, case_id))
        try:
            self._emit(run_id, "run_started", case_id=case_id,
                       message="Run started for case %s" % case_id,
                       data={"category": case.get("category"),
                             "workflow": self._wf.get("workflow"),
                             "workflow_version": str(self._wf.get("version", ""))})

            # exactly the demo.py recipe: mutate the proven full-chain seeds, then
            # seed -> run -> bounded approve loop. No new agent behaviour.
            seeds = BENCH.apply_mutations(copy.deepcopy(self._base["artifacts"]),
                                          case.get("mutations", []))
            kb_dir = self._kb_empty if case.get("kb") == "empty" else None
            run_dir = os.path.join(self.run_root, run_id)
            os.makedirs(run_dir, exist_ok=True)

            state = orch.seed_case(self._wf, case_id, seeds,
                                   provided_by=self._base.get("provided_by",
                                                               "upstream-dialogue"))
            rep = orch.run(state, self._wf, gate_policy="stop",
                           kb_dir=kb_dir, checkpoint_root=run_dir)
            approvals = 0
            while rep["status"] == "PAUSED_NEEDS_REVIEW" and approvals < MAX_GATE_APPROVALS:
                orch.approve(state, rep["stopped_at"])
                approvals += 1
                rep = orch.run(state, self._wf, gate_policy="stop",
                               kb_dir=kb_dir, checkpoint_root=run_dir)

            event_type, run_status = _TERMINAL.get(rep["status"], ("run_failed", "failed"))
            reasons = [str(r)[:300] for r in (rep.get("reasons") or [])][:5]
            self._emit(run_id, event_type, case_id=case_id, status=run_status,
                       stage=rep.get("stopped_at"),
                       message=("; ".join(reasons) or rep["status"]),
                       data={"result_status": rep["status"], "approvals": approvals,
                             "executed_stages": [e.get("stage")
                                                 for e in rep.get("executed", [])]})
            self._set(run_id, status=run_status, completed_at=events_mod.now_iso(),
                      result_status=rep["status"], reasons=reasons)
        except Exception as e:  # noqa: BLE001 — the run wrapper must always terminate
            print("[server] run %s crashed: %r" % (run_id, e), file=sys.stderr)
            traceback.print_exc()
            self._emit(run_id, "run_failed", case_id=case_id, status="failed",
                       message="run crashed: %r" % e,
                       data={"error_type": type(e).__name__})
            self._set(run_id, status="failed", completed_at=events_mod.now_iso(),
                      result_status="CRASHED", reasons=[repr(e)[:300]])
        finally:
            remove_tap()
            self._active.pop(case_id, None)      # M-1: release the case slot
            with self._lock:
                run = self._runs.get(run_id)
                if run is not None:
                    run.pop("_adapter", None)    # M-2: drop the run-scoped adapter
            self.bus.finish(run_id)   # defensive: every subscriber wakes and closes


# --------------------------------------------------------------------------- #
# FastAPI application
# --------------------------------------------------------------------------- #
class RunRequest(BaseModel):
    case_id: str


def _sse_chunk(event: dict) -> str:
    return "event: runtime\nid: %s\ndata: %s\n\n" % (
        event.get("event_id"), json.dumps(event, ensure_ascii=False))


def create_app(manager: Optional[RunManager] = None) -> FastAPI:
    mgr = manager or RunManager()
    app = FastAPI(title="insurance-agent Web UI API", version="0.1.0")
    # local-dev CORS so the Phase 2 React app (separate port) can consume the API
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["*"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "0.1.0", "bus": mgr.bus.stats()}

    @app.get("/api/cases")
    def list_cases():
        return {"cases": mgr.cases()}

    @app.post("/api/runs", status_code=201)
    def create_run(req: RunRequest):
        case = mgr.case_by_id(req.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail={
                "error": "unknown case_id",
                "available": [c["id"] for c in mgr.cases()]})
        run, active_run_id = mgr.create_run(case)
        if run is None:
            # M-1: the case already has an active run — never start a second one
            # (its events would be mis-attributed). Exact body shape is the API contract.
            return JSONResponse(status_code=409, content={
                "error": "case_already_running",
                "run_id": active_run_id,
                "case_id": req.case_id})
        return {"run_id": run["run_id"], "case_id": run["case_id"], "status": run["status"]}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = mgr.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="unknown run_id")
        return {k: v for k, v in run.items() if not k.startswith("_")}

    @app.get("/api/runs/{run_id}/events")
    def get_events(run_id: str, after_event_id: Optional[str] = None):
        _require_run(mgr, run_id)
        evs = mgr.bus.events_for(run_id, after_event_id=after_event_id)
        return {"run_id": run_id, "count": len(evs), "events": evs}

    @app.get("/api/runs/{run_id}/artifacts")
    def get_artifacts(run_id: str):
        _require_run(mgr, run_id)
        arts = mgr.artifacts_of(run_id)
        if arts is None:
            raise HTTPException(status_code=404, detail="no persisted state for this run yet")
        return {"run_id": run_id, "count": len(arts), "artifacts": arts}

    @app.get("/api/runs/{run_id}/artifacts/{artifact_type}")
    def get_artifact(run_id: str, artifact_type: str):
        _require_run(mgr, run_id)
        detail = mgr.artifact_detail(run_id, artifact_type)
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown artifact_type for this run")
        return detail

    @app.get("/api/runs/{run_id}/stream")
    def stream_run(run_id: str, after_event_id: Optional[str] = None,
                   request: Request = None):
        _require_run(mgr, run_id)
        # resume cursor priority: explicit query param, then the SSE Last-Event-ID header
        cursor = after_event_id or (request.headers.get("last-event-id") if request else None)

        def gen():
            cur = cursor   # local copy: the closed-over value is the resume point
            sub = mgr.bus.subscribe(run_id)
            try:
                for e in mgr.bus.events_for(run_id, after_event_id=cur):
                    yield _sse_chunk(e)
                    cur = e["event_id"]
                if mgr.bus.is_run_done(run_id):
                    return
                while True:
                    try:
                        item = sub.get(timeout=0.5)
                    except queue_mod.Empty:
                        if mgr.bus.is_run_done(run_id):
                            for e in mgr.bus.events_for(run_id, after_event_id=cur):
                                yield _sse_chunk(e)
                            return
                        yield ": keep-alive\n\n"
                        continue
                    if item is CLOSED:
                        # top up from history (covers events dropped while lagging)
                        for e in mgr.bus.events_for(run_id, after_event_id=cur):
                            yield _sse_chunk(e)
                        return
                    yield _sse_chunk(item)
                    cur = item["event_id"]
            finally:
                mgr.bus.unsubscribe(sub)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform",
                                          "X-Accel-Buffering": "no"})

    return app


def _require_run(mgr: RunManager, run_id: str) -> None:
    if mgr.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="unknown run_id")


app = create_app()


def main() -> None:
    import argparse
    import uvicorn

    ap = argparse.ArgumentParser(description="insurance-agent Web UI backend (Phase 1)")
    ap.add_argument("--host", default=os.environ.get("INSURANCE_AGENT_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int,
                    default=int(os.environ.get("INSURANCE_AGENT_PORT", "8000")))
    args = ap.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
