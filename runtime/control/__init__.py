"""Runtime Control Plane (Phase 10 V0.1) — Human-on-the-loop.

The human is a SUPERVISOR above the workflow DAG, not a node inside it:
agents execute autonomously by default; a deterministic monitor observes
runtime health; a deterministic intervention policy decides when the human
is notified or the runtime pauses; every human command is audited and
applied by the Harness — never by direct state mutation. Phase 9's
approval gateway remains a separate, unchanged boundary.
"""
from runtime.control.models import (
    RUNTIME_STATUSES, RISK_LOW, RISK_MEDIUM, RISK_HIGH, RISK_CRITICAL,
    RISK_LEVELS, SIGNAL_TASK_FAILURE, SIGNAL_REPAIR_EXHAUSTED,
    SIGNAL_REPLAN_EXHAUSTED, SIGNAL_REPLAN_NO_CHANGE, SIGNAL_BUDGET_EXCEEDED,
    SIGNAL_LONG_RUNNING, SIGNAL_REPEATED_FAILURE,
    SIGNAL_GRAPH_CHANGE_HIGH_IMPACT, SIGNAL_INTEGRITY,
    INTERVENTION_NONE, INTERVENTION_NOTIFY, INTERVENTION_PAUSE,
    INTERVENTION_WAIT_APPROVAL, INTERVENTION_CANCEL, COMMANDS,
    signal_fingerprint, make_signal, make_alert, make_notification,
    make_command, make_supervisor_state, make_observation)
from runtime.control.monitor import RuntimeMonitor
from runtime.control.policy import InterventionPolicy
from runtime.control.manager import ControlPlane
from runtime.control.store import ControlStore

__all__ = [
    "RUNTIME_STATUSES", "RISK_LOW", "RISK_MEDIUM", "RISK_HIGH", "RISK_CRITICAL",
    "RISK_LEVELS", "SIGNAL_TASK_FAILURE", "SIGNAL_REPAIR_EXHAUSTED",
    "SIGNAL_REPLAN_EXHAUSTED", "SIGNAL_REPLAN_NO_CHANGE",
    "SIGNAL_BUDGET_EXCEEDED", "SIGNAL_LONG_RUNNING", "SIGNAL_REPEATED_FAILURE",
    "SIGNAL_GRAPH_CHANGE_HIGH_IMPACT", "SIGNAL_INTEGRITY",
    "INTERVENTION_NONE", "INTERVENTION_NOTIFY", "INTERVENTION_PAUSE",
    "INTERVENTION_WAIT_APPROVAL", "INTERVENTION_CANCEL", "COMMANDS",
    "signal_fingerprint", "make_signal", "make_alert", "make_notification",
    "make_command", "make_supervisor_state", "make_observation",
    "RuntimeMonitor", "InterventionPolicy", "ControlPlane", "ControlStore",
]
