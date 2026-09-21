"""Queue operations layer — Phase 26B (authorized cancel + approval).

Closes F26A-P2-01: cancel is no longer bare DB access — it requires
an IDENTITY whose role may cancel (OWNER/OPERATOR; REVIEWER denied;
unauthenticated denied). Every authorized action writes an append-only
audit event (actor/project/run/task/reason/timestamp) to the queue's
OWN audit table (operator domain, same pattern as
knowledge_registry_events).

approve_and_resume implements the HITL hand-back: it verifies the task
is actually WAITING_FOR_APPROVAL, is bound to (project, run, task,
stage), records the approval marker the executor will verify, and
REQUEUES the task (FAILED -> PENDING — a legal 26A transition; the
next claim increments the attempt).
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

from . import agent_runtime, model
from .store import QueueError, TaskQueueStore

OPS_DDL = """
CREATE TABLE IF NOT EXISTS queue_ops_events (
    event_id    BIGSERIAL PRIMARY KEY,
    action      VARCHAR(40) NOT NULL,      -- CANCEL / APPROVE / REJECT
    actor       VARCHAR(120) NOT NULL,     -- authenticated identity
    role        VARCHAR(30) NOT NULL,
    project_id  VARCHAR(64),
    run_id      VARCHAR(120),
    task_id     VARCHAR(120),
    stage       VARCHAR(120),
    reason      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

CANCEL_ROLES = ("OWNER", "OPERATOR")
APPROVE_ROLES = ("OWNER", "REVIEWER", "OPERATOR")


class OpsDenied(RuntimeError):
    """Authorization failed — the action is refused (fail closed)."""


class QueueOps:
    """Authorized queue operations with audit. Wraps (never changes)
    the 26A TaskQueueStore semantics."""

    def __init__(self, store: TaskQueueStore, connect: Optional = None,
                 run_root: Optional[str] = None):
        self.store = store
        self._connect = connect
        self.run_root = run_root
        if connect is not None:
            with connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(OPS_DDL)

    # ---- audit ---------------------------------------------------------- #
    def _audit(self, action: str, actor: str, role: str, task: dict,
               stage: str = "", reason: str = "") -> None:
        if self._connect is None:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO queue_ops_events
                        (action, actor, role, project_id, run_id,
                         task_id, stage, reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (action, actor[:120], role[:30],
                      task.get("project_id") or None,
                      task.get("run_id") or None,
                      task.get("task_id"), stage[:120] or None,
                      (reason or "")[:400]))

    def audit_log(self, task_id: Optional[str] = None) -> list:
        if self._connect is None:
            return []
        with self._connect() as conn:
            with conn.cursor() as cur:
                if task_id:
                    cur.execute("SELECT * FROM queue_ops_events WHERE "
                                "task_id=%s ORDER BY event_id",
                                (task_id,))
                else:
                    cur.execute("SELECT * FROM queue_ops_events "
                                "ORDER BY event_id")
                out = []
                for r in cur.fetchall():
                    d = dict(r)
                    d["created_at"] = str(d.get("created_at"))
                    out.append(d)
                return out

    # ---- cancel (26B-13) ------------------------------------------------- #
    def cancel(self, ident, task_id: str, reason: str = "") -> dict:
        """OWNER/OPERATOR only. REVIEWER and unauthenticated are
        DENIED. A cancelled task can never be completed afterwards
        (terminal CANCELLED; the 26A CAS refuses any later write)."""
        actor, role = _identity(ident)
        if role not in CANCEL_ROLES:
            raise OpsDenied(
                "cancel denied for role %r (allowed: %s)"
                % (role, "/".join(CANCEL_ROLES)))
        task = self.store.get(task_id)
        if task is None:
            raise QueueError("task %s not found" % task_id)
        out = self.store.cancel(task_id)
        self._audit("CANCEL", actor, role, task, reason=reason)
        return out

    # ---- HITL approve / reject (26B-12) ----------------------------------- #
    def approve_and_resume(self, ident, task_id: str,
                           stage: Optional[str] = None) -> dict:
        """Approve the human gate a WAITING task paused at and hand it
        back to the queue. Binding: the task MUST be waiting (its
        retry_reason names the stage), and the written approval marker
        carries (project, run, task, stage) — the resume executor
        re-verifies all of them, so an approval for task A can never
        resume task B."""
        actor, role = _identity(ident)
        if role not in APPROVE_ROLES:
            raise OpsDenied(
                "approval denied for role %r (allowed: %s)"
                % (role, "/".join(APPROVE_ROLES)))
        task = self.store.get(task_id)
        if task is None:
            raise QueueError("task %s not found" % task_id)
        pending = agent_runtime.parse_defer_reason(
            task.get("retry_reason"))
        # BOTH the reason and the STATUS must say waiting: a terminal
        # task (e.g. CANCELLED) with a leftover reason never resumes
        if pending is None or task.get("status") != "FAILED":
            raise QueueError(
                "task %s is not WAITING_FOR_APPROVAL (status=%s, "
                "reason=%r) — refusing to resume a non-waiting task"
                % (task_id, task.get("status"),
                   task.get("retry_reason")))
        if stage is not None and stage != pending:
            raise QueueError(
                "approval stage mismatch: task waits at %r, approval "
                "names %r" % (pending, stage))
        self._write_marker(task, pending, actor, "APPROVED")
        out = self.store.requeue(task_id)
        self._audit("APPROVE", actor, role, task, stage=pending)
        return {"outcome": "REQUEUED_FOR_RESUME", "task_id": task_id,
                "stage": pending, "actor": actor}

    def reject(self, ident, task_id: str,
               reason: str = "rejected") -> dict:
        """Human REJECT at the gate: the run fails closed (the waiting
        task is cancelled — terminal, never resumed)."""
        actor, role = _identity(ident)
        if role not in APPROVE_ROLES:
            raise OpsDenied("reject denied for role %r" % role)
        task = self.store.get(task_id)
        if task is None:
            raise QueueError("task %s not found" % task_id)
        pending = agent_runtime.parse_defer_reason(
            task.get("retry_reason"))
        if pending is None or task.get("status") != "FAILED":
            raise QueueError("task %s is not WAITING_FOR_APPROVAL"
                             % task_id)
        self._write_marker(task, pending, actor, "REJECTED")
        out = self.store.cancel(task_id)
        self._audit("REJECT", actor, role, task, stage=pending,
                    reason=reason)
        return {"outcome": "CANCELLED", "task_id": task_id,
                "stage": pending, "actor": actor}

    # ---- marker --------------------------------------------------------- #
    def _write_marker(self, task: dict, stage: str, actor: str,
                      decision: str) -> None:
        """The approval marker the resume executor verifies. Written
        into the newest attempt dir of the task's run root."""
        if not self.run_root:
            return
        marker = {
            "decision": decision,
            "task_id": task["task_id"],
            "run_id": task.get("run_id") or None,
            "project_id": task.get("project_id") or None,
            "stage": stage,
            "actor": actor,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        attempt = task.get("attempt") or 1
        d = os.path.join(self.run_root, "attempt-%d" % attempt)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, agent_runtime.APPROVAL_FILE), "w",
                  encoding="utf-8") as f:
            json.dump(marker, f, ensure_ascii=False, indent=1)


def _identity(ident):
    """(actor, role) from a runtime.auth Identity (or an explicit
    (name, role) tuple for tests). Unauthenticated -> DENY."""
    if ident is None:
        raise OpsDenied("unauthenticated — action denied")
    if isinstance(ident, tuple) and len(ident) == 2:
        return str(ident[0]), str(ident[1]).upper()
    role = getattr(ident, "role", None)
    user = getattr(ident, "user", None)
    if not role or not user:
        raise OpsDenied("identity without role — action denied")
    return str(user), str(role).upper()
