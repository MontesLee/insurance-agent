"""InterventionPolicy (Phase 10 §12) — deterministic, never LLM-decided.

Answers ONE question: "does the runtime's CURRENT state warrant human
intervention, and of what kind?" It does NOT replace the Phase 9
ApprovalPolicy (which decides whether a SPECIFIC action/graph needs
approval). Deterministic mapping (§12):

    LOW      → NONE
    MEDIUM   → NOTIFY
    HIGH     → NOTIFY (configurable, e.g. "PAUSE")
    CRITICAL → PAUSE

plus WAIT_APPROVAL whenever a Phase 9 approval gate is already waiting —
the approval boundary keeps priority over supervisor notifications.
"""
from __future__ import annotations

from typing import Optional

from runtime.control import models as M


class InterventionPolicy:
    def __init__(self, high: str = M.INTERVENTION_NOTIFY,
                 medium: str = M.INTERVENTION_NOTIFY,
                 critical: str = M.INTERVENTION_PAUSE):
        self.actions = {
            M.RISK_LOW: M.INTERVENTION_NONE,
            M.RISK_MEDIUM: medium,
            M.RISK_HIGH: high,
            M.RISK_CRITICAL: critical,
        }

    def decide(self, observation: dict, supervisor: Optional[dict] = None,
               project=None, waiting_approval: bool = False) -> dict:
        """(action, reason) — a pure function of the observation."""
        # Phase 9 boundary keeps priority: an approval gate already waiting
        if waiting_approval or (supervisor or {}).get("status") == "WAITING_HUMAN" \
                or getattr(project, "status", "") == "waiting_approval":
            return {"action": M.INTERVENTION_WAIT_APPROVAL,
                    "reason": "a Phase 9 approval gate is waiting"}
        risk = observation.get("risk_level", M.RISK_LOW)
        action = self.actions.get(risk, M.INTERVENTION_NONE)
        reason = ("risk %s from %d signal(s): %s"
                  % (risk, len(observation.get("signals") or []),
                     ", ".join(sorted({s["signal_type"] for s in
                                       observation.get("signals") or []}))[:200]))
        return {"action": action, "reason": reason}
