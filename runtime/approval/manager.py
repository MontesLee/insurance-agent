"""ApprovalManager — approval STATE only, never execution (Phase 9 §4/§7).

The manager owns the ApprovalRequest lifecycle: create, wait, approve,
reject, expire, mark-resumed. It deliberately has NO ability to resume
tasks, activate graphs or execute anything — that authority stays with the
Harness (`LongRunningHarness.resume_approval`).

Permission boundary (deterministic actor allowlist, §18):
  approve/reject: actor must be "human" (the API) — agents, planners,
  tools and the message bus are refused by construction (they cannot even
  import a path that mutates approvals) and by the actor check.
"""
from __future__ import annotations

from typing import Callable, Optional

from runtime.approval import models
from runtime.approval.store import ApprovalStore


class ApprovalManager:
    def __init__(self, project_dir: str,
                 emit: Optional[Callable[[str, dict], None]] = None):
        self.store = ApprovalStore(project_dir)
        self._emit = emit or (lambda t, d: None)

    # ---------------- queries ---------------- #
    def get(self, approval_id: str) -> Optional[dict]:
        return self.store.get(approval_id)

    def list(self) -> list:
        return self.store.all()

    def list_pending(self) -> list:
        return self.store.pending()

    # ---------------- lifecycle ---------------- #
    def create_request(self, request: dict) -> dict:
        rec = self.store.append(request)
        self._emit("approval_requested", {
            "approval_id": rec["approval_id"], "project_id": rec["project_id"],
            "task_id": rec["task_id"], "graph_revision": rec["graph_revision"],
            "request_type": rec["request_type"], "reason": rec["reason"][:160]})
        return rec

    def wait(self, approval_id: str) -> dict:
        """PENDING → WAITING_HUMAN (the runtime pauses for a human)."""
        return self._transition(approval_id, "WAITING_HUMAN", "approval_waiting")

    def approve(self, approval_id: str, actor: str = "human") -> dict:
        """WAITING_HUMAN → APPROVED. Idempotent on APPROVED; refused on any
        other terminal state. Human-only by actor allowlist."""
        rec = self._require(approval_id)
        if actor not in models.RESOLVE_ACTORS:
            return self._refused(rec, "approve",
                                 "ACTOR_NOT_AUTHORIZED: %r may not approve "
                                 "(human only)" % actor)
        if rec["status"] == "APPROVED":
            return {"ok": True, "already": True, "approval": rec}
        if not models.can_transition(rec["status"], "APPROVED"):
            return self._refused(rec, "approve",
                                 "INVALID_TRANSITION: %s → APPROVED"
                                 % rec["status"])
        rec = self.store.update(approval_id, status="APPROVED",
                                decision="APPROVE", resolved_by=actor,
                                resolved_at=models._now())
        self._emit("approval_approved", {
            "approval_id": approval_id, "project_id": rec["project_id"],
            "task_id": rec["task_id"], "graph_revision": rec["graph_revision"],
            "actor": actor})
        return {"ok": True, "already": False, "approval": rec}

    def reject(self, approval_id: str, actor: str = "human",
               reason: str = "") -> dict:
        """WAITING_HUMAN → REJECTED. Fail closed: nothing ever resumes on a
        rejected approval. Idempotent on REJECTED."""
        rec = self._require(approval_id)
        if actor not in models.RESOLVE_ACTORS:
            return self._refused(rec, "reject",
                                 "ACTOR_NOT_AUTHORIZED: %r may not reject "
                                 "(human only)" % actor)
        if rec["status"] == "REJECTED":
            return {"ok": True, "already": True, "approval": rec}
        if not models.can_transition(rec["status"], "REJECTED"):
            return self._refused(rec, "reject",
                                 "INVALID_TRANSITION: %s → REJECTED"
                                 % rec["status"])
        rec = self.store.update(approval_id, status="REJECTED",
                                decision="REJECT", resolved_by=actor,
                                resolved_at=models._now(),
                                reject_reason=reason[:300])
        self._emit("approval_rejected", {
            "approval_id": approval_id, "project_id": rec["project_id"],
            "task_id": rec["task_id"], "graph_revision": rec["graph_revision"],
            "actor": actor, "reason": reason[:160]})
        return {"ok": True, "already": False, "approval": rec}

    def expire(self, approval_id: str, reason: str = "") -> dict:
        """WAITING_HUMAN → EXPIRED. Fail closed — EXPIRED never continues.
        V0.1 does not set TTLs automatically; this is an explicit operation."""
        rec = self._require(approval_id)
        if not models.can_transition(rec["status"], "EXPIRED"):
            return self._refused(rec, "expire",
                                 "INVALID_TRANSITION: %s → EXPIRED"
                                 % rec["status"])
        rec = self.store.update(approval_id, status="EXPIRED",
                                decision="EXPIRE",
                                resolved_at=models._now(),
                                reject_reason=reason[:300])
        self._emit("approval_expired", {
            "approval_id": approval_id, "project_id": rec["project_id"],
            "graph_revision": rec["graph_revision"]})
        return {"ok": True, "approval": rec}

    def mark_resumed(self, approval_id: str) -> dict:
        """APPROVED → RESUMED. Called ONLY by the Harness after it has
        actually activated the approved change and resumed execution."""
        rec = self._require(approval_id)
        if rec["status"] == "RESUMED":
            return {"ok": True, "already": True, "approval": rec}
        if not models.can_transition(rec["status"], "RESUMED"):
            return self._refused(rec, "resume",
                                 "INVALID_TRANSITION: %s → RESUMED (only the "
                                 "Harness resumes an APPROVED request)"
                                 % rec["status"])
        rec = self.store.update(approval_id, status="RESUMED")
        self._emit("approval_resumed", {
            "approval_id": approval_id, "project_id": rec["project_id"],
            "graph_revision": rec["graph_revision"]})
        return {"ok": True, "approval": rec}

    # ---------------- internals ---------------- #
    def _require(self, approval_id: str) -> dict:
        rec = self.store.get(approval_id)
        if rec is None:
            raise KeyError("approval %s not found" % approval_id)
        return rec

    def _transition(self, approval_id: str, to: str, event: str) -> dict:
        rec = self._require(approval_id)
        if not models.can_transition(rec["status"], to):
            raise ValueError("INVALID_TRANSITION: %s → %s" % (rec["status"], to))
        rec = self.store.update(approval_id, status=to)
        self._emit(event, {
            "approval_id": approval_id, "project_id": rec["project_id"],
            "task_id": rec["task_id"], "graph_revision": rec["graph_revision"]})
        return rec

    def _refused(self, rec: dict, op: str, reason: str) -> dict:
        self._emit("approval_failed", {
            "approval_id": rec["approval_id"], "project_id": rec["project_id"],
            "graph_revision": rec["graph_revision"],
            "operation": op, "reason": reason[:160]})
        return {"ok": False, "already": False, "error": reason, "approval": rec}
