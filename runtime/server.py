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
import time
import traceback
import uuid
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from fastapi import FastAPI, HTTPException, Request, Depends, Security  # noqa: E402
from fastapi.security import APIKeyHeader  # noqa: E402

from runtime import auth as runtime_auth  # noqa: E402
from runtime import consumer_access  # noqa: E402  (28.G B-02)
from runtime import governance  # noqa: E402  (28.I B-04)
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime import trace as tr  # noqa: E402
from runtime import events as events_mod  # noqa: E402
from runtime import artifact_registry as reg  # noqa: E402
from runtime import checkpoint as cp  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime.state import store as state_store  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.event_bus import CLOSED, EventBus, default_bus  # noqa: E402
from runtime.agent import (ChatManager, ProviderNotConfigured,  # noqa: E402
                           run_agent_turn, provider_from_env)
from runtime.agent.tools import ToolContext  # noqa: E402

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


# Phase 27.7.6 v2: the offline Review Card generator (evaluation layer,
# hyphenated dir -> not importable as a package; same importlib idiom as
# _load_bench). Loaded once; used ONLY as a read-only projection.
_REVIEW_CARD_GEN = None


def _review_card_generator():
    global _REVIEW_CARD_GEN
    if _REVIEW_CARD_GEN is None:
        path = os.path.join(REPO_ROOT, "evaluation", "human-review",
                            "review_card_generator.py")
        spec = importlib.util.spec_from_file_location(
            "webui_review_card_generator", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _REVIEW_CARD_GEN = mod
    return _REVIEW_CARD_GEN


# --------------------------------------------------------------------------- #
# Run registry — metadata about ONE execution of a case (never a second CaseState)
# --------------------------------------------------------------------------- #
class RunManager:
    def __init__(self, bus: Optional[EventBus] = None, run_root: Optional[str] = None,
                 agent_provider=None):
        self.bus = bus or default_bus
        self.run_root = run_root or DEFAULT_RUN_ROOT
        self.agent_provider = agent_provider      # injectable (tests use FakeLLM)
        self.agent_fast_provider = None           # optional fast tier injection
        self.chats = ChatManager()
        self._runs: dict = {}          # run_id -> Run metadata dict
        self._closed: set = set()      # 28.K.24: run_ids with a terminal already emitted
        self._lock = threading.Lock()
        self._active: dict = {}        # case_id -> run_id of THE active run (trace routing)
        self._active_chat: dict = {}   # chat_id -> run_id (one agent turn at a time)
        self._wf = None
        self._base = None
        self._cases: dict = {}
        self._kb_empty: Optional[str] = None
        # ADR-021: configuration-based Agent Registry — fail-closed startup
        # validation (invalid declarations refuse to start the server).
        # Read-only snapshot for process lifetime; no dynamic registration.
        from runtime import agent_registry as _agent_registry_mod
        self._agent_registry = _agent_registry_mod.load_registry()

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
    def create_run(self, case: dict, owner: Optional[str] = None) -> tuple:
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
            run_id = "run_%s" % uuid.uuid4().hex[:16]
            run = {
                "run_id": run_id,
                "case_id": case_id,
                "owner": owner,  # 28.G: creator subject (internal demo runs)
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
        # 28.K.28 latency profiling: pure-observation bus tap (never
        # raises; a missing profile is the worst case)
        try:
            from runtime.obs.run_profiler import attach as _prof_attach
            _prof_attach(run_id, self.bus)
        except Exception:  # noqa: BLE001 — observation only
            pass
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

    def _finish_run(self, run_id: str, case_id: str, event_type: str,
                    status: str, *, result_status: str = "",
                    message: str = "", data: Optional[dict] = None,
                    chat_id: Optional[str] = None,
                    chat_message: Optional[str] = None,
                    chat_kind: str = "finish") -> bool:
        """28.K.24: IDEMPOTENT terminal closure — the FIRST caller wins
        (worker normal path, crash handler, or the deadline supervisor);
        later attempts become no-ops. Guarantees exactly one terminal
        event per run no matter which path fires."""
        with self._lock:
            if run_id in self._closed:
                return False
            self._closed.add(run_id)
        payload = dict(data or {})
        payload.setdefault("result_status", result_status or status.upper())
        self._emit(run_id, event_type, case_id=case_id, status=status,
                   message=message[:600] or status, data=payload)
        self._set(run_id, status=status, completed_at=events_mod.now_iso(),
                  result_status=result_status or status.upper(),
                  reasons=[message[:300]] if message else [])
        if chat_id and chat_message:
            # 28.K.25-S1 delivery hygiene: the single chat-boundary point —
            # internal identifiers cannot cross into consumer text.
            from runtime.consumer_hygiene import sanitize_consumer_text
            self.chats.add_assistant_message(
                chat_id, sanitize_consumer_text(chat_message),
                chat_kind, run_id)
        return True

    def _after_publish(self, run_id: str, event: dict) -> None:
        update = {"event_count": self.bus.event_count(run_id)}
        if event.get("event_type") == "stage_started" and event.get("stage"):
            update["current_stage"] = event["stage"]
        self._set(run_id, **update)

    # ---------------- artifact / provenance reads (Phase 2 UI support) -------- #
    def _case_id_on_disk(self, run_id: str) -> Optional[str]:
        """Phase 27.7.6-F: case id for a run whose registry entry is gone
        (backend restart) — resolved from the persisted directory layout
        (<run_root>/<run_id>/<case_id>/case_state.json), never guessed."""
        import glob as globmod
        for d in sorted(globmod.glob(os.path.join(self.run_root, run_id, "*"))):
            if os.path.isfile(os.path.join(d, "case_state.json")):
                return os.path.basename(d)
        return None

    def _load_state(self, run_id: str) -> Optional[dict]:
        """Read-only load of the run's persisted CaseState (its own checkpoint root).

        This is the SAME state the runtime produced (no copy, no second truth):
        artifacts on disk + the artifact registry with its lineage edges.
        Phase 27.7.6-F: registry miss falls back to the on-disk case dir so
        artifact reads survive a backend restart (read-only; the live path
        is unchanged).
        """
        run = self.get_run(run_id)
        case_id = run["case_id"] if run else self._case_id_on_disk(run_id)
        if case_id is None:
            return None
        try:
            return state_store.load(os.path.join(self.run_root, run_id), case_id)
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
    def _observe_run(self, run_id: str, case_id: str, state,
                     run_status: str, duration_ms: float,
                     error=None) -> None:
        """Phase 25: run-level task/skill metrics + structured log.
        Observation ONLY — reads the finished state, never mutates it;
        failures here can never affect the run's own result."""
        import runtime.obs as obs
        try:
            m = obs.default_metrics()
            trace = (state or {}).get("trace") or []
            per = {}
            for r in trace:
                ev, skill = r.get("event"), r.get("skill")
                if not skill:
                    continue
                s = per.setdefault(skill, {"calls": 0, "ok": 0,
                                           "fail": 0})
                if ev == "SKILL_STARTED":
                    s["calls"] += 1
                elif ev == "SKILL_COMPLETED":
                    s["ok"] += 1
                    ms = r.get("duration_ms")
                    if isinstance(ms, (int, float)):
                        m.observe("skill_duration", ms)
                elif ev == "TASK_FAILED":
                    s["fail"] += 1
            tasks = (state or {}).get("tasks") or []
            retries = sum(max(0, (t.get("attempt") or 1) - 1)
                          for t in tasks if isinstance(t, dict))
            m.inc("tasks_total", by=len(tasks))
            m.inc("tasks_success_total",
                  by=sum(s["ok"] for s in per.values()))
            m.inc("tasks_failed_total",
                  by=sum(s["fail"] for s in per.values()))
            m.inc("tasks_retried_total", by=retries)
            m.inc("skill_calls_total",
                  by=sum(s["calls"] for s in per.values()))
            m.inc("skill_success_total",
                  by=sum(s["ok"] for s in per.values()))
            m.inc("skill_failure_total",
                  by=sum(s["fail"] for s in per.values()))
            m.observe("task_duration", duration_ms)
            obs.log("run.completed",
                        status=run_status, duration_ms=duration_ms,
                        skills={k: v for k, v in per.items()},
                        retries=retries, error=error)
        except Exception:  # noqa: BLE001 — observability must not break runs
            pass

    def _worker(self, run_id: str, case: dict) -> None:
        case_id = case["id"]
        _obs_t0 = time.perf_counter()
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
            self._observe_run(run_id, case_id, state, run_status,
                              (time.perf_counter() - _obs_t0) * 1000)
        except Exception as e:  # noqa: BLE001 — the run wrapper must always terminate
            print("[server] run %s crashed: %r" % (run_id, e), file=sys.stderr)
            traceback.print_exc()
            self._emit(run_id, "run_failed", case_id=case_id, status="failed",
                       message="run crashed: %r" % e,
                       data={"error_type": type(e).__name__})
            self._set(run_id, status="failed", completed_at=events_mod.now_iso(),
                      result_status="CRASHED", reasons=[repr(e)[:300]])
            self._observe_run(run_id, case_id, None, "failed",
                              (time.perf_counter() - _obs_t0) * 1000,
                              error=e)
        finally:
            remove_tap()
            self._active.pop(case_id, None)      # M-1: release the case slot
            with self._lock:
                run = self._runs.get(run_id)
                if run is not None:
                    run.pop("_adapter", None)    # M-2: drop the run-scoped adapter
            self.bus.finish(run_id)   # defensive: every subscriber wakes and closes

    # ---------------- Mode B: real LLM agent runs (Phase 2.6) ----------------- #
    def agent_provider_or_fail(self):
        """Configured provider or raise ProviderNotConfigured — NEVER a silent
        fallback to the deterministic demo (spec §41). Same config layer as the
        smoke test: process env over <repo root>/.env."""
        if self.agent_provider is not None:
            return self.agent_provider
        from runtime.agent.config import load_llm_config
        return load_llm_config().to_provider()

    def agent_provider_status(self) -> dict:
        if self.agent_provider is not None:
            return {"configured": True, "provider": self.agent_provider.name,
                    "model": self.agent_provider.model, "source": "injected"}
        from runtime.agent.config import load_llm_config
        cfg = load_llm_config()
        out = cfg.describe()
        out["source"] = "env-or-dotenv" if out["configured"] else None
        return out

    def create_agent_run(self, chat_id: str, text: str,
                         owner: Optional[str] = None, provider=None) -> tuple:
        """Start one agent turn as a Run. Returns (run, None) or (None, reason)
        with reason in {"busy:<run_id>"} — same one-at-a-time semantics as the
        deterministic path, per CHAT (the conversation is the unit of work)."""
        self._ensure_loaded()
        fast = self.agent_fast_provider
        if provider is None:
            provider = self.agent_provider_or_fail()
            if fast is None:
                from runtime.agent.config import load_llm_config
                cfg = load_llm_config()
                fast = cfg.to_provider(fast=True) if cfg.fast_model else None
        with self._lock:
            busy = self._active_chat.get(chat_id)
            if busy is not None:
                return None, "busy:%s" % busy
            run_id = "run_%s" % uuid.uuid4().hex[:16]
            run = {
                "run_id": run_id,
                "case_id": "agentcase-%s" % run_id[4:],
                "chat_id": chat_id,
                "owner": owner,  # 28.G: the chat owner's subject
                "mode": "agent",
                "status": "queued",
                "started_at": None,
                "completed_at": None,
                "current_stage": None,
                "event_count": 0,
                "result_status": None,
                "reasons": [],
                "stage_order": [{"id": st["id"], "skill": st.get("skill"),
                                 "produces": st.get("produces")}
                                for st in self._wf.get("stages", [])],
                # run-scoped adapter (M-2 discipline): tool-driven tr.emit records
                # (stage/eval/artifact/checkpoint) flow to THIS run's event stream
                "_adapter": events_mod.TraceEventAdapter(),
            }
            self._runs[run_id] = run
            self._active_chat[chat_id] = run_id
        # 28.K.28 latency profiling: pure-observation bus tap (never
        # raises; a missing profile is the worst case)
        try:
            from runtime.obs.run_profiler import attach as _prof_attach
            _prof_attach(run_id, self.bus)
        except Exception:  # noqa: BLE001 — observation only
            pass
        self.chats.get_or_create(chat_id)
        self.chats.add_user_message(chat_id, text)
        self.chats.link_run(chat_id, run_id)
        threading.Thread(target=self._agent_worker,
                         args=(run_id, chat_id, text, provider, fast), daemon=True,
                         name="agent-%s" % run_id).start()
        return self.get_run(run_id), None

    def _agent_worker(self, run_id: str, chat_id: str, text: str, provider,
                      fast_provider=None) -> None:
        from runtime.agent.state import AgentState
        from runtime.run_deadline import run_deadline_s

        run = self._runs.get(run_id) or {}
        case_id = run.get("case_id") or "agentcase"
        run_dir = os.path.join(self.run_root, run_id)
        os.makedirs(run_dir, exist_ok=True)
        self._set(run_id, status="running", started_at=events_mod.now_iso())
        self._active[case_id] = run_id   # route tool trace records to this run
        remove_tap = tr.add_sink(self._make_tap(run_id, case_id))
        # 28.K.24 (L1): ABSOLUTE monotonic run deadline — shared by every
        # stage/tool/generation (retries clamp to the REMAINING budget).
        # A supervisor thread owns the terminal transition if the worker
        # is still executing at the deadline: the run lifecycle does NOT
        # depend on the worker thread finishing.
        deadline_at = time.monotonic() + run_deadline_s()
        run_done = threading.Event()

        def _deadline_supervisor() -> None:
            remaining = deadline_at - time.monotonic()
            if run_done.wait(timeout=max(0.0, remaining)):
                return  # worker closed the run itself
            self._finish_run(
                run_id, case_id, "run_failed", "failed",
                result_status="RUN_DEADLINE_EXCEEDED",
                message="run deadline exceeded (%.0fs) — terminal closed "
                        "by the lifecycle supervisor" % run_deadline_s(),
                data={"error_type": "RunDeadlineExceeded"},
                chat_id=chat_id,
                chat_message="处理时间过长，已停止本次分析。你可以重新"
                             "发送再试。")

        threading.Thread(target=_deadline_supervisor, daemon=True,
                         name="run-deadline-" + run_id).start()
        try:
            self._emit(run_id, "run_started", case_id=case_id, status="running",
                       message="Agent run started",
                       data={"mode": "agent", "chat_id": chat_id,
                             "provider": provider.name, "model": provider.model})

            # Phase 28.A-1 / ADR-019+020: SHADOW intent layer + shadow router.
            # Classifies and routes for RECORDING ONLY — except the ONE
            # production slice authorized by ruling D4 (Phase 28.C-1):
            # insurance_qa turns dispatch to the Insurance QA Agent below.
            # Fail-quiet by design: the shadow layer can never break a turn
            # (a classification failure simply means the slice does not
            # fire and the existing path runs unchanged).
            _qa_slice = False
            _pq_slice = False
            _plan_slice = False
            _ir = None
            _recent = None
            try:
                from runtime.intent import classifier as _intent_classifier
                from runtime.intent import llm_candidate as _intent_llm
                from runtime.intent import shadow as _intent_shadow
                from runtime import router as _intent_router
                from runtime.qa_agent import qa_slice_enabled as _qa_enabled
                from runtime.product_qa_agent import (
                    product_qa_slice_enabled as _pq_enabled)
                from runtime.planning_agent import (
                    planning_slice_enabled as _plan_enabled)
                from runtime.router_authority import (
                    authority_governs as _auth_governs, authority_mode)
                _recent = [m.get("content", "") for m in
                           (self.chats.view(chat_id) or {}).get("messages", [])][-8:]
                # 28.K.27-RV4-C1 (ADR-019 continuation addendum): the
                # deterministic planning-continuation signal — derived
                # from EXISTING run state only (no new case lifecycle,
                # no persistence): the latest previous run in THIS chat
                # ended WAITING_USER with intent=insurance_plan. Fail
                # quiet: any doubt means no continuation.
                _pending_clarification = False
                try:
                    _prev = [x for x in ((self.chats.view(chat_id) or {})
                                         .get("runs") or []) if x != run_id]
                    if _prev:
                        _pv = self.get_run(_prev[-1]) or {}
                        if _pv.get("result_status") == "WAITING_USER":
                            _pit = next(
                                (e for e in self.bus.events_for(_prev[-1])
                                 if e.get("event_type") == "intent_classified"),
                                None)
                            if _pit and (_pit.get("data") or {}).get(
                                    "intent") == "insurance_plan":
                                _pending_clarification = True
                except Exception:  # noqa: BLE001 — signal is best-effort
                    _pending_clarification = False
                _cand = None
                if _intent_llm.enabled():
                    # default OFF (rules-only shadow): enabling adds ADVISORY
                    # LLM proposals for rule-miss messages only — the
                    # deterministic resolver + schema gate still decide.
                    _cand = _intent_llm.make_candidate(
                        fast_provider or provider)   # cheap tier first
                _t0 = time.monotonic()
                _ir = _intent_classifier.classify(
                    text, conversation_context=_recent,
                    conversation_id=chat_id,
                    active_case_id=None,  # no persistent cases yet (ADR-024 blocked)
                    llm_candidate=_cand,
                    pending_clarification=_pending_clarification)
                _rd = _intent_router.route(_ir, self._agent_registry)
                _latency_ms = int((time.monotonic() - _t0) * 1000.0)
                # Ruling D4 (28.C-1): the FIRST Intent->Agent production
                # slice — a clean registry lookup of insurance_qa routes to
                # the QA Agent; every other intent keeps shadow semantics.
                # 28.C-2: the product_qa slice rides the same seam behind
                # its own feature flag (DEFAULT OFF — spec Step 3).
                # M4 staging (ADR-025 §5): the staged ROUTER AUTHORITY —
                # when it governs an intent, the Router is authoritative
                # and the per-slice flag is bypassed. Invalid value =>
                # exception => this fail-quiet block => nothing fires
                # (an authority grant can never happen through a typo).
                _auth_mode = "slices"
                try:
                    _auth_mode = authority_mode()
                except Exception as _ae:  # noqa: BLE001 — fail CLOSED
                    print("[server] router authority config invalid, "
                          "staying at 'slices' (%r)" % _ae, file=sys.stderr)
                _qa_slice = (
                    (_auth_governs(_auth_mode, "insurance_qa")
                     or _qa_enabled())
                    and _ir["intent_id"] == "insurance_qa"
                    and not _ir["clarification_required"]
                    and _rd.get("agent_id") == "insurance-qa-agent"
                    and _rd.get("decision_source") == "registry_lookup")
                # 28.K.7 (S-1, owner decision D-K6-1 = B): an
                # insurance-DOMAIN unknown (rule-miss, current-message
                # anchor marker from the classifier) takes the SAME
                # evidence-governed knowledge-QA pipeline — grounded
                # answer or honest refusal, never the ungoverned generic
                # loop. Non-insurance unknowns carry no marker and keep
                # the existing path (A4). Unknown's intrinsic
                # clarification_required=True is allowed: the governed
                # pipeline's refusal copy itself invites rephrasing.
                _unknown_governed = (
                    _ir["intent_id"] == "unknown_insurance_intent"
                    and "domain:insurance_anchor" in (
                        _ir.get("reason_codes") or []))
                if ((_auth_governs(_auth_mode, "insurance_qa")
                     or _qa_enabled()) and _unknown_governed):
                    _qa_slice = True
                _pq_slice = (
                    (_auth_governs(_auth_mode, "product_qa")
                     or _pq_enabled())
                    and _ir["intent_id"] == "product_qa"
                    and not _ir["clarification_required"]
                    and _rd.get("agent_id") == "insurance-qa-agent"
                    and _rd.get("decision_source") == "registry_lookup")
                # M3 (Phase 28.D contract): the planning behavior unit —
                # same seam, DEFAULT OFF; clarify-pending modify turns
                # never fire (M1 handled upstream by the Intent Layer).
                _plan_slice = (
                    (_auth_governs(_auth_mode, "insurance_plan")
                     or _auth_governs(_auth_mode, "modify_existing_plan")
                     or _plan_enabled())
                    and _ir["intent_id"] in ("insurance_plan",
                                             "modify_existing_plan")
                    and not _ir["clarification_required"]
                    and _rd.get("agent_id") == "insurance-planning-agent"
                    and _rd.get("decision_source") == "registry_lookup")
                # 28.B4 gray observation: record WHY each slice did or did
                # not take the turn (selected path / fallback reason).
                _slice_decision = None
                _slice_kinds = {"insurance_qa": "knowledge-qa",
                                "product_qa": "product-qa",
                                # 28.K.7 (S-1): governed insurance-domain
                                # unknowns record as knowledge-qa
                                "unknown_insurance_intent": "knowledge-qa",
                                "insurance_plan": "plan",
                                "modify_existing_plan": "plan"}
                if _ir["intent_id"] in _slice_kinds and (
                        _ir["intent_id"] != "unknown_insurance_intent"
                        or _unknown_governed):
                    # (28.K.7: only GOVERNED insurance-domain unknowns
                    # record a slice decision — a non-insurance unknown
                    # has no slice consideration at all, exactly as
                    # before.)
                    _kind = _slice_kinds[_ir["intent_id"]]
                    _fired = (_qa_slice or _pq_slice or _plan_slice)
                    _auth_on = _auth_governs(_auth_mode,
                                             _ir["intent_id"])
                    _flag_on = (_qa_enabled() if _kind == "knowledge-qa"
                                else _pq_enabled() if _kind == "product-qa"
                                else _plan_enabled())
                    if _auth_on and _fired:
                        _why = "authority"
                    elif not _flag_on and not _auth_on:
                        _why = "flag_off"
                    elif _fired:
                        _why = "fired"
                    elif _ir["clarification_required"]:
                        _why = "clarification_required"
                    else:
                        _why = "not_registry_lookup"
                    _slice_decision = {"slice": _kind, "fired": _fired,
                                       "reason": _why}
                self._emit(run_id, "intent_classified", case_id=case_id,
                           message="shadow intent=%s conf=%.2f src=%s" % (
                               _ir["intent_id"], _ir["confidence"],
                               _ir["confidence_source"]),
                           data={"intent": _ir["intent_id"],
                                 "confidence": _ir["confidence"],
                                 "confidence_source": _ir["confidence_source"],
                                 "reason_codes": _ir["reason_codes"],
                                 "clarification_required":
                                     _ir["clarification_required"],
                                 "shadow": not (_qa_slice or _pq_slice),
                                 "latency_ms": _latency_ms,
                                 "route_decision": _rd})
                _intent_shadow.record(run_id=run_id, chat_id=chat_id,
                                      text=text, intent_result=_ir, route=_rd,
                                      actual_execution=(
                                          "insurance-planning-agent"
                                          if _plan_slice
                                          else "insurance-qa-agent"
                                          if (_qa_slice or _pq_slice)
                                          else "existing-agent"),
                                      latency_ms=_latency_ms,
                                      slice_decision=_slice_decision)
            except Exception as _e:  # noqa: BLE001 — shadow must be non-fatal
                print("[server] shadow intent layer skipped (%r)" % _e,
                      file=sys.stderr)

            # K.28-II-DP-P2-1 (product facts may never be answered by
            # the ungoverned legacy loop): in the default slices deploy
            # mode the product_qa slice rides its own feature flag
            # (28.C-2 spec default OFF). A CLEAN product_qa IntentResult
            # (clarify=False, registry_lookup -> insurance-qa-agent) used
            # to fall through to the legacy agent path — no C2, no
            # citation gate, no claim support. Fail closed instead,
            # reusing the existing run-failed terminal (same shape as
            # the deadline supervisor / crash wrapper: fixed
            # consumer-safe copy, single transcript write).
            if (_ir["intent_id"] == "product_qa" and not _pq_slice
                    and _rd.get("agent_id") == "insurance-qa-agent"
                    and _rd.get("decision_source") == "registry_lookup"
                    and not _ir["clarification_required"]):
                self._finish_run(
                    run_id, case_id, "run_failed", "failed",
                    result_status="PRODUCT_QA_UNAVAILABLE",
                    message="product_qa slice unavailable in deploy mode "
                            "'%s' (flag off) — fail closed, no ungoverned "
                            "product answer" % _auth_mode,
                    data={"error_type": "ProductQAUnavailable"},
                    chat_id=chat_id,
                    chat_message="该功能暂时不可用，暂时无法回答产品相关"
                                 "的问题。您可以咨询保险知识类问题，或"
                                 "稍后再试。",
                    chat_kind="error")
                return
            # Phase 28.C-1 / ADR-022 + ruling D4: Insurance QA Agent turn
            # (KnowledgeService evidence -> LLM Gateway -> closure gate ->
            # AnswerContext). 28.C-2: product_qa turns run the Product QA
            # behavior (catalog record + qualifying governed evidence) when
            # its feature flag is ON. The turn ALWAYS produces a user-facing
            # answer (grounded or an honest refusal); an unexpected slice
            # failure falls through to the existing agent path (fail-closed
            # to the status quo — the turn never dies).
            if _qa_slice or _pq_slice:
                _qa_ctx = None
                try:
                    if _pq_slice:
                        from runtime.product_qa_agent import (
                            run_product_qa_turn as _turn_fn)
                    else:
                        from runtime.qa_agent import run_qa_turn as _turn_fn
                    def _qa_emit(event_type, data):
                        # 28.K.22 Policy B: validated content deltas ride
                        # the transient channel (live-only). 28.K.25: the
                        # retrieval milestone reuses the EXISTING tool_*
                        # vocabulary on the DURABLE channel (replay/reconnect
                        # safe, I9) — no new event types.
                        if event_type == "agent_stream_delta":
                            self.bus.publish_transient(run_id, {
                                "event_id": None, "run_id": run_id,
                                "timestamp": events_mod.now_iso(),
                                "event_type": event_type,
                                "stage": None, "skill": None,
                                "status": None, "case_id": case_id,
                                "artifact_id": None, "eval_id": None,
                                "repair_attempt": None, "message": None,
                                "data": data})
                            return
                        self._emit(run_id, event_type, case_id=case_id,
                                   data=data)
                    # 28.K.32-C routing isolation: the QA slice gets its
                    # OWN tier when LLM_QA_MODEL is set; otherwise it keeps
                    # the pre-K.32-C shared fast slot (default unchanged).
                    _qa_provider = fast_provider or provider
                    try:
                        from runtime.agent.config import (
                            load_llm_config as _qa_cfg_load)
                        _qa_cfg = _qa_cfg_load()
                        if _qa_cfg.qa_model:
                            _qa_provider = _qa_cfg.to_provider(qa=True)
                    except Exception:  # noqa: BLE001 — config read must
                        pass            # never kill the turn (fail to fast)
                    _qa_ctx = _turn_fn(
                        question=text, intent_result=_ir,
                        conversation_context=_recent,
                        provider=_qa_provider,
                        emit=_qa_emit)
                except Exception as _qe:  # noqa: BLE001 — slice must not kill the turn
                    print("[server] QA slice failed closed (%r)" % _qe,
                          file=sys.stderr)
                    try:    # 28.B4: the fallback itself is observable
                        from runtime.intent import shadow as _err_shadow
                        _err_shadow.annotate(run_id,
                                             slice_error=repr(_qe)[:120])
                    except Exception:
                        pass
                if _qa_ctx is not None:
                    try:
                        with open(os.path.join(
                                run_dir, "qa-answer-context.json"), "w",
                                encoding="utf-8") as _fh:
                            json.dump(_qa_ctx, _fh, ensure_ascii=False,
                                      indent=2)
                    except Exception:  # noqa: BLE001 — audit file, best effort
                        pass
                    _qa_gr = _qa_ctx["grounding_status"]
                    _qa_rs = "QA_ANSWERED" if _qa_gr != "refused" else \
                        "QA_REFUSED"
                    _qa_slice_id = "product-qa" if _pq_slice else "knowledge-qa"
                    self._emit(run_id, "qa_answered", case_id=case_id,
                               status="completed",
                               message="QA grounding=%s" % _qa_gr,
                               data={"grounding_status": _qa_gr,
                                     "failure_reason":
                                         _qa_ctx["failure_reason"],
                                     "evidence_refs":
                                         _qa_ctx["evidence_refs"],
                                     "retrieval": _qa_ctx["retrieval"],
                                     "generation":
                                         _qa_ctx["generation_provenance"],
                                     "slice": _qa_slice_id,
                                     "answer_len": len(_qa_ctx["answer"])})
                    self._finish_run(
                        run_id, case_id, "run_completed", "completed",
                        result_status=_qa_rs,
                        message=_qa_ctx["answer"],
                        data={"qa": {"grounding_status": _qa_gr,
                                     "failure_reason":
                                         _qa_ctx["failure_reason"]}},
                        chat_id=chat_id,
                        chat_message=_qa_ctx["answer"])
                    # 28.K.27-S1: the ONLY transcript write is the one
                    # inside _finish_run (K.25-S1 sanitized boundary).
                    # A leftover direct add_assistant_message here wrote
                    # the QA refusal a SECOND time, bypassing the
                    # sanitizer — removed (single-write restored).
                    return

            # fresh canonical CaseState for this agent run (no demo seeding!)
            state = cs.new_case_state(case_id, self._wf)
            tk.init_tasks(state, self._wf)
            tr.register_case(case_id, os.path.join(run_dir, case_id))

            def persist():
                cp.save(state, run_dir, None)

            ctx = ToolContext(state, self._wf, run_id, persist=persist)
            agent_state = AgentState(run_id, case_id, chat_id)

            # cross-turn memory: replay the prior conversation turns so the
            # agent knows what the user ALREADY said (the chat owns history;
            # CaseState remains the canonical fact store). run_agent_turn
            # appends the current (last) user message itself.
            history = (self.chats.view(chat_id) or {}).get("messages", [])
            last_user = max((i for i, m in enumerate(history)
                             if m.get("role") == "user"), default=0)
            prev_user_id = None
            for m in history[max(0, last_user - 16):last_user]:  # bound ~8 turns
                if m.get("role") == "user":
                    prev_user_id = agent_state.add_user(m["content"])
                elif m.get("role") == "assistant" and prev_user_id:
                    agent_state.add_assistant(m["content"],
                                              m.get("kind", "finish"), prev_user_id)

            def emit(event_type: str, data: dict) -> None:
                if event_type == "agent_stream_delta":
                    # 28.K.24: a run closed by the deadline supervisor (or
                    # any terminal) emits NO further streaming content
                    with self._lock:
                        if run_id in self._closed:
                            return
                    # live-only streaming text: fans out to open SSE streams,
                    # never enters history/replay/durable records
                    self.bus.publish_transient(run_id, {
                        "event_id": None, "run_id": run_id,
                        "timestamp": events_mod.now_iso(),
                        "event_type": "agent_stream_delta",
                        "stage": None, "skill": None, "status": None,
                        "case_id": case_id, "artifact_id": None, "eval_id": None,
                        "repair_attempt": None,
                        "message": None, "data": data})
                    return
                self._emit(run_id, event_type, case_id=case_id,
                           stage=data.get("stage"), skill=data.get("tool"),
                           status=data.get("status"), message=data.get("summary"),
                           data={k: v for k, v in data.items()
                                 if k not in ("stage", "tool", "status", "summary")})

            # M3 planning slice (Phase 28.D): when fired, the turn is
            # EXECUTED AS the planning agent — the contract guard wraps
            # the SAME spine call (identity + guard, not a second
            # runtime). Guard failure -> legacy fallback + slice_error
            # annotation; exceptions DURING the spine PROPAGATE to the
            # identical crash handling as legacy (E1 equivalence).
            if _plan_slice:
                from runtime.planning_agent import run_planning_turn
                outcome = run_planning_turn(
                    _ir,
                    lambda: run_agent_turn(provider, agent_state, text,
                                           ctx, emit,
                                           fast_provider=fast_provider,
                                           deadline_at=deadline_at),
                    conversation_context=_recent)
                if outcome is None:
                    try:
                        from runtime.intent import shadow as _gshadow
                        _gshadow.annotate(run_id,
                                          slice_error="planning_guard_"
                                          "fallback")
                    except Exception:
                        pass
                    outcome = run_agent_turn(provider, agent_state, text,
                                             ctx, emit,
                                             fast_provider=fast_provider,
                                             deadline_at=deadline_at)
            else:
                outcome = run_agent_turn(provider, agent_state, text, ctx,
                                         emit, fast_provider=fast_provider,
                                         deadline_at=deadline_at)
            persist()

            # fill post-run facts into the shadow record (legacy intent =
            # the agent's own sticky classification, for the consistency
            # metric; still recording only — no execution change)
            try:
                from runtime.intent import shadow as _intent_shadow
                _intent_shadow.annotate(run_id,
                                        legacy_intent=agent_state.intent or None,
                                        legacy_action=outcome.action)
            except Exception:
                pass

            status_map = {"waiting_user": "waiting", "completed": "completed",
                          "needs_review": "needs_review", "failed": "failed"}
            run_status = status_map.get(outcome.status, "needs_review")
            # 28.K.24: idempotent closure (deadline supervisor may have won)
            self._finish_run(
                run_id, case_id, "run_completed", run_status,
                result_status=outcome.status.upper(),
                message=outcome.message,
                data={"agent": {"turns": agent_state.turn,
                                "tool_calls": len(agent_state.tool_history),
                                "usage": agent_state.usage}},
                chat_id=chat_id, chat_message=outcome.message,
                chat_kind="ask" if outcome.action == "ask_user" else "finish")
        except Exception as e:  # noqa: BLE001 — agent wrapper must always terminate
            from runtime.agent.config import redact_secrets
            safe = redact_secrets(repr(e))
            print("[server] agent run %s crashed: %s" % (run_id, safe), file=sys.stderr)
            traceback.print_exc()
            self._finish_run(run_id, case_id, "run_failed", "failed",
                             result_status="CRASHED",
                             message="agent run crashed: %s" % safe[:300],
                             data={"error_type": type(e).__name__},
                             chat_id=chat_id,
                             chat_message="Agent 运行异常，已停止。"
                                          "不会输出未经校验的结果。",
                             chat_kind="error")
        finally:
            run_done.set()  # 28.K.24: release the deadline supervisor
            remove_tap()
            self._active.pop(case_id, None)
            self._active_chat.pop(chat_id, None)
            with self._lock:
                r = self._runs.get(run_id)
                if r is not None:
                    r.pop("_adapter", None)
            self.bus.finish(run_id)


# --------------------------------------------------------------------------- #
# FastAPI application
# --------------------------------------------------------------------------- #
class RunRequest(BaseModel):
    case_id: str


class ChatMessageRequest(BaseModel):
    text: str


class ApprovalDecisionRequest(BaseModel):
    """Phase 9 §17: minimal human decision body (no user system in V0.1)."""
    actor: str = "human"
    reason: str = ""


class ControlCommandRequest(BaseModel):
    """Phase 10 §31: supervisor command body. The API only parses/validates
    and creates the command — the Harness applies it (never direct state
    mutation)."""
    actor: str = "human"
    task_id: str = ""
    reason: str = ""
    key: str = ""
    value: str = ""


def _harness_root(manager: "RunManager") -> str:
    """Root that holds LongRunningHarness projects (Phase 9 approval API)."""
    return os.environ.get(
        "INSURANCE_AGENT_HARNESS_ROOT",
        os.path.join(manager.run_root, "harness-projects"))


def _find_approval(approval_id: str, root: str):
    """(project_id, approval dict | None) — scan project approval stores."""
    from runtime.approval.store import ApprovalStore
    if not os.path.isdir(root):
        return None, None
    for pid in sorted(os.listdir(root)):
        pdir = os.path.join(root, pid)
        if not os.path.isdir(pdir):
            continue
        appr = ApprovalStore(pdir).get(approval_id)
        if appr is not None:
            return pid, appr
    return None, None


def _sse_generator(mgr: RunManager, run_id: str, cursor: Optional[str]):
    """The one SSE generator (GET stream + POST chat-message stream share it)."""
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


def _sse_response(mgr: RunManager, run_id: str, cursor: Optional[str]):
    return StreamingResponse(_sse_generator(mgr, run_id, cursor),
                              media_type="text/event-stream",
                              headers={"Cache-Control": "no-cache, no-transform",
                                       "X-Accel-Buffering": "no"})


def _sse_chunk(event: dict) -> str:
    # transient deltas carry no event_id → no `id:` line, so the browser's
    # Last-Event-ID resume cursor stays anchored to the last DURABLE event
    if event.get("event_id"):
        return "event: runtime\nid: %s\ndata: %s\n\n" % (
            event["event_id"], json.dumps(event, ensure_ascii=False))
    return "event: runtime\ndata: %s\n\n" % json.dumps(event, ensure_ascii=False)


_API_KEY_HEADER = APIKeyHeader(name="Authorization", auto_error=False)


def _validate_production_defaults() -> None:
    """P0.1 hardening: fail the app STARTUP in strict modes when the
    production safety defaults are not satisfiable — an unauthenticated
    or plaintext pilot must never start by forgetting a flag."""
    from runtime import mode as _rt_mode
    _rt_mode.validate_mode(os.environ.get("INSURANCE_AGENT_MODE", "demo"))
    if not _rt_mode.authentication_required():
        return
    identities = runtime_auth.load_identities()
    if not identities:
        raise RuntimeError(
            "AUTHENTICATION_REQUIRED: %s mode requires "
            "INSURANCE_AGENT_API_KEYS (or _FILE) — refusing to start "
            "unauthenticated" % _rt_mode.mode())
    from runtime.state.dataprotection import load_data_key
    if load_data_key() is None:
        raise RuntimeError(
            "ENCRYPTION_REQUIRED: %s mode requires "
            "INSURANCE_AGENT_DATA_KEY or INSURANCE_AGENT_KEYFILE — "
            "refusing to persist client data in plaintext" % _rt_mode.mode())
    # HD-2 (28.H §8): STRICT production knowledge preflight — the
    # KnowledgeService must construct (weknora-only, mock FORBIDDEN,
    # full WeKnora config validated — HG-24-03/RV-P2-01) AND the live
    # backend must be reachable at startup. A misconfigured or down
    # knowledge chain REFUSES TO START; it can never silently fall back
    # to mock knowledge.
    if _rt_mode.is_strict():
        from knowledge.service import default_service, ProviderConfigError
        try:
            svc = default_service()
            health = getattr(svc.provider, "transport", None)
            live_transport = getattr(svc.provider, "_transport", None)
            checker = live_transport or health
            if checker is not None and hasattr(checker, "health")                     and not checker.health():
                raise RuntimeError("WEKNORA_UNREACHABLE")
        except ProviderConfigError as e:
            raise RuntimeError(
                "PRODUCTION_KNOWLEDGE_REQUIRED: %s mode requires the "
                "governed WeKnora knowledge chain (mock is FORBIDDEN) — "
                "%s" % (_rt_mode.mode(), str(e)[:200]))
        except RuntimeError as e:
            if "WEKNORA_UNREACHABLE" in str(e):
                raise RuntimeError(
                    "WEKNORA_UNREACHABLE: %s mode requires a reachable "
                    "WeKnora at startup — refusing to start with an "
                    "unavailable knowledge chain (no mock fallback)"
                    % _rt_mode.mode())
            raise


def _current_identity(header: Optional[str] = None) -> Optional[runtime_auth.Identity]:
    """Resolve the authenticated identity; fail closed (401) when keys are
    configured but credentials are missing/unknown."""
    identities = runtime_auth.load_identities()
    if not identities:
        # P0.1: strict modes blocked keyless startup in
        # _validate_production_defaults; reaching here means the documented
        # DEMO/EVALUATION local-dev mode (loopback, no keys configured).
        return None
    ident = runtime_auth.authenticate(header, identities)
    if ident is None:
        raise HTTPException(status_code=401, detail="unauthenticated")
    return ident


def _identity_dep(request: Request) -> Optional[runtime_auth.Identity]:
    """FastAPI dependency: the authenticated identity for this request,
    or None in documented no-keys local-dev mode. Fails closed (401)
    when keys are configured and credentials are missing/unknown.
    Auth sources (in order): Authorization header, then ?key= query
    parameter — EventSource (browser SSE API) cannot set custom headers,
    so the stream endpoint relies on the query-parameter fallback."""
    header = request.headers.get("authorization")
    if header:
        return _current_identity(header)
    # EventSource auth fallback: ?key=<token> query parameter
    key = request.query_params.get("key")
    if key:
        return _current_identity("Bearer " + key)
    return _current_identity(None)


def _require_role(ident, minimum: str) -> None:
    """Fail closed (403) when the authenticated identity lacks the role.
    No-keys local-dev mode allows access as before."""
    if ident is not None and not ident.has_role(minimum):
        raise HTTPException(status_code=403,
                            detail="role %r required" % minimum)


def _consumer_read_guard(ident, owner) -> None:
    """28.G (B-02): endpoint-boundary ownership gate for CONSUMER objects.

    Uniform 404 for missing-vs-other-owner (D-API-1); 401 when keys are
    configured and the request is unauthenticated (T10); throttled
    probing on top (D-API-2). Internal RBAC identities keep their
    existing any-read duty (O-7); the documented no-keys local-dev
    loopback keeps its frozen all-allow behavior.
    """
    subject = consumer_access.resolve_subject(ident)
    # enumeration throttling applies in the AUTHENTICATED deployment mode
    # only — the documented no-keys local-dev loopback has no probing
    # threat model and must not throttle normal dev/test polling
    if consumer_access.keys_configured() and not consumer_access.consumer_limiter.allow(
            subject or "anonymous"):
        raise HTTPException(status_code=429, detail="too many requests")
    if ident is None and consumer_access.keys_configured():
        raise HTTPException(status_code=401, detail="unauthenticated")
    if not consumer_access.read_allowed(ident, owner):
        raise HTTPException(status_code=404, detail="not found")
    # 28.I D-GOV-6/GOV-9: internal (operator/developer) access to CONSUMER
    # business data is audited — metadata only (who/when/object/action),
    # never message or artifact bodies (GOV-7 by construction)
    if consumer_access.is_internal(ident) and owner             and str(owner).startswith("consumer:"):
        governance.audit(
            actor=consumer_access.resolve_subject(ident) or "internal",
            action="consumer_data_read", object_class="business_content",
            object_id=str(owner), subject=str(owner),
            purpose="operational_access")


def _run_owner(mgr, run_id):
    run = mgr.get_run(run_id)
    if run is not None:
        return run.get("owner")
    return None  # persisted-only (restarted) run: no provable owner -> fail closed


def _authed_actor(ident, body_actor: str = "human") -> str:
    """Approval/command actor = authenticated user when authn is on; the
    legacy body value is honored ONLY in no-keys local-dev mode."""
    if ident is not None:
        return "human:%s" % ident.user
    return body_actor


def create_app(manager: Optional[RunManager] = None) -> FastAPI:
    # Phase 13 P0.1: fail-closed production safety defaults (strict modes
    # must not start unauthenticated / plaintext / with a typo'd mode)
    _validate_production_defaults()
    mgr = manager or RunManager()
    app = FastAPI(title="insurance-agent Web UI API", version="0.1.0")
    # local-dev CORS so the Phase 2 React app (separate port) can consume the API
    # Phase 13 R-06: CORS allowlist (never `*` outside explicit dev mode)
    app.add_middleware(CORSMiddleware,
                       allow_origins=runtime_auth.cors_origins(),
                       allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["*"])

    # ---- Phase 25: request-level observability middleware ----------- #
    @app.middleware("http")
    async def _obs_middleware(request: Request, call_next):
        import runtime.obs as obs
        from runtime.obs import context as obs_ctx
        m = obs.default_metrics()
        m.inc("requests_total")
        with obs_ctx.start_request() as ctx:
            t0 = time.perf_counter()
            try:
                response = await call_next(request)
            except Exception as e:  # noqa: BLE001 — observed, re-raised
                ms = (time.perf_counter() - t0) * 1000
                m.inc("requests_failed_total")
                obs.log("http.request", level="ERROR", status="ERROR",
                            duration_ms=ms, method=request.method,
                            path=request.url.path, error=e)
                raise
            ms = (time.perf_counter() - t0) * 1000
            m.observe("request_duration", ms)
            if response.status_code < 400:
                m.inc("requests_success_total")
            else:
                m.inc("requests_failed_total")
            response.headers["X-Request-Id"] = ctx.request_id
            obs.log("http.request", status="OK",
                        duration_ms=ms, method=request.method,
                        path=request.url.path,
                        http_status=response.status_code)
            return response

    @app.get("/api/health")
    def health():
        """LIVENESS (Phase 25F): the process answering means the
        process is alive. Downstream dependencies are deliberately NOT
        consulted here — see /api/ready. The `status: "ok"` field is
        the historical Phase-1 API contract (WebUI + existing tests);
        the Phase 25 liveness vocabulary lives under `liveness`."""
        from runtime.obs.health import liveness
        out = liveness()
        out.update({"status": "ok",      # backward-compatible contract
                    "liveness": "LIVE",  # Phase 25F vocabulary
                    "version": "0.1.0", "bus": mgr.bus.stats()})
        return out

    @app.get("/api/ready")
    def ready():
        """READINESS (Phase 25F): can this instance accept production
        workload NOW — mode-aware dependency checks with short
        timeouts; READY / NOT_READY / DEGRADED."""
        from runtime.obs.health import readiness
        r = readiness()
        return JSONResponse(status_code=200 if r["status"] == "READY"
                            else (503 if r["status"] == "NOT_READY"
                                  else 200), content=r)

    @app.get("/api/diagnostics")
    def diagnostics(ident=Depends(_identity_dep)):
        """Phase 25G: read-only runtime diagnostics. OPERATOR role
        required when authentication is active; the payload is scrubbed
        (no secrets, no env dump)."""
        _require_role(ident, "OPERATOR")
        from runtime.obs import diagnostics_snapshot
        from runtime.obs.metrics import default_metrics
        out = diagnostics_snapshot(include_readiness=True)
        out["metrics"] = default_metrics().snapshot()
        return out

    @app.get("/api/metrics")
    def metrics(ident=Depends(_identity_dep)):
        """Phase 25D: the metrics snapshot (counters + latency
        percentiles + honest UNKNOWNs). OPERATOR role required when
        authentication is active."""
        _require_role(ident, "OPERATOR")
        from runtime.obs.metrics import default_metrics
        return default_metrics().snapshot()

    @app.get("/api/cases")
    def list_cases(ident=Depends(_identity_dep)):
        """Developer console data (demo cases). OPERATOR role required
        when authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "OPERATOR")
        return {"cases": mgr.cases()}

    @app.post("/api/runs", status_code=201)
    def create_run(req: RunRequest, ident=Depends(_identity_dep)):
        """Developer demo-run creation (28.G: OPERATOR gate — the demo
        pipeline is an internal surface; the consumer path is /api/chats)."""
        _require_role(ident, "OPERATOR")
        case = mgr.case_by_id(req.case_id)
        if case is None:
            raise HTTPException(status_code=404, detail={
                "error": "unknown case_id",
                "available": [c["id"] for c in mgr.cases()]})
        run, active_run_id = mgr.create_run(
            case, owner=consumer_access.resolve_subject(ident))
        if run is None:
            # M-1: the case already has an active run — never start a second one
            # (its events would be mis-attributed). Exact body shape is the API contract.
            return JSONResponse(status_code=409, content={
                "error": "case_already_running",
                "run_id": active_run_id,
                "case_id": req.case_id})
        return {"run_id": run["run_id"], "case_id": run["case_id"], "status": run["status"]}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, ident=Depends(_identity_dep)):
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        run = mgr.get_run(run_id)
        if run is not None:
            return {k: v for k, v in run.items() if not k.startswith("_")}
        # Phase 27.7.6-F: registry miss + persisted dir -> restored summary
        if _run_dir_exists(mgr, run_id):
            return _restored_run(mgr, run_id)
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/api/runs/{run_id}/events")
    def get_events(run_id: str, after_event_id: Optional[str] = None,
                   ident=Depends(_identity_dep)):
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        _require_run_readable(mgr, run_id)
        if mgr.get_run(run_id) is not None:
            # live run: the bus history, exactly as before
            evs = mgr.bus.events_for(run_id, after_event_id=after_event_id)
        else:
            # Phase 27.7.6-F: restarted backend -> deterministic trace replay
            evs = _replay_events(mgr, run_id)
            if after_event_id:
                cur = _evt_seq(after_event_id)
                evs = [e for e in evs if _evt_seq(e.get("event_id")) > cur]
        return {"run_id": run_id, "count": len(evs), "events": evs}

    @app.get("/api/runs/{run_id}/artifacts")
    def get_artifacts(run_id: str, ident=Depends(_identity_dep)):
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        # Phase 27.7.6-F: registry OR persisted dir (data path already disk)
        _require_run_readable(mgr, run_id)
        arts = mgr.artifacts_of(run_id)
        if arts is None:
            raise HTTPException(status_code=404, detail="no persisted state for this run yet")
        return {"run_id": run_id, "count": len(arts), "artifacts": arts}

    @app.get("/api/runs/{run_id}/artifacts/{artifact_type}")
    def get_artifact(run_id: str, artifact_type: str,
                     ident=Depends(_identity_dep)):
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        _require_run_readable(mgr, run_id)
        detail = mgr.artifact_detail(run_id, artifact_type)
        if detail is None:
            raise HTTPException(status_code=404, detail="unknown artifact_type for this run")
        return detail

    def _guard_chat_mutation(ident, chat_id: str) -> None:
        """28.G: messages may only flow into the subject's OWN chat. An
        unknown chat_id creates nothing here — the turn start binds a NEW
        chat to the requesting subject (anti-injection, T5)."""
        chat = mgr.chats.view(chat_id)
        if chat is None:
            if ident is None and consumer_access.keys_configured():
                raise HTTPException(status_code=401, detail="unauthenticated")
            # bind the new chat to the requesting subject up front
            mgr.chats.get_or_create(chat_id,
                                    owner=consumer_access.resolve_subject(ident))
            return
        _consumer_read_guard(ident, chat.get("owner"))

    @app.get("/api/consumer/whoami")
    def consumer_whoami(ident=Depends(_identity_dep)):
        """Minimal identity probe (28.G): the frontend resolves its subject
        for storage scoping / the key gate. Never returns secrets."""
        if ident is None:
            if consumer_access.keys_configured():
                raise HTTPException(status_code=401, detail="unauthenticated")
            return {"subject": None, "role": None, "mode": "local-dev"}
        return {"subject": consumer_access.resolve_subject(ident),
                "role": ident.role, "mode": "authenticated"}

    @app.delete("/api/consumer/chats/{chat_id}")
    def delete_consumer_chat(chat_id: str, ident=Depends(_identity_dep)):
        """28.I (D-GOV-3/4, B-04): consumer-initiated business-data
        deletion. authenticate → resolve subject → OWNERSHIP → deletion
        policy (legal hold / eligibility) → auditable cascade:
        Conversation → Messages → Runs (dirs: events/answer-context/
        artifacts) → bus trace → opaque artifact refs. Tombstone carries
        identity/reason only; audit records are INDEPENDENT (never
        cascaded away)."""
        if ident is None and consumer_access.keys_configured():
            raise HTTPException(status_code=401, detail="unauthenticated")
        subject = consumer_access.resolve_subject(ident)
        chat = mgr.chats.view(chat_id)
        if chat is None:
            governance.audit(actor=subject or "anonymous",
                             action="deletion_request",
                             object_class="business_content",
                             object_id=chat_id, subject=subject or "",
                             purpose="consumer_deletion", outcome="404")
            raise HTTPException(status_code=404, detail="not found")
        _consumer_read_guard(ident, chat.get("owner"))  # ownership/uniform 404
        governance.audit(actor=subject or "local-dev",
                         action="deletion_request",
                         object_class="business_content",
                         object_id=chat_id, subject=str(chat.get("owner")),
                         purpose="consumer_deletion")
        # policy: legal hold blocks; a consumer request deletes its own
        # business content at ANY time (its lifecycle, D-GOV-3)
        hold_key = "business_content:%s" % chat_id
        eligible, reason = governance.deletion_eligible(
            governance.BUSINESS, time.time(), legal_hold=False,
            consumer_requested=True)
        if governance.has_legal_hold(hold_key):
            eligible, reason = False, "legal_hold"
        if not eligible:
            governance.audit(actor=subject or "local-dev",
                             action="deletion_blocked",
                             object_class="business_content",
                             object_id=chat_id, subject=str(chat.get("owner")),
                             purpose="consumer_deletion", outcome=reason)
            raise HTTPException(status_code=409, detail=reason)
        # ---- cascade ----
        import shutil as _shutil
        revoked_refs = 0
        for run_id in list(chat.get("runs") or []):
            if _SAFE_RUN_ID(run_id):
                run_dir = os.path.join(mgr.run_root, run_id)
                if os.path.isdir(run_dir):
                    _shutil.rmtree(run_dir, ignore_errors=True)
            with mgr._lock:
                mgr._runs.pop(run_id, None)
                for k, v in list(mgr._active.items()):
                    if v == run_id:
                        mgr._active.pop(k, None)
                for k, v in list(mgr._active_chat.items()):
                    if v == run_id:
                        mgr._active_chat.pop(k, None)
            mgr.bus.purge(run_id)
            revoked_refs += consumer_access.artifact_refs.revoke_for_run(run_id)
            governance.write_tombstone(
                "run", run_id, reason="conversation_deletion",
                actor=subject or "local-dev")
        removed = mgr.chats.delete(chat_id)
        governance.write_tombstone(
            "conversation", chat_id, reason="consumer_deletion",
            actor=subject or "local-dev")
        governance.audit(actor=subject or "local-dev",
                         action="deletion_executed",
                         object_class="business_content",
                         object_id=chat_id, subject=str(chat.get("owner")),
                         purpose="consumer_deletion")
        return {"deleted": True, "chat_id": chat_id,
                "runs_deleted": len(chat.get("runs") or []),
                "artifact_refs_revoked": revoked_refs,
                "messages_removed": len(removed.get("messages", [])
                                        if removed else [])}

    @app.get("/api/governance/audit")
    def governance_audit(ident=Depends(_identity_dep)):
        """Operator-only audit view (D-GOV-6). Records are metadata-only."""
        _require_role(ident, "OPERATOR")
        return {"records": governance.audit_records()}

    @app.get("/api/runs/{run_id}/artifact-refs/{artifact_type}")
    def issue_artifact_ref(run_id: str, artifact_type: str,
                           ident=Depends(_identity_dep)):
        """D-05′: issue a high-entropy opaque consumer artifact reference.
        The reference is NOT authorization — resolution re-checks run
        ownership (see /api/consumer/artifacts/{ref})."""
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        _require_run_readable(mgr, run_id)
        ref = consumer_access.artifact_refs.issue(run_id, artifact_type)
        return {"ref": ref}

    @app.get("/api/consumer/artifacts/{ref}")
    def consumer_artifact_by_ref(ref: str, ident=Depends(_identity_dep)):
        """D-05′ resolution: opaque ref -> (run, type) -> OWNERSHIP CHECK ->
        artifact detail (same payload shape as the run-keyed endpoint)."""
        resolved = consumer_access.artifact_refs.resolve(ref)
        if resolved is None:
            raise HTTPException(status_code=404, detail="not found")
        run_id, artifact_type = resolved
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        _require_run_readable(mgr, run_id)
        detail = mgr.artifact_detail(run_id, artifact_type)
        if detail is None:
            raise HTTPException(status_code=404, detail="not found")
        return detail

    # ---- Phase 27.7.6 v2: Review Card projection (read-only) ------------- #
    @app.get("/api/runs/{run_id}/review-card")
    def get_review_card(run_id: str, ident=Depends(_identity_dep)):
        """Operator review data. REVIEWER role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "REVIEWER")
        """Risk-based review card for a FINISHED run, generated on demand.

        Read-only: computes the card in memory (the generator's
        generate_card path — never its file-writing main) and returns
        it. Keyed by the run DIRECTORY, not the in-memory registry, so
        cards keep working after a backend restart. A run whose state
        was never persisted gets the generator's fail-closed card.
        """
        run_dir = os.path.join(mgr.run_root, run_id)
        if not _SAFE_RUN_ID(run_id) or not os.path.isdir(run_dir):
            raise HTTPException(status_code=404, detail="unknown run_id")
        return _review_card_generator().generate_card(run_dir)

    @app.get("/api/runs/{run_id}/stream")
    def stream_run(run_id: str, after_event_id: Optional[str] = None,
                   request: Request = None, ident=Depends(_identity_dep)):
        _consumer_read_guard(ident, _run_owner(mgr, run_id))
        _require_run(mgr, run_id)
        # resume cursor priority: explicit query param, then the SSE Last-Event-ID header
        cursor = after_event_id or (request.headers.get("last-event-id") if request else None)
        return _sse_response(mgr, run_id, cursor)

    # ------------------------------------------------------------------ #
    # Mode B: agent chats (Phase 2.6) — the frontend never sees the LLM
    # ------------------------------------------------------------------ #
    @app.get("/api/agent/config")
    def agent_config():
        return mgr.agent_provider_status()

    @app.post("/api/chats", status_code=201)
    def create_chat(ident=Depends(_identity_dep)):
        if ident is None and consumer_access.keys_configured():
            raise HTTPException(status_code=401, detail="unauthenticated")
        chat = mgr.chats.get_or_create(
            None, owner=consumer_access.resolve_subject(ident))
        return {"chat_id": chat["chat_id"]}

    @app.get("/api/chats/{chat_id}")
    def get_chat(chat_id: str, ident=Depends(_identity_dep)):
        chat = mgr.chats.view(chat_id)
        if chat is None:
            # D-API-1: missing and other-owner are INDISTINGUISHABLE on the
            # consumer surface — same status AND same detail
            if ident is None and consumer_access.keys_configured():
                raise HTTPException(status_code=401, detail="unauthenticated")
            raise HTTPException(status_code=404, detail="not found")
        _consumer_read_guard(ident, chat.get("owner"))
        return chat

    @app.post("/api/chats/{chat_id}/messages")
    def send_chat_message(chat_id: str, req: ChatMessageRequest,
                          ident=Depends(_identity_dep)):
        _guard_chat_mutation(ident, chat_id)
        return _start_agent_turn(mgr, chat_id, req)

    @app.post("/api/chats/{chat_id}/messages/stream")
    def send_chat_message_stream(chat_id: str, req: ChatMessageRequest,
                                 request: Request = None,
                                 ident=Depends(_identity_dep)):
        _guard_chat_mutation(ident, chat_id)
        result = _start_agent_turn(mgr, chat_id, req)
        cursor = request.headers.get("last-event-id") if request else None
        return _sse_response(mgr, result["run_id"], cursor)

    # ---- Phase 9 §17: minimal human-approval API (state only; execution
    #      resumes via the Harness — LongRunningHarness.resume_approval). ---
    @app.get("/api/projects/{project_id}/approvals")
    def list_project_approvals(project_id: str, ident=Depends(_identity_dep)):
        """Operator review data. REVIEWER role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "REVIEWER")
        from runtime.approval.store import ApprovalStore
        pdir = os.path.join(_harness_root(mgr), project_id)
        if not os.path.isdir(pdir):
            return JSONResponse({"error": "project not found"}, status_code=404)
        return {"project_id": project_id,
                "approvals": ApprovalStore(pdir).all()}

    @app.get("/api/approvals/{approval_id}")
    def get_approval(approval_id: str, ident=Depends(_identity_dep)):
        """Operator review data. REVIEWER role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "REVIEWER")
        pid, appr = _find_approval(approval_id, _harness_root(mgr))
        if appr is None:
            return JSONResponse({"error": "approval not found"}, status_code=404)
        # Phase 27.7.6-C: read-only projection of the approval's
        # existing context — no state change, no computation.
        ctx = appr.get("context") or {}
        review_context = {}
        run_id = ctx.get("run_id")
        if run_id:
            review_context["run_id"] = run_id
        artifact_ids = ctx.get("artifact_ids")
        if artifact_ids:
            review_context["artifact_ids"] = artifact_ids
        return {"project_id": pid, "approval": appr,
                "review_context": review_context}

    @app.post("/api/approvals/{approval_id}/approve")
    def approve_approval(approval_id: str, req: ApprovalDecisionRequest,
                         ident=Depends(_identity_dep)):
        _require_role(ident, "REVIEWER")
        return _resolve_approval(mgr, approval_id, "approve", req,
                                 actor=_authed_actor(ident, req.actor))

    @app.post("/api/approvals/{approval_id}/reject")
    def reject_approval(approval_id: str, req: ApprovalDecisionRequest,
                        ident=Depends(_identity_dep)):
        _require_role(ident, "REVIEWER")
        return _resolve_approval(mgr, approval_id, "reject", req,
                                 actor=_authed_actor(ident, req.actor))

    # ---- Phase 10 §31: supervisor / control-plane endpoints -------------- #
    @app.get("/api/projects/{project_id}/supervisor")
    def get_supervisor(project_id: str, ident=Depends(_identity_dep)):
        """Operator control data. OPERATOR role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "OPERATOR")
        from runtime.control.store import ControlStore
        pdir = os.path.join(_harness_root(mgr), project_id)
        if not os.path.isdir(pdir):
            return JSONResponse({"error": "project not found"}, status_code=404)
        return {"project_id": project_id,
                "supervisor": ControlStore(pdir).load_supervisor(project_id)}

    @app.get("/api/projects/{project_id}/alerts")
    def get_alerts(project_id: str, ident=Depends(_identity_dep)):
        """Operator control data. OPERATOR role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "OPERATOR")
        from runtime.control.store import ControlStore
        pdir = os.path.join(_harness_root(mgr), project_id)
        if not os.path.isdir(pdir):
            return JSONResponse({"error": "project not found"}, status_code=404)
        return {"project_id": project_id, "alerts": ControlStore(pdir).alerts()}

    @app.get("/api/projects/{project_id}/notifications")
    def get_notifications(project_id: str, ident=Depends(_identity_dep)):
        """Operator control data. OPERATOR role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "OPERATOR")
        from runtime.control.store import ControlStore
        pdir = os.path.join(_harness_root(mgr), project_id)
        if not os.path.isdir(pdir):
            return JSONResponse({"error": "project not found"}, status_code=404)
        return {"project_id": project_id,
                "notifications": ControlStore(pdir).notifications()}

    @app.get("/api/projects/{project_id}/control-commands")
    def get_control_commands(project_id: str, ident=Depends(_identity_dep)):
        """Operator control data. OPERATOR role required when
        authentication is active (28.E-6 space boundary)."""
        _require_role(ident, "OPERATOR")
        from runtime.control.store import ControlStore
        pdir = os.path.join(_harness_root(mgr), project_id)
        if not os.path.isdir(pdir):
            return JSONResponse({"error": "project not found"}, status_code=404)
        return {"project_id": project_id,
                "commands": ControlStore(pdir).commands()}

    @app.post("/api/projects/{project_id}/control/pause")
    def control_pause(project_id: str, req: ControlCommandRequest, ident=Depends(_identity_dep)):
        return _control_command(mgr, project_id, "PAUSE", req, ident=ident)

    @app.post("/api/projects/{project_id}/control/resume")
    def control_resume(project_id: str, req: ControlCommandRequest, ident=Depends(_identity_dep)):
        return _control_command(mgr, project_id, "RESUME", req, ident=ident)

    @app.post("/api/projects/{project_id}/control/retry")
    def control_retry(project_id: str, req: ControlCommandRequest, ident=Depends(_identity_dep)):
        return _control_command(mgr, project_id, "RETRY_TASK", req, ident=ident)

    @app.post("/api/projects/{project_id}/control/replan")
    def control_replan(project_id: str, req: ControlCommandRequest, ident=Depends(_identity_dep)):
        return _control_command(mgr, project_id, "REPLAN", req, ident=ident)

    @app.post("/api/projects/{project_id}/control/cancel")
    def control_cancel(project_id: str, req: ControlCommandRequest, ident=Depends(_identity_dep)):
        return _control_command(mgr, project_id, "CANCEL", req, ident=ident)

    @app.post("/api/projects/{project_id}/control/information")
    def control_information(project_id: str, req: ControlCommandRequest, ident=Depends(_identity_dep)):
        return _control_command(mgr, project_id, "PROVIDE_INFORMATION", req, ident=ident)

    return app


def _control_command(mgr: "RunManager", project_id: str, command: str,
                     req: "ControlCommandRequest",
                     ident: Optional[runtime_auth.Identity] = None) -> dict:
    """Phase 10 §32: HTTP -> ControlPlane -> Harness. The API never mutates
    runtime state directly; the Harness validates and applies the audited
    command (state-only in this process — agent execution continues in the
    harness runtime)."""
    from runtime.harness import LongRunningHarness, load_project
    root = _harness_root(mgr)
    project = load_project(root, project_id)
    if project is None:
        return JSONResponse({"error": "project not found"}, status_code=404)
    payload = {}
    for key in ("task_id", "reason", "key", "value"):
        if getattr(req, key, ""):
            payload[key] = getattr(req, key)
    _require_role(ident, "OPERATOR")
    harness = LongRunningHarness(root)
    plane = harness._control_plane(project)
    actor = ("human:%s" % ident.user) if ident is not None else         (req.actor or "human")
    out = plane.command(command, actor=actor, payload=payload)
    if not out.get("ok"):
        return JSONResponse({"error": out.get("error"),
                             "command": out.get("command")}, status_code=409)
    return {"project_id": project_id, "result": out}


def _resolve_approval(mgr: "RunManager", approval_id: str, op: str,
                      req: "ApprovalDecisionRequest",
                      actor: Optional[str] = None) -> dict:
    """Idempotent approve/reject on the approval STATE. The actor comes
    from the AUTHENTICATED identity (R-06); non-human actors are refused."""
    from runtime.approval import ApprovalManager
    from runtime.harness import load_project
    pid, appr = _find_approval(approval_id, _harness_root(mgr))
    if appr is None:
        return JSONResponse({"error": "approval not found"}, status_code=404)
    pdir = os.path.join(_harness_root(mgr), pid)
    project = load_project(_harness_root(mgr), pid)
    emit = None
    if project is not None:
        def emit(event_type, data, _p=project):
            safe = {k: v for k, v in (data or {}).items()
                    if isinstance(v, (str, int, float, bool)) or v is None}
            _p._event(event_type, **safe)
    manager = ApprovalManager(pdir, emit=emit)
    actor = actor or req.actor
    if op == "approve":
        out = manager.approve(approval_id, actor=actor)
    else:
        out = manager.reject(approval_id, actor=actor, reason=req.reason)
    if not out.get("ok"):
        return JSONResponse({"error": out.get("error"), "approval": out.get("approval")},
                            status_code=409)
    return {"project_id": pid, "result": out}


def _start_agent_turn(mgr: RunManager, chat_id: str, req: ChatMessageRequest) -> dict:
    """Create the agent run for one user message (shared by both message routes).

    Phase 13 R-05: the provider data-policy gate runs BEFORE any user text
    reaches the LLM — real client data with an unverified provider policy
    fails closed here."""
    from runtime.agent.data_policy import client_data_allowed
    allowed, gate_reason = client_data_allowed()
    if not allowed:
        raise HTTPException(status_code=451, detail=gate_reason)
    if not req.text or not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    try:
        _chat = mgr.chats.view(chat_id)
        _owner = (_chat or {}).get("owner")
        run, reason = mgr.create_agent_run(chat_id, req.text.strip(),
                                           owner=_owner)
    except ProviderNotConfigured as e:
        # fail CLOSED — never silently fall back to the deterministic demo
        raise HTTPException(status_code=503, detail={
            "error": "llm_provider_not_configured",
            "message": ("LLM provider is not configured. Please configure the "
                        "provider (LLM_PROVIDER / LLM_MODEL / LLM_API_KEY) or "
                        "switch to Demo Mode."),
        }) from e
    if run is None:
        return JSONResponse(status_code=409, content={
            "error": "chat_busy", "run_id": reason.split(":", 1)[1],
            "chat_id": chat_id})
    return {"chat_id": chat_id, "run_id": run["run_id"], "status": run["status"]}


def _require_run(mgr: RunManager, run_id: str) -> None:
    if mgr.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="unknown run_id")


def _SAFE_RUN_ID(run_id: str) -> bool:
    """Disk-path safety for endpoints that read the run DIRECTORY
    (review-card): run ids are `run_<hex>`-shaped; refuse anything
    with path separators or dots before touching the filesystem."""
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", run_id))


def _run_dir_exists(mgr: "RunManager", run_id: str) -> bool:
    return _SAFE_RUN_ID(run_id) and os.path.isdir(os.path.join(mgr.run_root, run_id))


def _require_run_readable(mgr: "RunManager", run_id: str) -> None:
    """Phase 27.7.6-F: READ endpoints accept a run that lives on disk even
    when the in-memory registry is gone (backend restarted). Unknown ids
    still 404; a registry hit keeps the exact pre-existing live path."""
    if mgr.get_run(run_id) is not None or _run_dir_exists(mgr, run_id):
        return
    raise HTTPException(status_code=404, detail="unknown run_id")


def _restored_run(mgr: "RunManager", run_id: str) -> dict:
    """Minimal honest metadata for a registry-miss run (read-only restore;
    never a full runtime). Marked `restored` so consumers can tell."""
    state = mgr._load_state(run_id)
    if state is not None:
        _, run_status = _TERMINAL.get(state.get("status"), ("run_failed", "failed"))
        return {"run_id": run_id, "case_id": state.get("case_id"),
                "status": run_status,
                "created_at": state.get("created_at"), "restored": True}
    # trace-only run (state never persisted, e.g. WAITING_FOR_USER path)
    return {"run_id": run_id, "case_id": mgr._case_id_on_disk(run_id),
            "status": None, "created_at": None, "restored": True}


def _evt_seq(event_id: Optional[str]) -> int:
    """Sequence number of an `evt_%06d` id (0 when unparseable)."""
    try:
        return int(str(event_id or "").rsplit("_", 1)[-1])
    except ValueError:
        return 0


def _replay_events(mgr: "RunManager", run_id: str) -> list:
    """Phase 27.7.6-F: deterministic replay of a finished run's recorded
    trace.jsonl through the SAME TraceEventAdapter mapping used live.

    Sequence numbers mirror the live interleave (run_started=1, mapped
    trace records 2..n, terminal last), so replayed event ids match the
    pre-restart stream exactly. The two run-level markers are lifecycle
    reconstructions anchored to the first/last recorded trace timestamps
    and carry data.restored=True — no event is invented, nothing mocked."""
    import glob as globmod
    traces = sorted(globmod.glob(
        os.path.join(mgr.run_root, run_id, "*", "trace.jsonl")))
    if not traces:
        return []
    trace_path = traces[0]
    case_id = os.path.basename(os.path.dirname(trace_path))
    recs = []
    with open(trace_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except ValueError:
                continue                      # skip corrupt line, keep order
    adapter = events_mod.TraceEventAdapter()
    out: list = []
    seq = 1
    first_ts = (recs[0].get("timestamp") if recs else None) or events_mod.now_iso()
    out.append(events_mod.RuntimeEvent(
        event_id=events_mod.event_id_for(run_id, seq), run_id=run_id,
        event_type="run_started", case_id=case_id, timestamp=first_ts,
        message="Run started for case %s" % case_id,
        data={"restored": True}).to_dict())
    last_ts = first_ts
    for rec in recs:
        if rec.get("timestamp"):
            last_ts = rec["timestamp"]
        ev = adapter.to_event(rec, run_id, seq + 1)
        if ev is not None:
            seq += 1
            out.append(ev.to_dict())
    state = mgr._load_state(run_id)
    mapped = _TERMINAL.get((state or {}).get("status"))
    if mapped is not None:
        event_type, run_status = mapped
        seq += 1
        out.append(events_mod.RuntimeEvent(
            event_id=events_mod.event_id_for(run_id, seq), run_id=run_id,
            event_type=event_type, case_id=case_id, status=run_status,
            timestamp=last_ts,
            message="restored terminal: %s" % (state or {}).get("status"),
            data={"restored": True}).to_dict())
    return out


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
