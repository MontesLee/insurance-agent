"""Message-Driven Agent Handoff (Phase 6.1).

Bridges the MessageBus to the Harness: consumes TASK_HANDOFF messages
and ensures the referenced task is acknowledged only after it succeeds.

> Message = coordination intent. Harness = scheduling + execution.
> MessageBus is transport/persistence — it NEVER starts an agent.

Flow:
    Agent A → send TASK_HANDOFF → MessageBus (PENDING)
    Harness.run() → normal sequential execution
    _consume_handoffs() → for each PENDING TASK_HANDOFF:
        validate task_id exists, agent matches, artifacts valid
        if target task PASSED → ACK the message
        if target task FAILED → mark message FAILED
        if task not yet run → leave PENDING (Harness will execute it)
"""
from __future__ import annotations

from typing import Optional

from runtime.agents.message_bus import MessageBus
from runtime.agents import registry as agent_registry

MAX_HANDOFFS_PER_RUN = 20


def consume_handoffs(bus: MessageBus, project, case_state: dict,
                     emit=None) -> dict:
    """Process PENDING TASK_HANDOFF messages after a harness run.

    For each TASK_HANDOFF:
      1. Validate task_id exists in the project's task graph
      2. Validate to_agent matches the task's assigned_agent
      3. Validate artifact_ids exist in CaseState (if provided)
      4. If target task PASSED/COMPLETED → ACK the message
      5. If target task FAILED/NEEDS_REVIEW → mark message FAILED
      6. If task hasn't run yet → leave PENDING (will be consumed on next pass)

    Returns a summary dict with counts.
    """
    emit = emit or (lambda t, d: None)
    stats = {"checked": 0, "acked": 0, "failed": 0, "pending": 0,
             "invalid": 0}

    all_messages = bus.all_messages()
    handoffs = [m for m in all_messages
                if m.get("message_type") == "TASK_HANDOFF"
                and m.get("status") in ("PENDING", "DELIVERED")]

    if len(handoffs) > MAX_HANDOFFS_PER_RUN:
        emit("agent_message_failed", {
            "reason": "COMMUNICATION_LIMIT_EXCEEDED: %d handoffs > %d"
                      % (len(handoffs), MAX_HANDOFFS_PER_RUN)})
        stats["invalid"] += 1
        return stats

    for msg in handoffs:
        stats["checked"] += 1
        mid = msg["message_id"]
        task_id = msg.get("task_id", "")
        to_agent = msg.get("to_agent", "")
        from_agent = msg.get("from_agent", "")

        # T14: self-message blocked
        if from_agent == to_agent:
            bus._update_status(mid, "FAILED")
            emit("handoff_rejected", {
                "message_id": mid, "reason": "SELF_MESSAGE_BLOCKED",
                "from_agent": from_agent, "to_agent": to_agent})
            stats["failed"] += 1
            continue

        # Phase 6.2: communication policy check
        if not agent_registry.can_communicate(from_agent, to_agent):
            bus._update_status(mid, "FAILED")
            emit("handoff_rejected", {
                "message_id": mid, "reason": "COMMUNICATION_NOT_AUTHORIZED",
                "from_agent": from_agent, "to_agent": to_agent})
            stats["invalid"] += 1
            continue

        # T2: TASK_HANDOFF requires task_id
        if not task_id:
            bus._update_status(mid, "FAILED")
            emit("handoff_rejected", {
                "message_id": mid, "reason": "TASK_HANDOFF missing task_id"})
            stats["invalid"] += 1
            continue

        # T3: task must exist in the graph
        task = project.get_task(task_id)
        if task is None:
            bus._update_status(mid, "FAILED")
            emit("handoff_rejected", {
                "message_id": mid, "task_id": task_id,
                "reason": "MESSAGE_TARGET_TASK_NOT_FOUND"})
            stats["invalid"] += 1
            continue

        # T4: target agent must match task assignment
        expected_agent = task.get("assigned_agent") or \
            agent_registry.agent_for_task(task.get("task_type", ""))
        if to_agent != expected_agent:
            bus._update_status(mid, "FAILED")
            emit("handoff_rejected", {
                "message_id": mid, "task_id": task_id,
                "from_agent": from_agent, "to_agent": to_agent,
                "reason": "AGENT_MISMATCH: task %s is assigned to %s, not %s"
                          % (task_id, expected_agent, to_agent)})
            stats["invalid"] += 1
            continue

        # T10: artifact references must be valid
        artifact_ids = msg.get("artifact_ids") or []
        if artifact_ids and case_state is not None:
            from runtime import artifact_registry as reg
            known = {rec["artifact_id"]
                     for rec in (case_state.get("artifact_registry") or {}).values()}
            fake = [a for a in artifact_ids if a not in known]
            if fake:
                bus._update_status(mid, "FAILED")
                emit("handoff_rejected", {
                    "message_id": mid, "task_id": task_id,
                    "reason": "ARTIFACT_NOT_FOUND: %s" % fake[:2]})
                stats["invalid"] += 1
                continue

        # All validations passed → handoff is valid
        task_status = task.get("status", "")
        if task_status in ("PASSED", "COMPLETED"):
            # T8: ACK only after task PASSED
            bus._update_status(mid, "DELIVERED")
            bus.ack(mid)
            emit("handoff_validated", {
                "message_id": mid, "task_id": task_id,
                "from_agent": from_agent, "to_agent": to_agent,
                "task_status": task_status, "outcome": "ACKED"})
            emit("agent_message_acknowledged", {
                "message_id": mid, "task_id": task_id,
                "from_agent": from_agent, "to_agent": to_agent,
                "task_status": task_status})
            stats["acked"] += 1
        elif task_status in ("FAILED", "NEEDS_REVIEW"):
            # T9: no ACK on failure
            bus._update_status(mid, "FAILED")
            emit("handoff_validated", {
                "message_id": mid, "task_id": task_id,
                "from_agent": from_agent, "to_agent": to_agent,
                "task_status": task_status, "outcome": "FAILED"})
            emit("agent_message_failed", {
                "message_id": mid, "task_id": task_id,
                "from_agent": from_agent, "to_agent": to_agent,
                "reason": "target task %s: %s" % (task_id, task_status)})
            stats["failed"] += 1
        elif task_status == "PENDING":
            # Task exists, agent matches, deps may or may not be met.
            # Emit task_activated so the scheduler knows this task has
            # a coordination signal. The Harness still checks dependencies.
            emit("task_activated", {
                "message_id": mid, "task_id": task_id,
                "from_agent": from_agent, "to_agent": to_agent})
            stats["pending"] += 1
        else:
            # task is RUNNING or other state — leave PENDING
            stats["pending"] += 1

    return stats


def pending_handoff_count(bus: MessageBus) -> int:
    """Number of unresolved TASK_HANDOFF messages (for loop-limit checks)."""
    return sum(1 for m in bus.all_messages()
               if m.get("message_type") == "TASK_HANDOFF"
               and m.get("status") in ("PENDING", "DELIVERED"))
