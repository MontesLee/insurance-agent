"""Checkpoint / Resume (Step 3).

A checkpoint is only useful if it can be *trusted*. `load()` therefore validates before it
hands a state back:

  1. the file exists and parses;
  2. `case_id` matches the requested case;
  3. the state validates against runtime/state/case_state.schema.json;
  4. every registered artifact is present and still matches its fingerprint (registry.verify);
  5. every task points at a stage that exists.

Anything wrong -> CHECKPOINT_INVALID with reasons. Never a silent resume from a corrupt state.
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .state import case_state as cs  # noqa: E402
from .state import store  # noqa: E402
from . import artifact_registry as reg  # noqa: E402
from . import tasks as tk  # noqa: E402
from . import trace as tr  # noqa: E402


def next_id(state: dict) -> str:
    return "CP-%03d" % (len(state.get("checkpoints", [])) + 1)


def save(state: dict, root: str, stage_id: Optional[str] = None) -> dict:
    """Persist the case and record a checkpoint entry."""
    entry = {
        "checkpoint_id": next_id(state),
        "stage_id": stage_id,
        "case_status": state.get("status"),
        "completed_tasks": tk.completed_task_ids(state),
        "artifacts": reg.ids(state),
        "evals": [e["eval_id"] for e in state.get("evaluations", [])],
        "at": cs.now(),
        "valid": True,
    }
    state.setdefault("checkpoints", []).append(entry)
    store.save(state, root)
    cs.record_event(state, "CHECKPOINT_SAVED", stage=stage_id,
                    detail="%s tasks=%d artifacts=%d" % (entry["checkpoint_id"],
                                                         len(entry["completed_tasks"]),
                                                         len(entry["artifacts"])))
    tr.emit(state, "CHECKPOINT_SAVED", task_id=None, skill=None,
            output_artifact=None, detail="%s%s tasks=%d artifacts=%d"
            % (entry["checkpoint_id"], " stage=%s" % stage_id if stage_id else "",
               len(entry["completed_tasks"]), len(entry["artifacts"])))
    # rewrite so the checkpoint entry itself is durable
    store.save(state, root)
    return entry


def validate(state: dict, case_id: str) -> tuple:
    """Full checkpoint validation. Returns (ok, reasons)."""
    reasons = []
    if not isinstance(state, dict):
        return False, ["CHECKPOINT_INVALID: state is not an object"]
    if state.get("case_id") != case_id:
        reasons.append("CHECKPOINT_INVALID: case_id mismatch (%s != %s)"
                       % (state.get("case_id"), case_id))

    ok_schema, schema_errs = cs.validate(state)
    if not ok_schema:
        reasons.extend("CHECKPOINT_INVALID: schema: %s" % e for e in schema_errs[:5])

    ok_reg, reg_errs = reg.verify(state)
    if not ok_reg:
        reasons.extend("CHECKPOINT_INVALID: artifacts: %s" % e for e in reg_errs[:5])

    stages = state.get("stages", {})
    for t in state.get("tasks", []):
        if t.get("stage_id") not in stages:
            reasons.append("CHECKPOINT_INVALID: task %s points at unknown stage %s"
                           % (t.get("task_id"), t.get("stage_id")))
    return (len(reasons) == 0), reasons


def load(root: str, case_id: str) -> tuple:
    """Load and validate. Returns (state, reasons). state is None when invalid."""
    path = os.path.join(store.case_dir(root, case_id), "case_state.json")
    if not os.path.exists(path):
        return None, ["CHECKPOINT_INVALID: no checkpoint at %s" % path]
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:  # noqa: BLE001
        return None, ["CHECKPOINT_INVALID: unreadable (%r)" % e]
    ok, reasons = validate(state, case_id)
    if not ok:
        return None, reasons
    tr.emit(state, "CHECKPOINT_LOADED", detail="case_id=%s" % case_id)
    return state, []


def resume(root: str, case_id: str, workflow: dict, **run_kwargs) -> tuple:
    """Load a validated checkpoint and continue. Returns (report, reasons)."""
    state, reasons = load(root, case_id)
    if state is None:
        return None, reasons
    from . import orchestrator as orch

    before = {t["task_id"]: t["status"] for t in state.get("tasks", [])}
    report = orch.run(state, workflow, **run_kwargs)
    after = {t["task_id"]: t["status"] for t in state.get("tasks", [])}
    rerun = [tid for tid, st in before.items()
             if st == "PASS" and after.get(tid) != "PASS"]
    report["rerun_completed_tasks"] = rerun
    return report, []
