"""Agent runtime integration on the 26A queue — Phase 26B.

TASK BOUNDARY: one queue task == one AGENT RUN (case execution).
The skill graph, per-stage repair, eval gates and checkpoints stay
INSIDE the existing orchestrator — the worker executes the
orchestrator, never business logic. Skills stay queue-agnostic.

    DistributedTask(queue) → AgentTaskWorker → orchestrator.run/
    resume → Skills/Knowledge/LLM (UNCHANGED) → artifacts/checkpoints
    → settle (idempotent, lease-guarded)

Crash/retry resume uses the EXISTING checkpoint machinery with
PHYSICAL ATTEMPT ISOLATION: attempt N reads the newest checkpoint
from attempt dirs N-1..1 (newest-first, forward-only), writes only to
its own dir — a stale attempt's late writes can never pollute a newer
attempt's lineage (26B §10).

HITL (26B §12): a run pausing at a human gate does NOT hold the
lease. The worker persists the paused state as a checkpoint, defers
the task (FAILED + retry_reason=WAITING_FOR_APPROVAL@stage — a 26A
state, no semantics change), and EXITS. An authorized approval
(queue.ops.approve_and_resume) writes an approval marker bound to
(project, run, task, stage) and requeues the task; the next worker
resumes from the checkpoint, verifies the marker, and continues.
At-least-once + idempotent completion + stale-lease rejection —
exactly-once is NOT claimed.
"""
from __future__ import annotations

import json
import os
from typing import Callable, Optional

from . import model
from .store import LeaseRejected, OutcomeUnknown, TaskQueueStore
from .worker import TaskWorker

WAITING_PREFIX = "WAITING_FOR_APPROVAL"
APPROVAL_FILE = "approval.json"


def defer_reason(stage: str) -> str:
    return "%s@%s" % (WAITING_PREFIX, stage)


def parse_defer_reason(reason: Optional[str]) -> Optional[str]:
    """The paused stage id, when the task is waiting for approval."""
    if reason and reason.startswith(WAITING_PREFIX + "@"):
        return reason.split("@", 1)[1]
    return None


class AgentTaskWorker(TaskWorker):
    """TaskWorker + the agent settle policy: a run that pauses at a
    human gate is DEFERRED (lease released) instead of completed."""

    def _execute(self, task: dict) -> dict:
        tid, lease = task["task_id"], task["lease_id"]
        executor = self.executor          # bound agent executor
        try:
            self.store.start(tid, lease)
        except Exception as e:  # noqa: BLE001 — DB loss pre-execution
            self._log("task.start_failed", level="ERROR",
                      status="OUTCOME_UNKNOWN_RECOVERY_REQUIRED",
                      task_id=tid, lease_id=lease, error=e)
            return {"outcome": "RECOVERY_REQUIRED", "task_id": tid,
                    "changed": False}
        self._log("task.claimed", status="RUNNING", task_id=tid,
                  lease_id=lease, attempt=task["attempt"],
                  task_type=task["task_type"])
        import threading
        import time
        lost_lease = threading.Event()
        hb_stop = threading.Event()

        def _hb():
            while not hb_stop.wait(self.heartbeat_every_s):
                try:
                    self.store.heartbeat(tid, lease, self.lease_seconds)
                except LeaseRejected:
                    lost_lease.set()
                    return
                except Exception:  # noqa: BLE001 — transient DB
                    pass
        hb = threading.Thread(target=_hb, daemon=True)
        hb.start()
        outcome = None
        try:
            # the executor returns either a final report (dict with
            # "status") or {"__defer__": stage} for a human gate
            result = self._with_trace_context(task)
            if isinstance(result, dict) and "__defer__" in result:
                stage = result["__defer__"]
                outcome = self.store.fail(
                    tid, lease, defer_reason(stage), retry=False)
                self._log("task.deferred", status="WAITING_FOR_"
                          "APPROVAL", task_id=tid, lease_id=lease,
                          attempt=task["attempt"], stage=stage)
            else:
                outcome = self.store.succeed(tid, lease, result)
        except LeaseRejected as e:
            self._log("task.settle", level="ERROR",
                      status="STALE_LEASE_REJECTED", task_id=tid,
                      lease_id=lease, error=e)
            outcome = {"outcome": "STALE_REJECTED", "task_id": tid,
                       "changed": False}
        except OutcomeUnknown as e:
            self._log("task.settle", level="ERROR",
                      status="OUTCOME_UNKNOWN_RECOVERY_REQUIRED",
                      task_id=tid, lease_id=lease, error=e)
            outcome = {"outcome": "RECOVERY_REQUIRED", "task_id": tid,
                       "changed": False}
        except Exception as e:  # noqa: BLE001 — agent failure
            try:
                outcome = self.store.fail(
                    tid, lease, "%s: %s" % (type(e).__name__,
                                            str(e)[:200]), retry=True)
            except LeaseRejected:
                outcome = {"outcome": "STALE_REJECTED",
                           "task_id": tid, "changed": False}
            except Exception as e2:  # noqa: BLE001 — settle DB loss
                outcome = {"outcome": "RECOVERY_REQUIRED",
                           "task_id": tid, "changed": False}
                self._log("task.settle", level="ERROR",
                          status="OUTCOME_UNKNOWN_RECOVERY_REQUIRED",
                          task_id=tid, lease_id=lease, error=e2)
            self._log("task.failed", level="ERROR", status="FAILED",
                      task_id=tid, lease_id=lease,
                      attempt=task["attempt"], error=e)
        finally:
            hb_stop.set()
            hb.join(timeout=2)
        self._log("task.settled", status=str(outcome.get("outcome")),
                  task_id=tid, lease_id=lease, attempt=task["attempt"])
        return outcome


