"""Agent Message Bus (Phase 6 V0.1).

Persistent, validated, observable Agent-to-Agent communication.

> Artifact = durable source of truth.
> Message = coordination instruction.

Design rules:
  - Agents send messages referencing artifact_ids (NOT full payload content).
  - The bus validates: sender exists, target exists, artifacts exist.
  - Messages persist as JSONL in the project directory (survives restart).
  - Idempotent by message_id (duplicate send = no-op).
  - The bus does NOT execute anything — the Harness controls execution.

This is separate from EventBus: EventBus is for observability/SSE, the
MessageBus is for agent coordination.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Optional

from runtime.agents import registry as agent_registry
from runtime.agents.registry import is_valid_agent, can_communicate as policy_allows

# allowed message types (§5: limited vocabulary, no free-form chat)
MESSAGE_TYPES = frozenset({
    "TASK_HANDOFF",        # upstream agent hands off to downstream
    "INFORMATION_REQUEST", # agent asks another for info
    "INFORMATION_RESPONSE",# response to an info request
    "REVIEW_REQUEST",      # ask another agent to review an artifact
    "REVIEW_RESPONSE",     # review result
})

MESSAGE_STATUSES = frozenset({"PENDING", "DELIVERED", "ACKED", "FAILED"})


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _uid() -> str:
    return "msg_%s" % uuid.uuid4().hex[:10]


class MessageBus:
    """Persistent agent-to-agent message store, backed by JSONL files."""

    def __init__(self, project_dir: str):
        self._dir = project_dir
        self._path = os.path.join(project_dir, "messages.jsonl")
        os.makedirs(project_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # send
    # ------------------------------------------------------------------ #
    def send(self, *, from_agent: str, to_agent: str, message_type: str,
             task_id: str = "", artifact_ids: Optional[list] = None,
             content: Optional[dict] = None,
             case_state: Optional[dict] = None,
             project: Optional[object] = None,
             message_id: str = "") -> dict:
        """Send a validated message. Returns the message dict or raises ValueError."""
        # validate sender
        if not is_valid_agent(from_agent):
            raise ValueError("UNKNOWN_SENDER: %r not in Agent Registry" % from_agent)
        # validate target
        if not is_valid_agent(to_agent):
            raise ValueError("UNKNOWN_TARGET: %r not in Agent Registry" % to_agent)
        # Phase 6.2: communication policy — sender must be authorized to
        # message this target (prevents unauthorized cross-domain communication)
        if not policy_allows(from_agent, to_agent):
            raise ValueError(
                "COMMUNICATION_NOT_AUTHORIZED: %r may not send to %r "
                "(allowed targets: %s)" % (from_agent, to_agent,
                                           sorted(agent_registry.allowed_message_targets(from_agent))))
        # validate message_type
        if message_type not in MESSAGE_TYPES:
            raise ValueError("INVALID_MESSAGE_TYPE: %r (allowed: %s)"
                             % (message_type, sorted(MESSAGE_TYPES)))
        # validate artifact references
        artifact_ids = artifact_ids or []
        if artifact_ids and case_state is not None:
            from runtime import artifact_registry as reg
            known = {rec["artifact_id"]
                     for rec in (case_state.get("artifact_registry") or {}).values()}
            for aid in artifact_ids:
                if aid not in known:
                    raise ValueError("ARTIFACT_NOT_FOUND: %r not in registry" % aid)

        mid = message_id or _uid()

        # idempotency: check if this message_id already exists
        existing = self.get(mid)
        if existing is not None:
            return existing  # no-op (send exactly once logically)

        msg = {
            "message_id": mid,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "message_type": message_type,
            "task_id": task_id,
            "artifact_ids": list(artifact_ids),
            "content": content or {},
            "created_at": _now(),
            "status": "PENDING",
        }
        self._append(msg)

        # emit observability event via project if available
        if project is not None and hasattr(project, "_event"):
            project._event("agent_message_sent",
                           message_id=mid, from_agent=from_agent,
                           to_agent=to_agent, message_type=message_type,
                           task_id=task_id)
        return msg

    # ------------------------------------------------------------------ #
    # receive / poll
    # ------------------------------------------------------------------ #
    def receive(self, agent_id: str, limit: int = 10) -> list:
        """Get PENDING messages for an agent (marks them DELIVERED)."""
        msgs = self._read_all()
        result = []
        for m in msgs:
            if m["to_agent"] == agent_id and m["status"] == "PENDING":
                self._update_status(m["message_id"], "DELIVERED")
                m["status"] = "DELIVERED"
                result.append(m)
                if len(result) >= limit:
                    break
        # emit received events via project if available
        return result

    def inbox(self, agent_id: str) -> list:
        """All messages addressed to an agent (any status)."""
        return [m for m in self._read_all() if m["to_agent"] == agent_id]

    # ------------------------------------------------------------------ #
    # ack
    # ------------------------------------------------------------------ #
    def ack(self, message_id: str) -> Optional[dict]:
        """Acknowledge a message (DELIVERED → ACKED)."""
        msg = self.get(message_id)
        if msg is None:
            return None
        if msg["status"] != "DELIVERED":
            return msg  # already acked or failed — idempotent
        self._update_status(message_id, "ACKED")
        msg["status"] = "ACKED"
        return msg

    # ------------------------------------------------------------------ #
    # query
    # ------------------------------------------------------------------ #
    def get(self, message_id: str) -> Optional[dict]:
        for m in self._read_all():
            if m["message_id"] == message_id:
                return m
        return None

    def all_messages(self) -> list:
        return self._read_all()

    def can_communicate(self, from_agent: str, to_agent: str,
                        task_graph: Optional[dict] = None) -> bool:
        """Check if from→to is a valid communication path.

        Phase 6.2: checks BOTH the communication policy (registry) and,
        optionally, that the target is a participant in the given task graph."""
        if not is_valid_agent(from_agent) or not is_valid_agent(to_agent):
            return False
        # Phase 6.2: enforce communication policy
        if not policy_allows(from_agent, to_agent):
            return False
        if task_graph is None:
            return True  # no graph constraint — policy check is sufficient
        # check target agent is a participant in the graph
        participants = set()
        for t in task_graph.get("tasks", []):
            assigned = t.get("assigned_agent") or agent_registry.agent_for_task(
                t.get("task_type", ""))
            if assigned:
                participants.add(assigned)
        return to_agent in participants

    # ------------------------------------------------------------------ #
    # persistence (JSONL, mirrors Project._append_jsonl pattern)
    # ------------------------------------------------------------------ #
    def _append(self, msg: dict) -> None:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")

    def _read_all(self) -> list:
        if not os.path.exists(self._path):
            return []
        with open(self._path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def _update_status(self, message_id: str, new_status: str) -> None:
        """Rewrite JSONL with updated status (simple file-level update)."""
        msgs = self._read_all()
        with open(self._path, "w", encoding="utf-8") as f:
            for m in msgs:
                if m["message_id"] == message_id:
                    m["status"] = new_status
                f.write(json.dumps(m, ensure_ascii=False) + "\n")
