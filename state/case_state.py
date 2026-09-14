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
        "stage_order": order,
        "current_stage": None,
        "stages": stages,
        "artifacts": {},
        "services": services,
        "events": [],
    }
    record_event(state, "CASE_CREATED", detail="case %s" % case_id)
    return state


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