def make_agent_executor(*, workflow: dict, case_id: str, seeds: dict,
                        run_root: str, provided_by: str = "upstream-"
                        "dialogue", kb_dir: Optional[str] = None,
                        max_gate_approvals: int = 3) -> Callable:
    """Build the executor an AgentTaskWorker runs. It drives the
    EXISTING orchestrator (seed → run → bounded approve loop) with
    attempt-isolated checkpoint roots and HITL deferral at the FIRST
    unapproved gate."""
    from runtime import checkpoint as cp
    from runtime import orchestrator as orch

    def attempt_dir(attempt: int) -> str:
        return os.path.join(run_root, "attempt-%d" % attempt)

    def load_resumable(attempt: int):
        """Newest-first scan over attempt dirs < attempt (forward-only
        lineage: a stale older attempt can only write to its OWN,
        already-superseded dir)."""
        for a in range(attempt - 1, 0, -1):
            state, reasons = cp.load(attempt_dir(a), case_id)
            if state is not None:
                return state, a
        return None, None

    def execute(task: dict) -> dict:
        attempt = task["attempt"]
        root = attempt_dir(attempt)
        os.makedirs(root, exist_ok=True)
        state, resumed_from = load_resumable(attempt)
        if state is None:
            state = orch.seed_case(workflow, case_id, seeds,
                                   provided_by=provided_by)
        # resume a paused (WAITING) run only with a VALID approval
        # marker bound to THIS task + stage (26B §19); a human gate is
        # NEVER auto-approved
        pending_stage = _paused_stage(state)
        if pending_stage is not None:
            marker = _read_approval(run_root, resumed_from)
            if not _marker_valid(marker, task, pending_stage):
                cp.save(state, root, pending_stage)
                return {"__defer__": pending_stage,
                        "resumed_from_attempt": resumed_from}
            orch.approve(state, pending_stage)
        rep = orch.run(state, workflow, gate_policy="stop",
                       kb_dir=kb_dir, checkpoint_root=root)
        if rep["status"] == "PAUSED_NEEDS_REVIEW":
            pending = rep.get("stopped_at")
            cp.save(state, root, pending)
            return {"__defer__": pending,
                    "resumed_from_attempt": resumed_from}
        return {
            "kind": "agent-run",
            "case_id": case_id,
            "status": rep["status"],
            "reasons": [str(r)[:200] for r in (rep.get("reasons")
                                               or [])][:5],
            "executed": [e.get("stage") for e in
                         rep.get("executed", [])],
            "attempt": attempt,
            "resumed_from_attempt": resumed_from,
            "checkpoints": len(state.get("checkpoints") or []),
        }

    return execute


def _paused_stage(state: Optional[dict]) -> Optional[str]:
    """The stage awaiting review in a resumed state, if any."""
    if not state:
        return None
    for stage_id, stage in (state.get("stages") or {}).items():
        if stage.get("status") == "NEEDS_REVIEW":
            return stage_id
    return None


def _read_approval(run_root: str, attempt: Optional[int]) -> Optional[dict]:
    if attempt is None:
        attempt = 0
    for a in range(attempt, 0, -1):
        p = os.path.join(run_root, "attempt-%d" % a, APPROVAL_FILE)
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                return None
    return None


def _marker_valid(marker: Optional[dict], task: dict,
                  stage: str) -> bool:
    """Approval binding (26B §19): the marker must name THIS task,
    THIS run and THIS stage — an approval for task A can never resume
    task B."""
    if not isinstance(marker, dict):
        return False
    return (marker.get("task_id") == task["task_id"]
            and marker.get("run_id") == (task.get("run_id") or None)
            and marker.get("stage") == stage
            and marker.get("decision") == "APPROVED")
