"""Task ledger (Step 3).

One Task per stage. The Task is the *execution* record: how many attempts were spent, what
was repaired, which evals were produced, and why it failed.

Mirror discipline
-----------------
`stages[stage_id].status` (Phase 7) and `tasks[].status` (Step 3) must never diverge, because
`state.transitions` reads the former while operators/UI read the latter. Therefore there is
exactly ONE write path: `set_status()`. It writes both, and `check_mirror()` exists so a test
can prove they agree. Never set either field directly.
"""
from __future__ import annotations

from typing import Optional

from .state import case_state as cs  # noqa: E402
from . import trace as tr  # noqa: E402

# stage status (Phase 7 vocabulary) -> task status (Step 3 vocabulary)
STATUS_FROM_STAGE = {
    "PENDING": "PENDING",
    "RUNNING": "RUNNING",
    "COMPLETED": "PASS",
    "FAILED": "FAIL",
    "NEEDS_REVIEW": "NEEDS_REVIEW",
    "SKIPPED": "SKIPPED",
}


def init_tasks(state: dict, workflow: dict) -> list:
    """Create one Task per stage and point each stage at it."""
    state.setdefault("tasks", [])
    for i, st in enumerate(workflow.get("stages", []), start=1):
        task_id = "TASK-%03d" % i
        rec = {
            "task_id": task_id,
            "stage_id": st["id"],
            "skill": st.get("skill"),
            "status": "PENDING",
            "input_artifacts": [],
            "output_artifact": None,
            "attempt": 0,
            "max_attempts": int(st.get("max_attempts", 3)),
            "repairs": [],
            "failure_reason": None,
            "eval_ids": [],
            "created_at": cs.now(),
            "updated_at": cs.now(),
        }
        state["tasks"].append(rec)
        if st["id"] in state.get("stages", {}):
            state["stages"][st["id"]]["task_id"] = task_id
            state["stages"][st["id"]]["max_attempts"] = rec["max_attempts"]
        tr.emit(state, "TASK_CREATED", task_id=task_id, skill=st.get("skill"),
                detail="stage=%s" % st["id"])
    return state["tasks"]


def by_stage(state: dict, stage_id: str) -> Optional[dict]:
    for t in state.get("tasks", []):
        if t["stage_id"] == stage_id:
            return t
    return None


def by_id(state: dict, task_id: str) -> Optional[dict]:
    for t in state.get("tasks", []):
        if t["task_id"] == task_id:
            return t
    return None


def set_status(state: dict, stage_id: str, stage_status: str,
               failure_reason: Optional[str] = None) -> dict:
    """Single write path: update stage status AND its mirrored task status."""
    task_status = STATUS_FROM_STAGE[stage_status]
    rec = state["stages"][stage_id]
    rec["status"] = stage_status
    if stage_status == "RUNNING":
        rec["started_at"] = cs.now()
    if stage_status in ("COMPLETED", "FAILED", "NEEDS_REVIEW", "SKIPPED"):
        rec["completed_at"] = cs.now()
    if failure_reason is not None:
        rec["failure_reason"] = failure_reason

    t = by_stage(state, stage_id)
    if t is None:  # pragma: no cover - init_tasks always runs first
        raise KeyError("no task for stage %s" % stage_id)
    t["status"] = task_status
    t["updated_at"] = cs.now()
    if failure_reason is not None:
        t["failure_reason"] = failure_reason
    state["updated_at"] = cs.now()
    return t


def set_task_status(state: dict, stage_id: str, task_status: str) -> dict:
    """Set ONLY the task status (used for REPAIRING, which has no stage-status counterpart).

    The stage stays RUNNING while its task is REPAIRING; `check_mirror()` tolerates exactly
    this pair so the ledger stays consistent without inventing a stage status.
    """
    t = by_stage(state, stage_id)
    t["status"] = task_status
    t["updated_at"] = cs.now()
    state["updated_at"] = cs.now()
    return t


def begin_attempt(state: dict, stage_id: str) -> int:
    """Increment the attempt counter. Returns the new attempt number."""
    state["stages"][stage_id]["attempts"] += 1
    t = by_stage(state, stage_id)
    t["attempt"] = state["stages"][stage_id]["attempts"]
    t["updated_at"] = cs.now()
    return t["attempt"]


def remaining_attempts(state: dict, stage_id: str) -> int:
    t = by_stage(state, stage_id)
    return max(0, t["max_attempts"] - t["attempt"])


def record_repair(state: dict, stage_id: str, failed_checks: list,
                  repair_action: str, detail: Optional[str] = None) -> dict:
    entry = {
        "attempt": state["stages"][stage_id]["attempts"],
        "failed_checks": list(failed_checks),
        "repair_action": repair_action,
        "detail": detail,
        "at": cs.now(),
    }
    state["stages"][stage_id].setdefault("repairs", []).append(entry)
    t = by_stage(state, stage_id)
    t["repairs"].append(entry)
    t["updated_at"] = cs.now()
    cs.record_event(state, "REPAIR_APPLIED", stage=stage_id,
                    detail="%s: %s" % (repair_action, detail or ""))
    return entry


def set_input_artifacts(state: dict, stage_id: str, artifact_ids: list) -> None:
    t = by_stage(state, stage_id)
    t["input_artifacts"] = list(artifact_ids)
    t["updated_at"] = cs.now()


def set_output(state: dict, stage_id: str, artifact_id: Optional[str]) -> None:
    t = by_stage(state, stage_id)
    t["output_artifact"] = artifact_id
    t["updated_at"] = cs.now()


def attach_eval(state: dict, stage_id: str, eval_id: str) -> None:
    t = by_stage(state, stage_id)
    if eval_id not in t["eval_ids"]:
        t["eval_ids"].append(eval_id)
    st = state["stages"][stage_id]
    if eval_id not in st.setdefault("eval_ids", []):
        st["eval_ids"].append(eval_id)
    t["updated_at"] = cs.now()


def check_mirror(state: dict) -> tuple:
    """Invariant helper: stage.status and task.status must agree. Returns (ok, problems)."""
    problems = []
    for t in state.get("tasks", []):
        st = state.get("stages", {}).get(t["stage_id"])
        if st is None:
            problems.append("%s: unknown stage" % t["task_id"])
            continue
        expected = STATUS_FROM_STAGE[st["status"]]
        if t["status"] != expected:
            # REPAIRING is a legitimate transient: the stage is still RUNNING underneath.
            if not (t["status"] == "REPAIRING" and st["status"] == "RUNNING"):
                problems.append("%s: stage=%s task=%s (expected %s)"
                                % (t["task_id"], st["status"], t["status"], expected))
        if st.get("attempts") != t.get("attempt"):
            problems.append("%s: attempts stage=%s task=%s"
                            % (t["task_id"], st.get("attempts"), t.get("attempt")))
    return (len(problems) == 0), problems


def completed_task_ids(state: dict) -> list:
    return [t["task_id"] for t in state.get("tasks", []) if t["status"] == "PASS"]
