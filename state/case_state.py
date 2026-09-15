"""CaseState container (Phase 7).

Thin, explicit operations over the state dict. No business logic: it stores artifacts,
tracks stage status, appends events, and stamps fingerprints. All ordering policy lives in
`state.transitions`; all artifact shape policy lives in `contracts/`.
"""
from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional

from . import transitions

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "case_state.schema.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def now() -> str:
    """Public timestamp helper (UTC ISO-8601)."""
    return _now()


def new_case_state(case_id: str, workflow: dict) -> dict:
    """Create an empty CaseState bound to a workflow definition."""
    order = transitions.stage_order(workflow)
    stages = {}
    for st in transitions.stage_defs(workflow):
        stages[st["id"]] = {
            "index": st["index"],
            "skill": st["skill"],
            "produces": st.get("produces"),
            "consumes": list(st.get("consumes") or []),
            "gate": st.get("gate", "auto"),
            "executor": st.get("executor", "python"),
            "status": "PENDING",
            "provided_by": None,
            "started_at": None,
            "completed_at": None,
            "attempts": 0,
            "artifact_fingerprint": None,
            "notes": [],
            # --- Step 3: task / repair linkage (populated by workflow.tasks) ---
            "task_id": None,
            "max_attempts": int(st.get("max_attempts", 3)),
            "repairs": [],
            "failure_reason": None,
            "eval_ids": [],
        }
    services = {}
    for sv in workflow.get("services", []) or []:
        services[sv["id"]] = {
            "skill": sv["skill"],
            "provides": sv.get("provides"),
            "calls": 0,
            "last_requester": None,
            "last_at": None,
            "source_unchanged": None,
        }
    now = _now()
    state = {
        "case_id": case_id,
        "workflow": workflow.get("workflow"),
        "workflow_version": str(workflow.get("version", "")),
        "created_at": now,
        "updated_at": now,
        # --- Step 3: agent-control layer -------------------------------------
        "status": "PENDING",
        "waiting_for_user": None,
        "artifact_registry": {},
        "tasks": [],
        "evaluations": [],
        "checkpoints": [],
        "trace": [],
        "review": None,
        # --- Phase 7 core ----------------------------------------------------
        "stage_order": order,
        "current_stage": None,
        "stages": stages,
        "artifacts": {},
        "services": services,
        "events": [],
    }
    record_event(state, "CASE_CREATED", detail="case %s" % case_id)
    return state


# --------------------------------------------------------------------------- #
# Step 3: case-level status & user hand-off
# --------------------------------------------------------------------------- #
def set_case_status(state: dict, status: str, detail: Optional[str] = None) -> None:
    state["status"] = status
    state["updated_at"] = _now()
    record_event(state, "CASE_STATUS", detail="%s%s" % (status, (": " + detail) if detail else ""))


def wait_for_user(state: dict, reason: str, trigger_stage: Optional[str] = None,
                  blocking_fields: Optional[list] = None, conflicts: Optional[list] = None,
                  next_questions: Optional[list] = None) -> dict:
    """Park the case until the client supplies more information.

    This is the Step 3 hard stop: while `waiting_for_user` is set, the orchestrator must not
    advance downstream. Missing facts stay UNKNOWN; conflicts are never resolved by picking one.
    """
    handoff = {
        "reason": reason,
        "trigger_stage": trigger_stage,
        "blocking_fields": list(blocking_fields or []),
        "conflicts": list(conflicts or []),
        "next_questions": list(next_questions or []),
        "requested_at": _now(),
    }
    state["waiting_for_user"] = handoff
    set_case_status(state, "WAITING_FOR_USER",
                    "%s @ %s" % (reason, trigger_stage or "<none>"))
    record_event(state, "WAITING_FOR_USER", stage=trigger_stage, detail=reason)
    return handoff


def clear_waiting_for_user(state: dict) -> None:
    state["waiting_for_user"] = None
    state["updated_at"] = _now()


def needs_review(state: dict, stage_id: Optional[str], reason: str,
                 failed_checks: Optional[list] = None, repair_attempts: int = 0) -> dict:
    rec = {
        "stage_id": stage_id,
        "reason": reason,
        "failed_checks": list(failed_checks or []),
        "repair_attempts": repair_attempts,
        "at": _now(),
    }
    state["review"] = rec
    set_case_status(state, "NEEDS_REVIEW", "%s @ %s" % (reason, stage_id or "<none>"))
    return rec


def record_event(state: dict, event_type: str, stage: Optional[str] = None,
                 detail: Optional[str] = None) -> None:
    state.setdefault("events", []).append(
        {"at": _now(), "type": event_type, "stage": stage, "detail": detail}
    )
    state["updated_at"] = _now()


def set_status(state: dict, stage_id: str, status: str, note: Optional[str] = None) -> None:
    rec = state["stages"][stage_id]
    rec["status"] = status
    if note:
        rec.setdefault("notes", []).append(note)
    state["updated_at"] = _now()


def put_artifact(state: dict, artifact_type: str, artifact: dict, stage_id: str) -> tuple:
    """Store a stage's artifact, enforcing immutability of completed stages.

    Returns (ok, reasons). A write that would change an already-frozen artifact is refused.
    """
    existing = state["artifacts"].get(artifact_type)
    ok, reasons = transitions.guard_immutable(existing, artifact, stage_id)
    if not ok:
        record_event(state, "GUARD_REJECTED", stage=stage_id, detail="; ".join(reasons))
        return False, reasons
    state["artifacts"][artifact_type] = copy.deepcopy(artifact)
    state["stages"][stage_id]["artifact_fingerprint"] = transitions.fingerprint(artifact)
    record_event(state, "ARTIFACT_STORED", stage=stage_id, detail=artifact_type)
    return True, []


def get_artifact(state: dict, artifact_type: str) -> Optional[dict]:
    return state["artifacts"].get(artifact_type)


def verified(state: dict, stage_id: str) -> bool:
    """True when the stored artifact still matches the fingerprint recorded at completion."""
    rec = state["stages"].get(stage_id, {})
    art_type = rec.get("produces")
    if not art_type or art_type not in state["artifacts"]:
        return False
    return transitions.fingerprint(state["artifacts"][art_type]) == rec.get("artifact_fingerprint")


def statuses(state: dict) -> dict:
    return {sid: rec["status"] for sid, rec in state["stages"].items()}


def to_json(state: dict, indent: int = 2) -> str:
    return json.dumps(state, ensure_ascii=False, indent=indent)


def validate(state: dict) -> tuple:
    """Validate the state object against state/case_state.schema.json."""
    from jsonschema import Draft7Validator

    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    Draft7Validator.check_schema(schema)
    errors = sorted(Draft7Validator(schema).iter_errors(state), key=lambda e: list(e.path))
    msgs = ["%s: %s" % ("/".join(str(p) for p in e.path) or "<root>", e.message) for e in errors]
    return (len(msgs) == 0, msgs)
