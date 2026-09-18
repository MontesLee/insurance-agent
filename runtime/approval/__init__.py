"""Runtime Approval boundary (Phase 9 V0.1).

Human-in-the-loop as a Runtime CONTROL PLANE capability:
  - Agents/Tools may only REQUEST approval (and V0.1 produces no
    agent-originated requests — the two non-replan types are reserved).
  - The ApprovalManager owns approval STATE only — never execution.
  - The Harness is the only layer that pauses for, and resumes from, an
    approval (`LongRunningHarness.resume_approval`).
  - The ApprovalPolicy is deterministic; the LLM never decides.
"""
from runtime.approval.models import (APPROVAL_REPLAN, APPROVAL_EXTERNAL_ACTION,
                                     APPROVAL_HIGH_IMPACT, REQUEST_TYPES,
                                     APPROVAL_STATUSES, TRANSITIONS,
                                     RESOLVE_ACTORS, create_request)
from runtime.approval.store import ApprovalStore
from runtime.approval.policy import ApprovalPolicy, AUTO, HUMAN_APPROVAL
from runtime.approval.manager import ApprovalManager

__all__ = [
    "APPROVAL_REPLAN", "APPROVAL_EXTERNAL_ACTION", "APPROVAL_HIGH_IMPACT",
    "REQUEST_TYPES", "APPROVAL_STATUSES", "TRANSITIONS", "RESOLVE_ACTORS",
    "create_request", "ApprovalStore", "ApprovalPolicy", "AUTO",
    "HUMAN_APPROVAL", "ApprovalManager",
]
