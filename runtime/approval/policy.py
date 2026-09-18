"""ApprovalPolicy — the deterministic human-approval decision (Phase 9 §5/§6).

The policy answers ONE question: "may this already-validated high-impact
change proceed automatically, or must a human approve it first?"

It is a pure function of machine-computed facts (the graph diff and the
project's task statuses). LLM wording, timestamps and thread scheduling are
never inputs. The LLM never decides "this needs a human" — the policy does.

V0.1 covers APPROVAL_REPLAN. A high-impact replan is one that:
  - adds more than `replan_added_threshold` new tasks, OR
  - removes any existing task, OR
  - changes any dependency edge, OR
  - re-routes the continuation of already-completed tasks
    (dependency_changes touching a preserved task)

The other two request types (APPROVAL_EXTERNAL_ACTION,
APPROVAL_HIGH_IMPACT) are RESERVED: no runtime path produces them in V0.1;
when a future phase does, their policy hooks live here.
"""
from __future__ import annotations

from typing import Optional

AUTO = "AUTO"
HUMAN_APPROVAL = "HUMAN_APPROVAL"


class ApprovalPolicy:
    def __init__(self, enabled: bool = True, replan_added_threshold: int = 2):
        """enabled=False keeps the gateway installed but fully automatic
        (every outcome AUTO — Phase 8 behaviour)."""
        self.enabled = bool(enabled)
        self.replan_added_threshold = int(replan_added_threshold)

    # ------------------------------------------------------------------ #
    def evaluate_replan(self, diff: dict, project) -> tuple:
        """(outcome, reason) for a validated replan candidate.
        `diff` is the machine-computed Phase 8 graph diff."""
        if not self.enabled:
            return AUTO, "approval gateway disabled (policy AUTO)"
        reasons = []
        added = diff.get("added") or []
        removed = diff.get("removed") or []
        dep_changes = diff.get("dependency_changes") or []
        preserved = set(diff.get("preserved") or [])
        if len(added) > self.replan_added_threshold:
            reasons.append("adds %d new tasks (threshold %d)"
                           % (len(added), self.replan_added_threshold))
        if removed:
            reasons.append("removes existing task(s): %s" % ", ".join(removed[:5]))
        if dep_changes:
            reasons.append("changes %d dependency edge(s)" % len(dep_changes))
        rerouted = [c["task_id"] for c in dep_changes if c["task_id"] in preserved]
        if rerouted:
            reasons.append("re-routes continuation of completed task(s): %s"
                           % ", ".join(rerouted[:5]))
        if reasons:
            return HUMAN_APPROVAL, "; ".join(reasons)
        return AUTO, ("low-impact replan (added=%d, removed=%d, dep_changes=%d)"
                      % (len(added), len(removed), len(dep_changes)))

    # reserved hooks (not produced by any runtime path in V0.1) ------------- #
    def evaluate_external_action(self, action: str, context: Optional[dict]) -> tuple:
        return HUMAN_APPROVAL, "external actions always require a human (reserved)"

    def evaluate_high_impact(self, context: Optional[dict]) -> tuple:
        return HUMAN_APPROVAL, "high-impact decisions always require a human (reserved)"
