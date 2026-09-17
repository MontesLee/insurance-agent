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
                 agent_executor=None):
        self.root = harness_root
        self.emit = emit or (lambda event_type, data: None)
        # Phase 5.1: inject a SpecialistAgentExecutor or an LLMProvider for
        # agent-mode execution; None = deterministic reference mode only
        self.agent_executor = agent_executor

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
