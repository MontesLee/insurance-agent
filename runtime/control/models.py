"""Control-plane models (Phase 10 V0.1).

Human-on-the-loop: the human is a SUPERVISOR above the workflow DAG, not a
node inside it. These models cover the durable vocabulary of that
supervision: runtime status, monitor signals, runtime risk levels,
alerts, notifications, control commands and the supervisor state.

NOTE on "risk": everything here is RUNTIME execution risk (agent runtime
health) — deliberately unrelated to the insurance domain's R1–R5 client
risk categories.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Optional

# ---- runtime (supervisor) statuses ---------------------------------------- #
# WAITING_HUMAN is the Phase 9 approval state and is deliberately distinct
# from PAUSED: WAITING_HUMAN = an approval gate awaits a decision;
# PAUSED = the supervisor proactively paused the runtime.
RUNTIME_STATUSES = frozenset({
    "RUNNING", "PAUSING", "PAUSED", "RESUMING", "COMPLETED", "FAILED",
    "CANCELLED", "WAITING_HUMAN"})

# ---- deterministic monitor signals ---------------------------------------- #
SIGNAL_TASK_FAILURE = "SIGNAL_TASK_FAILURE"
SIGNAL_REPAIR_EXHAUSTED = "SIGNAL_REPAIR_EXHAUSTED"
SIGNAL_REPLAN_EXHAUSTED = "SIGNAL_REPLAN_EXHAUSTED"
SIGNAL_REPLAN_NO_CHANGE = "SIGNAL_REPLAN_NO_CHANGE"
SIGNAL_BUDGET_EXCEEDED = "SIGNAL_BUDGET_EXCEEDED"
SIGNAL_LONG_RUNNING = "SIGNAL_LONG_RUNNING"
SIGNAL_REPEATED_FAILURE = "SIGNAL_REPEATED_FAILURE"
SIGNAL_GRAPH_CHANGE_HIGH_IMPACT = "SIGNAL_GRAPH_CHANGE_HIGH_IMPACT"
SIGNAL_INTEGRITY = "SIGNAL_INTEGRITY"            # CRITICAL: corrupted invariants

# ---- deterministic runtime risk levels ------------------------------------- #
RISK_LOW = "LOW"
RISK_MEDIUM = "MEDIUM"
RISK_HIGH = "HIGH"
RISK_CRITICAL = "CRITICAL"
RISK_LEVELS = (RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL)

SEVERITY_TO_RISK = {"LOW": RISK_LOW, "MEDIUM": RISK_MEDIUM,
                    "HIGH": RISK_HIGH, "CRITICAL": RISK_CRITICAL}

# ---- intervention outcomes -------------------------------------------------- #
INTERVENTION_NONE = "NONE"
INTERVENTION_NOTIFY = "NOTIFY"
INTERVENTION_PAUSE = "PAUSE"
INTERVENTION_WAIT_APPROVAL = "WAIT_APPROVAL"
INTERVENTION_CANCEL = "CANCEL"

# ---- control commands -------------------------------------------------------- #
COMMANDS = frozenset({
    "PAUSE", "RESUME", "RETRY_TASK", "CANCEL", "REPLAN",
    "PROVIDE_INFORMATION", "APPROVE", "REJECT"})
COMMAND_STATUSES = frozenset({"RECEIVED", "VALIDATED", "APPLIED", "REJECTED"})

# ---- alert lifecycle --------------------------------------------------------- #
ALERT_STATUSES = frozenset({"OPEN", "RESOLVED"})


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _uid(prefix: str) -> str:
    return "%s_%s" % (prefix, uuid.uuid4().hex[:10])


def signal_fingerprint(project_id: str, signal_type: str, task_id: str,
                       graph_revision: int, relevant_state="") -> str:
    """§34: stable dedup fingerprint — same signal/project/task/revision/
    state fires once until the state actually changes."""
    blob = json.dumps([str(project_id), str(signal_type), str(task_id or ""),
                       int(graph_revision or 0), str(relevant_state or "")],
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def make_signal(signal_type: str, severity: str, task_id: str = "",
                message: str = "", relevant_state: str = "") -> dict:
    return {"signal_type": signal_type, "severity": severity,
            "task_id": task_id, "message": message[:300],
            "relevant_state": str(relevant_state)[:200]}


def make_alert(project_id: str, signal: dict, fingerprint: str,
               graph_revision: int = 1) -> dict:
    return {
        "alert_id": _uid("alert"),
        "project_id": project_id,
        "signal_type": signal["signal_type"],
        "task_id": signal.get("task_id", ""),
        "severity": signal["severity"],
        "risk_level": SEVERITY_TO_RISK.get(signal["severity"], RISK_LOW),
        "fingerprint": fingerprint,
        "graph_revision": graph_revision,
        "message": signal.get("message", ""),
        "status": "OPEN",
        "created_at": _now(),
        "resolved_at": None,
    }


def make_notification(project_id: str, alert: dict) -> dict:
    """§14: the human-facing notification record (a future Feishu adapter
    consumes exactly this model)."""
    return {
        "notification_id": _uid("notif"),
        "project_id": project_id,
        "alert_id": alert["alert_id"],
        "severity": alert["severity"],
        "signal_type": alert["signal_type"],
        "task_id": alert.get("task_id", ""),
        "message": alert.get("message", "")[:300],
        "created_at": _now(),
        "status": "PENDING",
    }


def make_command(project_id: str, command: str, actor: str = "human",
                 payload: Optional[dict] = None,
                 command_id: str = "") -> dict:
    if command not in COMMANDS:
        raise ValueError("unknown command %r (allowed: %s)"
                         % (command, sorted(COMMANDS)))
    return {
        "command_id": command_id or _uid("cmd"),
        "project_id": project_id,
        "command": command,
        "actor": actor[:120],
        "payload": payload or {},
        "status": "RECEIVED",
        "created_at": _now(),
        "applied_at": None,
        "error": "",
        "result": None,
    }


def make_supervisor_state(project_id: str) -> dict:
    return {
        "project_id": project_id,
        "status": "RUNNING",
        "risk_level": RISK_LOW,
        "active_alerts": [],
        "pending_interventions": [],
        "last_event_id": None,
        "last_checkpoint_id": None,
        "updated_at": _now(),
    }


def make_observation(project_id: str, risk_level: str, signals: list,
                     recommended_intervention: str) -> dict:
    return {"project_id": project_id, "risk_level": risk_level,
            "signals": signals,
            "recommended_intervention": recommended_intervention}
