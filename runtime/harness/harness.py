"""Long-Running Harness implementation (Phase 3 V0.1).

Minimal, file-persisted task runner on top of the existing deterministic
runtime. One Harness instance owns zero in-memory execution state — everything
survives a process kill and can be picked up by a NEW instance via `resume()`.

Persistence layout (all JSON, under `harness_root`):

    <harness_root>/
        projects.json                # index of all projects
        <project_id>/
            project.json             # project metadata + task statuses
            checkpoints.jsonl        # harness-level checkpoint log
            events.jsonl             # harness-level event log
            case/                    # existing CaseState store (store.py layout)
                case_state.json
                artifacts/*.json
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from typing import Callable, Optional

from runtime import orchestrator as orch
from runtime import tasks as tk
from runtime import checkpoint as cp
from runtime import trace as tr
from runtime import artifact_registry as reg_mod
from runtime.state import case_state as cs
from runtime.state import store as state_store
from runtime.state import transitions

# --------------------------------------------------------------------------- #
# task type → workflow stage id (V0.1: code-defined, not LLM-generated §14)
# --------------------------------------------------------------------------- #
TASK_CHAIN = [
    "client_profile",
    "requirement",
    "risk",
    "coverage_gap",
    "solution",
    "knowledge_search",
    "product_candidates",
    "recommendation",
    "report",
]

# map task_type → (stage_id, artifact_type)
TASK_DEFS = {
    "client_profile":    ("client-intake", "client-profile"),
    "requirement":       ("requirement-analysis", "requirement-analysis"),
    "risk":              ("risk-analysis", "risk-assessment"),
    "coverage_gap":      ("coverage-gap-analysis", "coverage-gap-analysis"),
    "solution":          ("solution", "solution-plan"),
    # knowledge_search is a SERVICE not a stage; its artifact is created by
    # product-candidate-provider's service round-trip
    "knowledge_search":  ("product-candidate-provider", "knowledge-evidence"),
    "product_candidates": ("product-candidate-provider", "product-candidates"),
    "recommendation":    ("product-recommendation", "product-recommendation"),
    "report":            ("report-generation", "insurance-report"),
}

# tasks that map to the same workflow stage run only once
_UNIQUE_STAGES = {"product-candidate-provider"}

HARNESS_TASK_EVENTS = {
    "project_created", "task_created", "task_started", "task_completed",
    "task_failed", "task_skipped", "checkpoint_created", "checkpoint_loaded",
    "run_resumed",
    # Phase 7 parallel scheduler: batch selection + crash-recovery reset
    "task_scheduled", "task_recovered",
}

_TASK_STATUSES = {"PENDING", "RUNNING", "PASSED", "FAILED", "BLOCKED",
                  "NEEDS_REVIEW", "COMPLETED"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _uid(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:8])


# --------------------------------------------------------------------------- #
# Project model
# --------------------------------------------------------------------------- #
class Project:
    def __init__(self, project_id: str, name: str, case_id: str,
                 harness_root: str):
        self.project_id = project_id
        self.name = name
        self.case_id = case_id
        self.status = "pending"
        self.state_version = 0
        self.created_at = _now()
        self.updated_at = _now()
        self.tasks: list = []       # [task dicts]
        self._root = harness_root
        self._dir = os.path.join(harness_root, project_id)
        self._lock = threading.Lock()

    # ---------------- persistence ------------------------------------------- #
    def _save(self) -> None:
        os.makedirs(self._dir, exist_ok=True)
        doc = {
            "project_id": self.project_id,
            "name": self.name,
            "case_id": self.case_id,
            "status": self.status,
            "state_version": self.state_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "tasks": self.tasks,
        }
        with open(os.path.join(self._dir, "project.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        _index_upsert(self._root, {
            "project_id": self.project_id, "name": self.name,
            "case_id": self.case_id, "status": self.status,
            "updated_at": self.updated_at,
        })

    def _append_jsonl(self, filename: str, record: dict) -> None:
        os.makedirs(self._dir, exist_ok=True)
        with open(os.path.join(self._dir, filename), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_jsonl(self, filename: str) -> list:
        path = os.path.join(self._dir, filename)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    # ---------------- task management ---------------------------------------- #
    def create_task(self, task_type: str, dependencies: Optional[list] = None) -> dict:
        task = {
            "task_id": _uid("task"),
            "project_id": self.project_id,
            "parent_task_id": None,
            "task_type": task_type,
            "status": "PENDING",
            "dependencies": dependencies or [],
            "input_artifacts": [],
            "output_artifacts": [],
            "attempt": 0,
            "max_attempts": 3,
            "created_at": _now(),
            "updated_at": _now(),
        }
        self.tasks.append(task)
        self.state_version += 1
        self.updated_at = _now()
        self._save()
        self._event("task_created", task_id=task["task_id"], task_type=task_type)
        return task

    def get_task(self, task_id: str) -> Optional[dict]:
        return next((t for t in self.tasks if t["task_id"] == task_id), None)

    def _set_task(self, task_id: str, **kw) -> None:
        t = self.get_task(task_id)
        if t is None:
            return
        t.update(kw)
        t["updated_at"] = _now()
        self.state_version += 1
        self.updated_at = _now()
        self._save()

    def _event(self, event_type: str, **data) -> dict:
        rec = {"event_type": event_type, "project_id": self.project_id,
               "timestamp": _now(), **data}
        self._append_jsonl("events.jsonl", rec)
        return rec

    def events(self) -> list:
        return self._read_jsonl("events.jsonl")

    def checkpoints(self) -> list:
        return self._read_jsonl("checkpoints.jsonl")

    def to_public(self) -> dict:
        return {
            "project_id": self.project_id, "name": self.name,
            "case_id": self.case_id, "status": self.status,
            "state_version": self.state_version,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "task_ids": [t["task_id"] for t in self.tasks],
            "tasks": self.tasks,
        }


# --------------------------------------------------------------------------- #
# project index (harness_root/projects.json)
# --------------------------------------------------------------------------- #
def _index_path(harness_root: str) -> str:
    return os.path.join(harness_root, "projects.json")


def _index_read(harness_root: str) -> list:
    path = _index_path(harness_root)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _index_upsert(harness_root: str, entry: dict) -> None:
    os.makedirs(harness_root, exist_ok=True)
    entries = _index_read(harness_root)
    entries = [e for e in entries if e["project_id"] != entry["project_id"]]
    entries.append(entry)
    with open(_index_path(harness_root), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def list_projects(harness_root: str) -> list:
    return _index_read(harness_root)


def load_project(harness_root: str, project_id: str) -> Optional[Project]:
    """Load a project from disk — this is what a NEW process calls."""
    path = os.path.join(harness_root, project_id, "project.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    p = Project(doc["project_id"], doc["name"], doc["case_id"], harness_root)
    p.status = doc["status"]
    p.state_version = doc["state_version"]
    p.created_at = doc["created_at"]
    p.updated_at = doc["updated_at"]
    p.tasks = doc["tasks"]
    return p


# --------------------------------------------------------------------------- #
# Phase 7 §8: worker execution contract
# --------------------------------------------------------------------------- #
class TaskExecutionResult:
    """What ONE worker returns to the scheduler. The worker EXECUTES only —
    it never decides PASS/FAIL and never mutates scheduler or project state.
    """

    def __init__(self, task_id: str, agent_id: str = "", status: str = "",
                 artifacts: Optional[list] = None,
                 execution_metadata: Optional[dict] = None, error: str = "",
                 worker_state: Optional[dict] = None,
                 events: Optional[list] = None):
        self.task_id = task_id
        self.agent_id = agent_id
        self.status = status            # ARTIFACT_READY | OK | AGENT_FAILED | NEEDS_REVIEW
        self.artifacts = artifacts or []   # produced artifact types (candidates)
        self.execution_metadata = execution_metadata or {}
        self.error = error
        self.worker_state = worker_state   # isolated CaseState copy (merged by the scheduler)
        self.events = events or []         # worker events, replayed at commit

    def get(self, key, default=None):
        return {"outcome": self.status, "reasons": ([self.error] if self.error else []),
                "error_code": self.error}.get(key, default)


class _WorkerProjectProxy:
    """Read-only project stand-in handed to workers (§7).

    Workers must not touch shared project state. The proxy only exposes the
    project dir (so the MessageBus persists agent messages in the right
    place) and CAPTURES _event() calls for the scheduler to replay in
    deterministic commit order.
    """

    def __init__(self, project_dir: str, sink: list):
        self._dir = project_dir
        self._sink = sink

    def _event(self, event_type: str, **data) -> None:
        self._sink.append((event_type, dict(data)))


# --------------------------------------------------------------------------- #
# the harness executor
# --------------------------------------------------------------------------- #
class LongRunningHarness:
    """Reliable execution infrastructure over the existing deterministic runtime.

    One instance is stateless (beyond the `emit` callback) — all state lives
    on disk under `harness_root`. A NEW instance can `resume()` what a killed
    instance left behind.
    """

    def __init__(self, harness_root: str,
                 emit: Optional[Callable[[str, dict], None]] = None,
                 agent_executor=None,
                 max_concurrency: int = 1):
        self.root = harness_root
        self.emit = emit or (lambda event_type, data: None)
        # Phase 5.1: inject a SpecialistAgentExecutor or an LLMProvider for
        # agent-mode execution; None = deterministic reference mode only
        self.agent_executor = agent_executor
        # Phase 7: DAG-aware bounded parallel scheduler. 1 = sequential (Phase 6 compat).
        if not isinstance(max_concurrency, int) or max_concurrency < 1:
            raise ValueError("max_concurrency must be a positive int, got %r" % max_concurrency)
        self.max_concurrency = max_concurrency
        # Phase 7 §13: no task may ever have two concurrently-running workers.
        # The scheduler thread is the only writer of this set.
        self._running_task_ids: set = set()
        # Phase 7: project dir workers use for the MessageBus (set per run)
        self._worker_project_dir: str = ""

    # ------------------------------------------------------------------ #
    # project lifecycle
    # ------------------------------------------------------------------ #
    def create_project(self, name: str, case_id: Optional[str] = None,
                       workflow: Optional[dict] = None,
                       task_types: Optional[list] = None,
                       task_graph: Optional[dict] = None) -> Project:
        """Create a project + its task chain + an empty CaseState.

        `task_graph` (Phase 4): a validated TaskGraph from the Planner — tasks
        with explicit dependencies. When given, `task_types` is ignored.
        `task_types` (Phase 3): a simple ordered list (canonical chain fallback).
        """
        wf = workflow or orch.load_workflow()
        cid = case_id or _uid("case")
        project_id = _uid("proj")
        p = Project(project_id, name, cid, self.root)

        # initialize the CaseState on disk (reuses existing store)
        state = cs.new_case_state(cid, wf)
        tk.init_tasks(state, wf)
        state_store.save(state, self._case_root(p))

        p._event("project_created", name=name, case_id=cid)
        p._save()

        if task_graph:
            # Phase 4: create tasks from the validated graph, preserving the
            # graph's task_ids so dependencies resolve correctly
            for t in task_graph.get("tasks", []):
                graph_id = t.get("task_id") or _uid("task")
                task = p.create_task(t["task_type"],
                                     dependencies=t.get("dependencies") or [])
                # force the project task_id to match the graph's
                task["task_id"] = graph_id
                if t.get("description"):
                    task["description"] = t["description"][:200]
                # Multi-Agent: carry assigned_agent from the graph if present
                if t.get("assigned_agent"):
                    task["assigned_agent"] = t["assigned_agent"]
            # persist the graph task_ids (create_task saved with auto IDs)
            p._save()
        else:
            # Phase 3: code-defined linear chain
            for tt in (task_types or TASK_CHAIN):
                p.create_task(tt,
                              dependencies=[p.tasks[-1]["task_id"]] if p.tasks else [])

        self.emit("project_created", {"project_id": project_id, "name": name})
        return p

    def _case_root(self, project: Project) -> str:
        return os.path.join(self.root, project.project_id, "case")

    def _load_case_state(self, project: Project) -> Optional[dict]:
        state = state_store.load(self._case_root(project), project.case_id)
        if state is None:
            return None
        ok, reasons = cp.validate(state, project.case_id)
        if not ok:
            return None
        return state

    # ------------------------------------------------------------------ #
    # execution
    # ------------------------------------------------------------------ #
    def run(self, project: Project, force_rerun: bool = False,
            workflow: Optional[dict] = None,
            max_tasks: int = 50) -> dict:
        """Execute the task chain from the first unfinished task."""
        wf = workflow or orch.load_workflow()
        state = self._load_case_state(project)
        if state is None:
            return {"status": "FAILED", "reason": "no valid case state on disk"}

        project.status = "running"
        project._save()
        executed = []

        # Phase 7: DAG-aware bounded parallel path (max_concurrency > 1).
        # max_concurrency == 1 keeps the Phase 6 sequential path unchanged.
        if self.max_concurrency > 1:
            executed = []
            # §16 crash recovery: interrupted RUNNING -> PENDING, terminal
            # tasks are skipped and never re-executed (§14 idempotency)
            self._parallel_recovery_pass(project, executed)
            handoff_stats = {"checked": 0, "acked": 0, "failed": 0, "pending": 0,
                             "invalid": 0}
            max_scheduling_rounds = 5  # same bound as the sequential path
            for _round in range(max_scheduling_rounds):
                executed.extend(self._run_parallel(project, state, wf,
                                                   force_rerun=force_rerun))
                stats = self._consume_handoffs(project, state)
                for k in handoff_stats:
                    handoff_stats[k] += stats.get(k, 0)
                # handoff-activated PENDING tasks go through another parallel
                # pass (the scheduler — never the bus — still decides)
                activated = stats.get("pending", 0) > 0
                has_pending_tasks = any(t["status"] == "PENDING" for t in project.tasks)
                if not (activated and has_pending_tasks):
                    break
            project.status = "completed" if all(
                t["status"] in ("PASSED", "COMPLETED") for t in project.tasks
            ) else ("needs_review" if any(t["status"] == "NEEDS_REVIEW"
                                          for t in project.tasks) else "failed")
            project._save()
            return {"status": project.status, "executed": executed,
                    "handoffs": handoff_stats,
                    "project": project.to_public()}

        for task in project.tasks:
            tt = task["task_type"]
            # use the Planner Registry for the trusted mapping (falls back to
            # the legacy TASK_DEFS for Phase 3 compatibility)
            from runtime.planner import registry as _planner_reg
            reg_def = _planner_reg.get(tt)
            if reg_def:
                stage_id = reg_def["stage_id"]
            else:
                stage_id = TASK_DEFS.get(tt, ("", None))[0]

            # ---- Multi-Agent: deterministic assignment + validation (§5/§14) -- #
            from runtime.agents import agent_for_task, validate_assignment
            assigned = task.get("assigned_agent") or agent_for_task(tt) or ""
            if assigned:
                project._set_task(task["task_id"], assigned_agent=assigned)
                ok_assign, assign_err = validate_assignment(tt, assigned)
                if not ok_assign:
                    project._set_task(task["task_id"], status="BLOCKED",
                                      reason=assign_err)
                    project._event("agent_validation_failed",
                                   task_id=task["task_id"], task_type=tt,
                                   agent_id=assigned, reason=assign_err[:160])
                    self.emit("agent_validation_failed",
                              {"project_id": project.project_id,
                               "task_id": task["task_id"], "task_type": tt,
                               "agent_id": assigned, "reason": assign_err[:160]})
                    executed.append({"task": tt, "outcome": "AGENT_INVALID"})
                    continue
                project._event("agent_assigned", task_id=task["task_id"],
                               task_type=tt, agent_id=assigned)
                self.emit("agent_assigned", {"project_id": project.project_id,
                                             "task_id": task["task_id"],
                                             "task_type": tt, "agent_id": assigned})

            # ---- dependency check FIRST: a failed upstream task BLOCKS all
            #      downstream tasks regardless of stage status (§7) ------------ #
            missing = [d for d in task["dependencies"]
                       if self._dep_status(project, d) not in ("PASSED", "COMPLETED")]
            if missing:
                project._set_task(task["task_id"], status="BLOCKED",
                                  reason="unmet dependencies")
                project._event("task_failed", task_id=task["task_id"],
                               task_type=tt, reason="BLOCKED by %s" % missing)
                self.emit("task_failed", {"project_id": project.project_id,
                                          "task_id": task["task_id"],
                                          "task_type": tt, "reason": "BLOCKED"})
                executed.append({"task": tt, "outcome": "BLOCKED"})
                continue

            # ---- idempotency: skip already-PASSED tasks (§8) ---------------- #
            stage_status = (state.get("stages", {}).get(stage_id, {}) or {}).get("status")
            if stage_status == "COMPLETED" and not force_rerun:
                project._set_task(task["task_id"], status="COMPLETED",
                                  output_artifacts=self._stage_artifacts(state, stage_id))
                project._event("task_skipped", task_id=task["task_id"],
                               task_type=tt, reason="already_passed")
                self.emit("task_skipped", {"project_id": project.project_id,
                                           "task_id": task["task_id"], "task_type": tt})
                executed.append({"task": tt, "outcome": "SKIPPED"})
                continue

            # ---- skip duplicate stages (knowledge_search + product_candidates
            #       both map to product-candidate-provider) ------------------- #
            if stage_id in _UNIQUE_STAGES and self._stage_done(state, stage_id) \
                    and not force_rerun:
                project._set_task(task["task_id"], status="COMPLETED")
                project._event("task_skipped", task_id=task["task_id"],
                               task_type=tt, reason="stage already executed")
                executed.append({"task": tt, "outcome": "SKIPPED"})
                continue

            # ---- execute via the EXISTING orchestrator stage runner ---------- #
            stage = transitions.stage_by_id(wf, stage_id)
            if stage is None:
                project._set_task(task["task_id"], status="FAILED",
                                  reason="unknown stage %s" % stage_id)
                executed.append({"task": tt, "outcome": "FAILED"})
                continue

            project._set_task(task["task_id"], status="RUNNING",
                              attempt=task["attempt"] + 1)
            project._event("task_started", task_id=task["task_id"], task_type=tt,
                           attempt=task["attempt"] + 1,
                           agent_id=assigned or None)
            self.emit("task_started", {"project_id": project.project_id,
                                       "task_id": task["task_id"], "task_type": tt,
                                       "agent_id": assigned or None})
            if assigned:
                project._event("agent_started", task_id=task["task_id"],
                               task_type=tt, agent_id=assigned,
                               attempt=task["attempt"] + 1)
                self.emit("agent_started", {"project_id": project.project_id,
                                            "task_id": task["task_id"],
                                            "task_type": tt, "agent_id": assigned})

            state["current_stage"] = stage_id

            # ---- Phase 5.1/5.2: Specialist Agent Executor when configured ------ #
            if assigned and self.agent_executor is not None:
                from runtime.agents.executor import SpecialistAgentExecutor
                executor = (self.agent_executor if isinstance(
                    self.agent_executor, SpecialistAgentExecutor)
                    else SpecialistAgentExecutor(self.agent_executor))
                state["_workflow"] = wf  # executor needs stage defs

                # Phase 6.2.2: dual-write emit — SSE callback AND durable
                # project.events.jsonl (no second event store, just a bridge)
                def _agent_emit(event_type, data, _p=project, _cb=self.emit):
                    _cb(event_type, data)
                    safe = {k: v for k, v in (data or {}).items()
                            if isinstance(v, (str, int, float, bool)) or v is None}
                    _p._event(event_type, **safe)

                result = executor.execute(
                    agent_id=assigned, task=task, project=project,
                    case_state=state, emit=_agent_emit)
                state.pop("_workflow", None)

                # Phase 5.2: Harness owns the Eval boundary.
                # Agent produced artifact → Harness runs eval + repair here.
                if result.outcome == "ARTIFACT_READY":
                    result = self._run_eval_and_repair(
                        state, wf, stage_id, task, project, assigned, executor)
            else:
                # Reference / Deterministic mode (Phase 3)
                # _execute_stage already owns eval + repair internally
                result = orch._execute_stage(state, wf, stage)  # noqa: SLF001

            outcome = result.get("outcome")
            if outcome == "GATE":
                orch.approve(state, stage_id)
                outcome = "OK"

            if outcome == "OK":
                arts = self._stage_artifacts(state, stage_id)
                project._set_task(task["task_id"], status="PASSED",
                                  output_artifacts=arts)
                project._event("task_completed", task_id=task["task_id"],
                               task_type=tt, artifacts=arts,
                               eval_id=(result.get("eval") or {}).get("eval_id"),
                               agent_id=assigned or None)
                self.emit("task_completed", {"project_id": project.project_id,
                                             "task_id": task["task_id"],
                                             "task_type": tt, "artifacts": arts})
                if assigned:
                    project._event("agent_completed", task_id=task["task_id"],
                                   task_type=tt, agent_id=assigned,
                                   artifacts=arts)
                    self.emit("agent_completed",
                              {"project_id": project.project_id,
                               "task_id": task["task_id"], "task_type": tt,
                               "agent_id": assigned, "artifacts": arts})
                executed.append({"task": tt, "outcome": "PASS", "agent": assigned})
            else:
                project._set_task(task["task_id"], status="NEEDS_REVIEW",
                                  reason=str(result.get("reasons", ""))[:200])
                project._event("task_failed", task_id=task["task_id"],
                               task_type=tt, agent_id=assigned or None,
                               reason=str(result.get("reasons", ""))[:200])
                if assigned:
                    project._event("agent_failed", task_id=task["task_id"],
                                   task_type=tt, agent_id=assigned,
                                   reason=str(result.get("reasons", ""))[:160])
                    self.emit("agent_failed",
                              {"project_id": project.project_id,
                               "task_id": task["task_id"], "task_type": tt,
                               "agent_id": assigned,
                               "reason": str(result.get("reasons", ""))[:160]})
                executed.append({"task": tt, "outcome": "NEEDS_REVIEW",
                                 "agent": assigned})
                # do NOT break: continue so downstream tasks get BLOCKED by
                # the dependency check (their dep is now NEEDS_REVIEW)

            # ---- checkpoint after each PASS (§11) ---------------------------- #
            self._checkpoint(project, state, task["task_id"])

        # ---- Phase 6.2: message-driven scheduling loop ---------------------- #
        # After the sequential pass, consume handoffs. If any handoff activates
        # a still-PENDING task whose dependencies are now met, loop back and
        # run another sequential pass. Bounded to prevent infinite loops.
        handoff_stats = {"checked": 0, "acked": 0, "failed": 0, "pending": 0,
                         "invalid": 0}
        max_scheduling_rounds = 5  # safety bound for message-driven re-runs
        for round_num in range(max_scheduling_rounds):
            stats = self._consume_handoffs(project, state)
            for k in handoff_stats:
                handoff_stats[k] += stats.get(k, 0)

            # if any task_activated events fired and there are still PENDING
            # tasks, loop back for another sequential execution pass
            activated = stats.get("pending", 0) > 0
            has_pending_tasks = any(t["status"] == "PENDING" for t in project.tasks)
            if not (activated and has_pending_tasks):
                break

            # run another sequential pass for newly-eligible tasks
            for task in project.tasks:
                if task["status"] != "PENDING":
                    continue
                tt = task["task_type"]
                from runtime.planner import registry as _pr
                rd = _pr.get(tt)
                stage_id = rd["stage_id"] if rd else TASK_DEFS.get(tt, ("", None))[0]
                missing = [d for d in task["dependencies"]
                           if self._dep_status(project, d) not in ("PASSED", "COMPLETED")]
                if missing:
                    continue  # dependency not met yet — skip
                # Re-execute this task (simplified path for activated tasks)
                result2 = self._execute_single_task(
                    project, state, wf, task, stage_id)
                executed.extend(result2)

        project.status = "completed" if all(
            t["status"] in ("PASSED", "COMPLETED") for t in project.tasks
        ) else ("needs_review" if any(t["status"] == "NEEDS_REVIEW"
                                      for t in project.tasks) else "failed")
        project._save()
        return {"status": project.status, "executed": executed,
                "handoffs": handoff_stats,
                "project": project.to_public()}

    def _execute_single_task(self, project, state, wf, task, stage_id):
        """Execute one task in the message-driven scheduling loop.
        Returns a list of executed outcome dicts."""
        from runtime.planner import registry as _pr
        from runtime.agents import agent_for_task
        tt = task["task_type"]
        assigned = task.get("assigned_agent") or agent_for_task(tt) or ""

        # Check stage completion (idempotency)
        stage_status = (state.get("stages", {}).get(stage_id, {}) or {}).get("status")
        if stage_status == "COMPLETED":
            project._set_task(task["task_id"], status="COMPLETED")
            return [{"task": tt, "outcome": "SKIPPED", "agent": assigned}]

        stage = transitions.stage_by_id(wf, stage_id)
        if stage is None:
            project._set_task(task["task_id"], status="FAILED",
                              reason="unknown stage %s" % stage_id)
            return [{"task": tt, "outcome": "FAILED", "agent": assigned}]

        project._set_task(task["task_id"], status="RUNNING",
                          attempt=task["attempt"] + 1)
        project._event("task_started", task_id=task["task_id"], task_type=tt,
                       agent_id=assigned or None)

        state["current_stage"] = stage_id

        if assigned and self.agent_executor is not None:
            from runtime.agents.executor import SpecialistAgentExecutor
            executor = (self.agent_executor if isinstance(
                self.agent_executor, SpecialistAgentExecutor)
                else SpecialistAgentExecutor(self.agent_executor))
            state["_workflow"] = wf
            result = executor.execute(
                agent_id=assigned, task=task, project=project,
                case_state=state, emit=self.emit)
            state.pop("_workflow", None)
            if result.outcome == "ARTIFACT_READY":
                result = self._run_eval_and_repair(
                    state, wf, stage_id, task, project, assigned, executor)
        else:
            result = orch._execute_stage(state, wf, stage)

        outcome = result.get("outcome")
        if outcome == "GATE":
            orch.approve(state, stage_id)
            outcome = "OK"

        if outcome == "OK":
            arts = self._stage_artifacts(state, stage_id)
            project._set_task(task["task_id"], status="PASSED",
                              output_artifacts=arts)
            project._event("task_completed", task_id=task["task_id"],
                           task_type=tt, artifacts=arts,
                           agent_id=assigned or None)
            self._checkpoint(project, state, task["task_id"])
            return [{"task": tt, "outcome": "PASS", "agent": assigned}]
        else:
            project._set_task(task["task_id"], status="NEEDS_REVIEW",
                              reason=str(result.get("reasons", ""))[:200])
            project._event("task_failed", task_id=task["task_id"],
                           task_type=tt, agent_id=assigned or None,
                           reason=str(result.get("reasons", ""))[:200])
            return [{"task": tt, "outcome": "NEEDS_REVIEW", "agent": assigned}]

    # ------------------------------------------------------------------ #
    # Phase 7: DAG-aware bounded parallel scheduler
    # ------------------------------------------------------------------ #
    def _stage_id_for(self, task_type: str) -> str:
        """task_type → workflow stage id (Planner Registry, legacy fallback)."""
        from runtime.planner import registry as _pr
        pdef = _pr.get(task_type)
        if pdef:
            return pdef["stage_id"]
        return TASK_DEFS.get(task_type, ("", None))[0]

    def _produced_types_for(self, task_type: str) -> list:
        """task_type → artifact types the Planner Registry declares it produces."""
        from runtime.planner import registry as _pr
        pdef = _pr.get(task_type)
        if pdef:
            return list(pdef.get("produced_artifacts") or [])
        art = TASK_DEFS.get(task_type, ("", None))[1]
        return [art] if art else []

    def _resolve_agent_executor(self):
        """The executor workers and repairs share: a SpecialistAgentExecutor
        (or custom execute()-shaped test executor) as-is, an LLM provider
        wrapped in SpecialistAgentExecutor."""
        from runtime.agents.executor import SpecialistAgentExecutor
        ae = self.agent_executor
        if hasattr(ae, "execute") and not hasattr(ae, "generate"):
            return ae  # SpecialistAgentExecutor or a custom test executor
        return SpecialistAgentExecutor(ae)

    def _compute_runnable(self, project: Project) -> list:
        """Phase 7 §4: PENDING tasks whose dependencies are all PASSED/COMPLETED,
        excluding anything already running. Stable graph order (§19)."""
        order = {t["task_id"]: i for i, t in enumerate(project.tasks)}
        runnable = []
        for task in project.tasks:
            if task["status"] != "PENDING":
                continue
            if task["task_id"] in self._running_task_ids:
                continue
            deps_ok = all(self._dep_status(project, d) in ("PASSED", "COMPLETED")
                          for d in task.get("dependencies", []))
            if deps_ok:
                runnable.append(task["task_id"])
        return sorted(runnable, key=order.__getitem__)

    def _parallel_recovery_pass(self, project: Project, executed: list) -> None:
        """§16 crash recovery. Recorded policy: a task left RUNNING by an
        interrupted process is recovered to PENDING (never assumed PASS) and
        re-executed; already-terminal tasks are skipped, not re-executed (§14)."""
        self._running_task_ids = set()
        for task in project.tasks:
            if task["status"] == "RUNNING":
                project._set_task(task["task_id"], status="PENDING",
                                  reason="recovered: RUNNING at interruption -> PENDING")
                project._event("task_recovered", task_id=task["task_id"],
                               task_type=task["task_type"],
                               from_status="RUNNING", to_status="PENDING")
                self.emit("task_recovered", {
                    "project_id": project.project_id,
                    "task_id": task["task_id"], "task_type": task["task_type"],
                    "from_status": "RUNNING", "to_status": "PENDING"})
            elif task["status"] in ("PASSED", "COMPLETED"):
                executed.append({"task": task["task_type"], "outcome": "SKIPPED",
                                 "agent": task.get("assigned_agent") or ""})

    def _terminalize_ready(self, project: Project, state: dict,
                           executed: list, force_rerun: bool) -> None:
        """Idempotency (§14): PENDING tasks whose workflow stage is already
        COMPLETED on disk (e.g. checkpoint recovery) become COMPLETED/SKIPPED
        without invoking an agent. Unknown task types fail fast.

        force_rerun deliberately covers ONLY the stage-done skip: already
        PASSED/COMPLETED tasks are never re-executed in parallel mode —
        idempotency (§14) outranks force_rerun here (known, documented
        asymmetry vs the sequential path)."""
        for task in project.tasks:
            if task["status"] != "PENDING":
                continue
            tid, tt = task["task_id"], task["task_type"]
            stage_id = self._stage_id_for(tt)
            if not stage_id:
                project._set_task(tid, status="FAILED",
                                  reason="unknown task_type %s" % tt)
                project._event("task_failed", task_id=tid, task_type=tt,
                               reason="unknown task_type %s" % tt)
                self._checkpoint(project, state, tid)
                executed.append({"task": tt, "outcome": "FAILED"})
                continue
            if force_rerun:
                continue
            stage_status = (state.get("stages", {}).get(stage_id, {}) or {}).get("status")
            done = stage_status == "COMPLETED" or (
                stage_id in _UNIQUE_STAGES and self._stage_done(state, stage_id))
            if done:
                project._set_task(tid, status="COMPLETED",
                                  output_artifacts=self._stage_artifacts(state, stage_id))
                project._event("task_skipped", task_id=tid, task_type=tt,
                               reason="already_passed")
                self.emit("task_skipped", {"project_id": project.project_id,
                                           "task_id": tid, "task_type": tt})
                self._checkpoint(project, state, tid)
                executed.append({"task": tt, "outcome": "SKIPPED"})

    def _block_downstream(self, project: Project, state: dict,
                          executed: list) -> int:
        """§12 failure propagation: a PENDING task whose dependency is
        FAILED/NEEDS_REVIEW/BLOCKED becomes terminally BLOCKED."""
        blocked = 0
        for task in project.tasks:
            if task["status"] != "PENDING":
                continue
            bad = [d for d in task.get("dependencies", [])
                   if self._dep_status(project, d) in ("FAILED", "NEEDS_REVIEW", "BLOCKED")]
            if not bad:
                continue
            tid, tt = task["task_id"], task["task_type"]
            project._set_task(tid, status="BLOCKED", reason="unmet dependencies")
            project._event("task_failed", task_id=tid, task_type=tt,
                           reason="BLOCKED by %s" % bad)
            self.emit("task_failed", {"project_id": project.project_id,
                                      "task_id": tid, "task_type": tt,
                                      "reason": "BLOCKED"})
            self._checkpoint(project, state, tid)
            executed.append({"task": tt, "outcome": "BLOCKED"})
            blocked += 1
        return blocked

    def _run_parallel(self, project: Project, state: dict, wf: dict,
                      force_rerun: bool = False) -> list:
        """Phase 7 §22: DAG-aware bounded parallel execution loop.

        Round-based scheduler (worker pool = ThreadPoolExecutor):
          1. terminalize stage-done tasks (idempotency) and BLOCKED tasks
          2. compute the runnable set (graph order), fill up to
             max_concurrency slots, mark RUNNING (never two workers per task)
          3. agent tasks execute on isolated CaseState copies in workers;
             reference tasks execute in the scheduler thread on the main
             state (the same code path as Phase 6 — safe because the
             scheduler thread is the only main-state writer)
          4. barrier: wait for the round, then COMMIT IN GRAPH ORDER —
             merge artifacts, replay worker events, run Harness-owned
             Eval + Repair, set the terminal status, checkpoint

        Determinism (§19): thread completion order never decides commits —
        artifact ids, eval ids and events follow graph order.
        """
        import copy as _copy
        from concurrent.futures import ThreadPoolExecutor
        from runtime.agents import agent_for_task, validate_assignment

        executed = []
        max_rounds = 200  # safety bound
        # workers read this (MessageBus location); only the scheduler writes it
        self._worker_project_dir = project._dir
        pool = ThreadPoolExecutor(max_workers=self.max_concurrency)
        try:
            for _round in range(max_rounds):
                self._terminalize_ready(project, state, executed, force_rerun)
                runnable = self._compute_runnable(project)
                if not runnable:
                    if self._block_downstream(project, state, executed):
                        continue  # a fresh BLOCKED state may cascade further
                    break
                batch = runnable[:self.max_concurrency]

                # ---- schedule + start the round -------------------------------- #
                workers = {}     # tid -> future (agent mode)
                ref_tasks = []   # (tid, stage_id) reference mode
                for slot, tid in enumerate(batch):
                    task = project.get_task(tid)
                    tt = task["task_type"]
                    stage_id = self._stage_id_for(tt)
                    assigned = task.get("assigned_agent") or agent_for_task(tt) or ""
                    if assigned:
                        project._set_task(tid, assigned_agent=assigned)
                        ok_assign, assign_err = validate_assignment(tt, assigned)
                        if not ok_assign:
                            project._set_task(tid, status="BLOCKED",
                                              reason=assign_err)
                            project._event("agent_validation_failed",
                                           task_id=tid, task_type=tt,
                                           agent_id=assigned, reason=assign_err[:160])
                            self.emit("agent_validation_failed",
                                      {"project_id": project.project_id,
                                       "task_id": tid, "task_type": tt,
                                       "agent_id": assigned, "reason": assign_err[:160]})
                            self._checkpoint(project, state, tid)
                            executed.append({"task": tt, "outcome": "AGENT_INVALID"})
                            continue
                        project._event("agent_assigned", task_id=tid, task_type=tt,
                                       agent_id=assigned)
                        self.emit("agent_assigned", {"project_id": project.project_id,
                                                     "task_id": tid, "task_type": tt,
                                                     "agent_id": assigned})
                    attempt = task["attempt"] + 1
                    project._set_task(tid, status="RUNNING", attempt=attempt)
                    self._running_task_ids.add(tid)  # §13 no duplicate execution
                    worker_id = "w%d" % slot
                    project._event("task_scheduled", task_id=tid, task_type=tt,
                                   worker_id=worker_id)
                    project._event("task_started", task_id=tid, task_type=tt,
                                   attempt=attempt, agent_id=assigned or None,
                                   worker_id=worker_id)
                    self.emit("task_started", {"project_id": project.project_id,
                                               "task_id": tid, "task_type": tt,
                                               "agent_id": assigned or None,
                                               "worker_id": worker_id})
                    if assigned:
                        project._event("agent_started", task_id=tid, task_type=tt,
                                       agent_id=assigned, attempt=attempt)
                        self.emit("agent_started", {"project_id": project.project_id,
                                                    "task_id": tid, "task_type": tt,
                                                    "agent_id": assigned})
                    if assigned and self.agent_executor is not None:
                        # snapshot BEFORE submit: workers never observe the
                        # main state while the scheduler mutates it (§7)
                        snapshot = _copy.deepcopy(state)
                        workers[tid] = pool.submit(self._execute_worker, wf, task,
                                                   assigned, worker_id, snapshot)
                    else:
                        ref_tasks.append((tid, stage_id))

                # ---- reference tasks run in the scheduler thread (main state),
                #      concurrently with the in-flight agent workers --------- #
                ref_results = {}
                for tid, stage_id in ref_tasks:
                    ref_results[tid] = self._execute_reference(state, wf, stage_id)

                # ---- round barrier, then graph-order commit (§19) ------------- #
                agent_results = {tid: fut.result() for tid, fut in workers.items()}
                for tid in batch:
                    if tid in ref_results:
                        executed.extend(
                            self._commit_reference(project, state,
                                                   ref_results[tid], tid))
                    elif tid in agent_results:
                        executed.extend(
                            self._commit_agent(project, state, wf,
                                               agent_results[tid]))
                    self._running_task_ids.discard(tid)
        finally:
            pool.shutdown(wait=True)
        return executed

    def _execute_worker(self, wf: dict, task: dict, assigned: str,
                        worker_id: str, snapshot: dict) -> "TaskExecutionResult":
        """Run ONE agent task on an isolated CaseState copy (§7/§8).

        The worker only executes; it never decides PASS, never touches the
        project / main state / checkpoints, and its emitted events are
        captured for the scheduler to replay in commit order.
        """
        t0 = time.time()
        captured: list = []
        worker_state = snapshot
        worker_state["_workflow"] = wf
        proxy = _WorkerProjectProxy(self._worker_project_dir, captured)

        def _worker_emit(event_type, data):
            captured.append((event_type, dict(data or {})))

        try:
            executor = self._resolve_agent_executor()
            result = executor.execute(agent_id=assigned, task=task,
                                      project=proxy, case_state=worker_state,
                                      emit=_worker_emit)
            produced = [t for t in self._produced_types_for(task["task_type"])
                        if t in (worker_state.get("artifacts") or {})]
            return TaskExecutionResult(
                task_id=task["task_id"], agent_id=assigned,
                status=result.outcome, artifacts=produced,
                execution_metadata={
                    "worker_id": worker_id,
                    "duration_ms": round((time.time() - t0) * 1000, 1)},
                error=getattr(result, "error_code", "") or "",
                worker_state=worker_state, events=captured)
        except Exception as e:  # noqa: BLE001 — a worker crash fails ONE task
            return TaskExecutionResult(
                task_id=task["task_id"], agent_id=assigned,
                status="AGENT_FAILED",
                execution_metadata={
                    "worker_id": worker_id,
                    "duration_ms": round((time.time() - t0) * 1000, 1)},
                error="WORKER_EXCEPTION: %r" % e,
                worker_state=worker_state, events=captured)
        finally:
            worker_state.pop("_workflow", None)

    def _execute_reference(self, state: dict, wf: dict, stage_id: str) -> dict:
        """Reference (deterministic-runtime) task, executed by the scheduler
        thread on the MAIN state — the exact Phase 6 execution path."""
        stage = transitions.stage_by_id(wf, stage_id)
        if stage is None:
            return {"outcome": "NEEDS_REVIEW",
                    "reasons": ["unknown stage %s" % stage_id]}
        state["current_stage"] = stage_id
        return orch._execute_stage(state, wf, stage)  # noqa: SLF001 — Phase 6 path

    def _commit_reference(self, project: Project, state: dict,
                          result: dict, tid: str) -> list:
        """Commit a reference-mode task result (scheduler thread only)."""
        task = project.get_task(tid)
        tt = task["task_type"]
        assigned = task.get("assigned_agent") or ""
        outcome = result.get("outcome")
        if outcome == "GATE":
            orch.approve(state, self._stage_id_for(tt))
            outcome = "OK"
        if outcome == "OK":
            arts = self._stage_artifacts(state, self._stage_id_for(tt))
            project._set_task(tid, status="PASSED", output_artifacts=arts)
            project._event("task_completed", task_id=tid, task_type=tt,
                           artifacts=arts, agent_id=assigned or None)
            self.emit("task_completed", {"project_id": project.project_id,
                                         "task_id": tid, "task_type": tt,
                                         "artifacts": arts})
            self._checkpoint(project, state, tid)
            return [{"task": tt, "outcome": "PASS", "agent": assigned}]
        reason = str(result.get("reasons", ""))[:200] or "execution failed"
        project._set_task(tid, status="NEEDS_REVIEW", reason=reason)
        project._event("task_failed", task_id=tid, task_type=tt,
                       agent_id=assigned or None, reason=reason)
        self.emit("task_failed", {"project_id": project.project_id,
                                  "task_id": tid, "task_type": tt,
                                  "reason": reason})
        self._checkpoint(project, state, tid)  # terminal → checkpoint (§15)
        return [{"task": tt, "outcome": "NEEDS_REVIEW", "agent": assigned}]

    def _commit_agent(self, project: Project, state: dict, wf: dict,
                      wres: "TaskExecutionResult") -> list:
        """Commit one agent-mode worker result in the scheduler thread:
        replay events → merge artifacts → Harness-owned Eval + Repair →
        terminal status → checkpoint. Only this thread writes shared state."""
        tid = wres.task_id
        task = project.get_task(tid)
        tt = task["task_type"]
        assigned = wres.agent_id
        stage_id = self._stage_id_for(tt)

        # 1. replay worker-captured events (dual-write, graph order)
        for etype, edata in wres.events:
            self.emit(etype, {"project_id": project.project_id, **edata})
            safe = {k: v for k, v in edata.items()
                    if isinstance(v, (str, int, float, bool)) or v is None}
            project._event(etype, **safe)

        # 2. merge the worker's artifacts into the main state
        merged = self._merge_worker_artifacts(state, wf, wres.worker_state)

        # 3. Harness-owned Eval + Repair — the ONLY PASS authority (§9).
        #    A worker result alone can NEVER yield PASS: only the eval branch
        #    can, so a misbehaving executor cannot self-pass.
        if wres.status == "ARTIFACT_READY" and merged:
            result = self._run_eval_and_repair(
                state, wf, stage_id, task, project, assigned,
                self._resolve_agent_executor())
            outcome = result.get("outcome")
            if outcome == "GATE":
                orch.approve(state, stage_id)
                outcome = "OK"
        else:
            result, outcome = wres, None

        if outcome == "OK":
            arts = self._produced_artifact_ids(state, tt)
            project._set_task(tid, status="PASSED", output_artifacts=arts)
            project._event("task_completed", task_id=tid, task_type=tt,
                           artifacts=arts, agent_id=assigned or None)
            self.emit("task_completed", {"project_id": project.project_id,
                                         "task_id": tid, "task_type": tt,
                                         "artifacts": arts})
            project._event("agent_completed", task_id=tid, task_type=tt,
                           agent_id=assigned, artifacts=arts)
            self.emit("agent_completed", {"project_id": project.project_id,
                                          "task_id": tid, "task_type": tt,
                                          "agent_id": assigned,
                                          "artifacts": arts})
            self._checkpoint(project, state, tid)
            return [{"task": tt, "outcome": "PASS", "agent": assigned}]

        reason = wres.error or "; ".join(str(r) for r in result.get("reasons") or [])
        reason = (reason or "agent execution failed")[:200]
        project._set_task(tid, status="NEEDS_REVIEW", reason=reason)
        project._event("task_failed", task_id=tid, task_type=tt,
                       agent_id=assigned or None, reason=reason)
        project._event("agent_failed", task_id=tid, task_type=tt,
                       agent_id=assigned, reason=reason[:160])
        self.emit("agent_failed", {"project_id": project.project_id,
                                   "task_id": tid, "task_type": tt,
                                   "agent_id": assigned, "reason": reason[:160]})
        self._checkpoint(project, state, tid)  # terminal → checkpoint (§15)
        return [{"task": tt, "outcome": "NEEDS_REVIEW", "agent": assigned}]

    def _merge_worker_artifacts(self, state: dict, wf: dict,
                                worker_state: dict) -> bool:
        """Scheduler-thread merge of a worker's produced artifacts into the
        main state (§7). Content is RE-REGISTERED through the canonical
        put_artifact + artifact_registry path so ids stay sequential and
        unique regardless of worker count. Returns False on a collision."""
        main_arts = state.setdefault("artifacts", {})
        for art_type, art in (worker_state.get("artifacts") or {}).items():
            if art_type in main_arts:
                # same type re-produced (e.g. repair recovery): only the exact
                # same content may merge; anything else is a P0 collision
                if transitions.fingerprint(main_arts[art_type]) != \
                        transitions.fingerprint(art):
                    cs.record_event(state, "MERGE_REJECTED", detail=(
                        "ARTIFACT_COLLISION: %s produced twice with different "
                        "content" % art_type))
                    return False
                continue
            wrec = (worker_state.get("artifact_registry") or {}).get(art_type) or {}
            producer = wrec.get("producer_stage")
            if not producer:
                for st in transitions.stage_defs(wf):
                    if st.get("produces") == art_type:
                        producer = st["id"]
                        break
            if not producer:  # service-provided artifacts (knowledge-evidence)
                producer = self._stage_id_for("knowledge_search")
            ok, reasons = cs.put_artifact(state, art_type, art, producer)
            if not ok:
                cs.record_event(state, "MERGE_REJECTED", detail="; ".join(reasons))
                return False
            stage_def = transitions.stage_by_id(wf, producer) or {
                "id": producer, "skill": wrec.get("producer_skill"),
                "consumes": []}
            arec = reg_mod.register(state, art_type, art, stage_def)
            tr.emit(state, "ARTIFACT_STORED", output_artifact=arec["artifact_id"],
                    detail="artifact_type=%s stage=%s (parallel merge)"
                           % (art_type, producer))
            # mirror stage/task completion when the worker completed the stage
            wstage = (worker_state.get("stages") or {}).get(producer, {})
            if wstage.get("status") == "COMPLETED" and \
                    state["stages"][producer].get("status") != "COMPLETED":
                tk.set_output(state, producer, arec["artifact_id"])
                tk.set_status(state, producer, "COMPLETED")
                state["stages"][producer]["completed_at"] = \
                    wstage.get("completed_at") or cs.now()
                cs.record_event(state, "STAGE_COMPLETED", stage=producer,
                                detail="parallel merge")
        return True

    def _produced_artifact_ids(self, state: dict, task_type: str) -> list:
        """Artifact ids a task_type produced (Planner Registry types)."""
        out = []
        for art_type in self._produced_types_for(task_type):
            arec = reg_mod.by_type(state, art_type)
            if arec:
                out.append(arec["artifact_id"])
        return out

    def resume(self, project_id: str, workflow: Optional[dict] = None,
               force_rerun: bool = False) -> dict:
        """Load from disk (a NEW process can call this) and continue."""
        project = load_project(self.root, project_id)
        if project is None:
            return {"status": "FAILED", "reason": "project not found: %s" % project_id}

        # emit a resume event (this is what makes restart observable)
        project._event("run_resumed", state_version=project.state_version)
        self.emit("run_resumed", {"project_id": project_id,
                                  "state_version": project.state_version})
        return self.run(project, force_rerun=force_rerun, workflow=workflow)

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _checkpoint(self, project: Project, state: dict, task_id: str) -> dict:
        entry = cp.save(state, self._case_root(project), None)
        rec = {
            "checkpoint_id": entry["checkpoint_id"],
            "project_id": project.project_id,
            "task_id": task_id,
            "state_version": project.state_version,
            "created_at": _now(),
            "artifact_refs": entry.get("artifacts", []),
            "completed_task_ids": [t["task_id"] for t in project.tasks
                                   if t["status"] in ("PASSED", "COMPLETED")],
            "pending_task_ids": [t["task_id"] for t in project.tasks
                                 if t["status"] == "PENDING"],
        }
        project._append_jsonl("checkpoints.jsonl", rec)
        project._event("checkpoint_created", checkpoint_id=entry["checkpoint_id"],
                       task_id=task_id)
        return rec

    def _dep_status(self, project: Project, dep_task_id: str) -> str:
        t = project.get_task(dep_task_id)
        return t["status"] if t else "UNKNOWN"

    def _stage_artifacts(self, state: dict, stage_id: str) -> list:
        from runtime import artifact_registry as reg
        st = state.get("stages", {}).get(stage_id, {}) or {}
        art_type = st.get("produces")
        if not art_type:
            return []
        arec = reg.by_type(state, art_type)
        return [arec["artifact_id"]] if arec else []

    def _consume_handoffs(self, project, state: dict) -> dict:
        """Phase 6.1: process TASK_HANDOFF messages after task execution."""
        try:
            from runtime.agents.handoff import consume_handoffs
            from runtime.agents.message_bus import MessageBus
            bus = MessageBus(project._dir)
            return consume_handoffs(bus, project, state,
                                    emit=lambda t, d: self.emit(t, {
                                        "project_id": project.project_id, **d}))
        except Exception as e:  # noqa: BLE001 — handoff failure never breaks the run
            return {"error": str(e)[:120]}

    def _stage_done(self, state: dict, stage_id: str) -> bool:
        st = state.get("stages", {}).get(stage_id, {}) or {}
        return st.get("status") == "COMPLETED"

    # ------------------------------------------------------------------ #
    # Phase 5.2: Harness-owned Eval + Repair for Agent Mode
    # ------------------------------------------------------------------ #
    def _run_eval_and_repair(self, state: dict, wf: dict, stage_id: str,
                             task: dict, project, assigned: str,
                             executor) -> "AgentExecAdapter":
        """Run eval on the agent-produced artifact; if FAIL, bounded repair.

        The Agent produced the artifact (skip_eval=True in the ToolContext).
        THIS method is the eval owner — the ONLY place PASS/FAIL is determined
        for agent-mode tasks. Repair re-runs the agent (≤2 attempts)."""
        from runtime import eval_engine as ev
        from runtime import repair as rep
        from runtime import trace as tr
        from runtime import tasks as tk
        from runtime.planner import registry as _pr

        stage = transitions.stage_by_id(wf, stage_id)
        # Phase 6.2.2: use the Planner Registry's produced_artifacts for the
        # artifact type — the workflow stage may produce a different artifact
        # (e.g. knowledge_search → knowledge-evidence, NOT product-candidates)
        _pdef = _pr.get(task.get("task_type", ""))
        _parts = (_pdef or {}).get("produced_artifacts") or []
        art_type = _parts[0] if _parts else (stage or {}).get("produces") or ""
        max_repairs = 2

        for attempt in range(1 + max_repairs):  # 1 initial + 2 repairs
            artifact = (state.get("artifacts") or {}).get(art_type)
            if artifact is None:
                return AgentExecAdapter("AGENT_FAILED", None,
                                        ["artifact %s not found" % art_type])

            # ---- Harness runs Eval (the ONLY eval for this task attempt) ---- #
            tr.emit(state, "EVAL_STARTED", skill=stage.get("skill") if stage else None,
                    detail="artifact=%s attempt=%d" % (art_type, attempt + 1))
            rec_eval = ev.evaluate(state, art_type, artifact, stage or {})
            tr.emit(state, "EVAL_COMPLETED",
                    skill=stage.get("skill") if stage else None,
                    eval_status=rec_eval["status"],
                    detail="artifact=%s eval=%s" % (art_type, rec_eval["eval_id"]))
            self.emit("eval_started" if rec_eval["status"] == "PASS" else "eval_failed",
                      {"task_id": task["task_id"], "stage": stage_id,
                       "eval_id": rec_eval["eval_id"],
                       "status": rec_eval["status"]})

            if rec_eval["status"] == "PASS":
                # PASS → task passed (eval determined by Harness, not Agent)
                return AgentExecAdapter("OK", rec_eval)

            # ---- FAIL → repair or exhaust ------------------------------------ #
            failed = ev.failed_checks(rec_eval)
            if attempt < max_repairs:
                action = rep.plan(failed, ev.load_rules())
                if action:
                    tr.emit(state, "REPAIR_STARTED",
                            skill=stage.get("skill") if stage else None,
                            attempt=attempt + 1,
                            detail="action=%s failed=%s"
                                   % (action, ",".join(f["check_id"] for f in failed)))
                    self.emit("repair_started",
                              {"task_id": task["task_id"], "stage": stage_id,
                               "attempt": attempt + 1, "action": action})
                    # re-run the agent to produce a repaired artifact
                    state["_workflow"] = wf
                    repair_result = executor.execute(
                        agent_id=assigned, task=task, project=project,
                        case_state=state, emit=self.emit)
                    state.pop("_workflow", None)
                    if repair_result.outcome == "ARTIFACT_READY":
                        tr.emit(state, "REPAIR_COMPLETED",
                                skill=stage.get("skill") if stage else None,
                                attempt=attempt + 1,
                                detail="agent re-produced artifact")
                        self.emit("repair_completed",
                                  {"task_id": task["task_id"], "stage": stage_id,
                                   "attempt": attempt + 1})
                        continue  # re-eval the repaired artifact
                    else:
                        return AgentExecAdapter("NEEDS_REVIEW", rec_eval,
                                                ["repair agent execution failed"])
                else:
                    # not repairable
                    tr.emit(state, "REPAIR_EXHAUSTED",
                            skill=stage.get("skill") if stage else None,
                            attempt=attempt + 1, detail="not repairable")
                    return AgentExecAdapter("NEEDS_REVIEW", rec_eval,
                                            ["eval FAIL, not repairable"])
            else:
                # repair budget exhausted
                tr.emit(state, "REPAIR_EXHAUSTED",
                        skill=stage.get("skill") if stage else None,
                        attempt=attempt + 1,
                        detail="budget exhausted after %d repairs" % max_repairs)
                self.emit("repair_exhausted",
                          {"task_id": task["task_id"], "stage": stage_id})
                return AgentExecAdapter("NEEDS_REVIEW", rec_eval,
                                        ["eval FAIL after %d repairs" % max_repairs])

        return AgentExecAdapter("NEEDS_REVIEW", None, ["unexpected loop exit"])


class AgentExecAdapter:
    """Wraps _execute_stage results to match AgentExecutionResult interface."""
    def __init__(self, outcome, eval_rec=None, reasons=None):
        self.outcome = outcome
        self.eval_rec = eval_rec
        self.reasons = reasons or []

    def get(self, key, default=None):
        return {'outcome': self.outcome, 'eval': self.eval_rec,
                'reasons': self.reasons}.get(key, default)
