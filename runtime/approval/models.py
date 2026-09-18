"""Approval models (Phase 9 V0.1).

An ApprovalRequest is the durable record of something the runtime wants to
do that requires HUMAN judgement before it may proceed. The request itself
carries no execution power: approving it only changes approval state —
activating a graph or resuming execution remains Harness-only.

Statuses:
    PENDING → WAITING_HUMAN → APPROVED → RESUMED
                            → REJECTED (fail closed; nothing resumes)
                            → EXPIRED   (fail closed; never auto-continues)
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

# request types (V0.1: exactly one auto-produced; two reserved)
APPROVAL_REPLAN = "APPROVAL_REPLAN"                  # high-impact graph revision
APPROVAL_EXTERNAL_ACTION = "APPROVAL_EXTERNAL_ACTION"  # reserved (send_email/…)
APPROVAL_HIGH_IMPACT = "APPROVAL_HIGH_IMPACT"          # reserved (domain decisions)

REQUEST_TYPES = frozenset({APPROVAL_REPLAN, APPROVAL_EXTERNAL_ACTION,
                           APPROVAL_HIGH_IMPACT})

# state machine
APPROVAL_STATUSES = frozenset({
    "PENDING", "WAITING_HUMAN", "APPROVED", "REJECTED", "EXPIRED", "RESUMED"})

# allowed transitions (anything else is refused — fail closed)
TRANSITIONS = {
    "PENDING": {"WAITING_HUMAN"},
    "WAITING_HUMAN": {"APPROVED", "REJECTED", "EXPIRED"},
    "APPROVED": {"RESUMED"},
    "REJECTED": set(),
    "EXPIRED": set(),
    "RESUMED": set(),
}

# who may resolve an approval (deterministic actor allowlist; §18)
RESOLVE_ACTORS = frozenset({"human", "harness"})


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def new_approval_id() -> str:
    return "appr_%s" % uuid.uuid4().hex[:10]


def create_request(*, project_id: str, request_type: str, reason: str,
                   task_id: str = "", graph_revision: Optional[int] = None,
                   context: Optional[dict] = None,
                   options: Optional[list] = None,
                   requested_by: str = "harness",
                   approval_id: str = "") -> dict:
    """Build a PENDING ApprovalRequest dict (validated shape)."""
    if request_type not in REQUEST_TYPES:
        raise ValueError("unknown request_type %r (allowed: %s)"
                         % (request_type, sorted(REQUEST_TYPES)))
    return {
        "approval_id": approval_id or new_approval_id(),
        "project_id": project_id,
        "task_id": task_id,
        "graph_revision": graph_revision,
        "request_type": request_type,
        "reason": reason[:500],
        "context": context or {},
        "options": options or ["approve", "reject"],
        "default_action": None,
        "status": "PENDING",
        "requested_by": requested_by[:120],
        "created_at": _now(),
        "resolved_at": None,
        "resolved_by": None,
        "decision": None,
    }


def can_transition(status: str, to: str) -> bool:
    return to in TRANSITIONS.get(status, set())
