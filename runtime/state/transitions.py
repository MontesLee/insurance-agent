"""Stage transition guards (Phase 7).

These are the invariants that make the pipeline a *pipeline* rather than a bag of scripts:

  1. Monotonicity  -- a later stage may not run before its predecessors complete, and a
                      completed stage may not be re-entered to move backwards.
  2. Preconditions -- a stage may only run when every artifact it `consumes` is present.
  3. Immutability  -- once a stage is COMPLETED, its artifact is frozen. Later stages read
                      it; nothing may rewrite it. (Enforced by fingerprint comparison.)

None of this decides anything about insurance. It only enforces ordering and freeze.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

TERMINAL_OK = ("COMPLETED", "SKIPPED")
IN_FLIGHT = ("PENDING", "RUNNING", "NEEDS_REVIEW", "FAILED")


def fingerprint(artifact: Any) -> Optional[str]:
    """Stable sha256 of a canonical artifact (sorted keys, UTF-8)."""
    if artifact is None:
        return None
    blob = json.dumps(artifact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def is_completed(status: str) -> bool:
    return status == "COMPLETED"


def stage_defs(workflow: dict) -> list:
    return list(workflow.get("stages", []))


def stage_order(workflow: dict) -> list:
    return [s["id"] for s in stage_defs(workflow)]


def stage_by_id(workflow: dict, stage_id: str) -> Optional[dict]:
    for s in stage_defs(workflow):
        if s["id"] == stage_id:
            return s
    return None


def completed_indices(state: dict) -> list:
    idx = []
    for st in state.get("stages", {}).values():
        if is_completed(st.get("status", "")):
            idx.append(st.get("index", -1))
    return sorted(idx)


def _producers(state: dict) -> dict:
    """artifact_type -> stage_id that produces it."""
    out = {}
    for sid, rec in (state.get("stages") or {}).items():
        if rec.get("produces"):
            out[rec["produces"]] = sid
    return out


def guard_preconditions(state: dict, stage: dict) -> tuple:
    """Every `consumes` artifact must be present AND its producing stage COMPLETED.

    Requiring the producer to be COMPLETED (not merely "artifact present") is what makes a
    human-review gate real: a stage parked in NEEDS_REVIEW blocks its downstream consumers.
    """
    producers = _producers(state)
    missing, blocked = [], []
    for art in stage.get("consumes", []) or []:
        if art not in (state.get("artifacts") or {}):
            missing.append(art)
            continue
        sid = producers.get(art)
        if sid and state["stages"][sid].get("status") != "COMPLETED":
            blocked.append("%s (producer %s is %s)" % (art, sid, state["stages"][sid].get("status")))
    reasons = []
    if missing:
        reasons.append("MISSING_INPUT_ARTIFACT: " + ", ".join(missing))
    if blocked:
        reasons.append("INPUT_NOT_RELEASED: " + ", ".join(blocked))
    return (len(reasons) == 0), reasons


def guard_monotonic(state: dict, stage: dict) -> tuple:
    """No later stage may already be completed when an earlier stage runs (no backflow)."""
    this_idx = stage.get("index", -1)
    ahead = [i for i in completed_indices(state) if i > this_idx]
    if ahead:
        return False, ["NON_MONOTONIC: later stage index(es) %s already completed" % ahead]
    return True, []


def guard_not_done(state: dict, stage: dict) -> tuple:
    rec = (state.get("stages") or {}).get(stage["id"], {})
    if rec.get("status") == "COMPLETED":
        return False, ["STAGE_ALREADY_COMPLETED: %s" % stage["id"]]
    return True, []


def guard_immutable(existing: Any, new: Any, stage_id: str) -> tuple:
    """A completed stage's artifact must not change under a later write attempt."""
    if existing is None:
        return True, []
    if fingerprint(existing) != fingerprint(new):
        return False, ["ARTIFACT_MUTATION: %s artifact would change after completion" % stage_id]
    return True, []


def can_run(state: dict, stage: dict) -> tuple:
    """Full guard set for entering a stage. Returns (ok, reasons)."""
    reasons = []
    for guard in (guard_not_done, guard_monotonic, guard_preconditions):
        ok, rs = guard(state, stage)
        if not ok:
            reasons.extend(rs)
    return (len(reasons) == 0), reasons


def next_runnable(state: dict, workflow: dict) -> Optional[str]:
    """The lowest-index stage that is not COMPLETED/SKIPPED.

    Returns None when the case is finished. A stage that is NEEDS_REVIEW/FAILED is
    returned again (it is not done), so the caller can approve/retry it explicitly.
    """
    done = set(completed_indices(state))
    for st in stage_defs(workflow):
        if st.get("index", 0) not in done:
            return st["id"]
    return None


def is_finished(state: dict, workflow: dict) -> bool:
    return all(
        (state.get("stages", {}).get(s["id"], {}).get("status") in TERMINAL_OK)
        for s in stage_defs(workflow)
    )
