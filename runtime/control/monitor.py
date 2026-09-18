"""RuntimeMonitor (Phase 10 §8–§11) — deterministic observation only.

Inputs: project state (tasks / replans / graph revisions / status),
the durable event log, approval state. Output: an Observation (signals +
runtime risk level + recommended intervention seed).

The monitor NEVER acts: no pause(), no replan(), no state mutation
(§1/§13). All rules are deterministic functions of the observed state —
the LLM is never consulted (§9). "Risk" here is RUNTIME execution risk,
not insurance business risk (R1–R5 are unrelated).
"""
from __future__ import annotations

from typing import Optional

from runtime.control import models as M

DEFAULT_CONFIG = {
    "repeated_failure_threshold": 3,   # task_failed events per task
    "max_tasks": 20,                   # budget: active task count
    "max_replans": 2,                  # budget: replan attempts
    "max_repairs": 6,                  # budget: summed repair attempts
    "long_running_seconds": 3600,      # per-task staleness (wall-clock)
}


class RuntimeMonitor:
    def __init__(self, config: Optional[dict] = None):
        self.config = dict(DEFAULT_CONFIG)
        self.config.update(config or {})

    # ------------------------------------------------------------------ #
    def observe(self, project, events: Optional[list] = None,
                max_replans: int = 2) -> dict:
        """Pure observation of the CURRENT durable state. Deterministic
        except SIGNAL_LONG_RUNNING, which by nature reads wall-clock age
        from the stored updated_at (documented; excluded from determinism
        tests)."""
        signals = []
        tasks = getattr(project, "tasks", None) or []
        replans = getattr(project, "replans", None) or []
        graph_revision = getattr(project, "current_graph_revision", 1) or 1
        events = events if events is not None else []

        # ---- integrity (CRITICAL) -------------------------------------- #
        ids = {t.get("task_id") for t in tasks}
        dangling = [d for t in tasks
                    for d in (t.get("dependencies") or []) if d not in ids]
        # the ACTIVE revision (if any) must match current_graph_revision —
        # a rejected/superseded tail revision is legitimate and is NOT a
        # violation (current may legitimately point at an earlier revision)
        all_revisions = getattr(project, "graph_revisions", []) or []
        active = [r for r in all_revisions if r.get("status") == "active"]
        revision_mismatch = (
            (tasks and not active)
            or (active and active[-1].get("revision") != graph_revision))
        if dangling or revision_mismatch \
                or any(t.get("status") not in _KNOWN_TASK_STATUSES for t in tasks):
            signals.append(M.make_signal(
                M.SIGNAL_INTEGRITY, "CRITICAL",
                message="graph integrity violation: dangling=%s "
                        "active_revision=%s current=%s"
                        % (sorted(set(dangling))[:3],
                           [a.get("revision") for a in active[-1:]],
                           graph_revision),
                relevant_state="dangling:%d" % len(dangling)))

        # ---- task failure / repair exhaustion -------------------------- #
        for t in tasks:
            if t.get("status") in ("NEEDS_REVIEW", "FAILED"):
                signals.append(M.make_signal(
                    M.SIGNAL_TASK_FAILURE, "MEDIUM", task_id=t["task_id"],
                    message="task %s is %s" % (t["task_id"], t["status"]),
                    relevant_state=t["status"]))
                if int(t.get("attempt") or 0) >= 3:
                    signals.append(M.make_signal(
                        M.SIGNAL_REPAIR_EXHAUSTED, "MEDIUM",
                        task_id=t["task_id"],
                        message="task %s exhausted its repair budget "
                                "(attempts=%d)" % (t["task_id"],
                                                   t.get("attempt")),
                        relevant_state="attempt:%s" % t.get("attempt")))

        # ---- repeated failure (per task, from the event log) ----------- #
        threshold = self.config["repeated_failure_threshold"]
        fail_counts: dict = {}
        for e in events:
            if e.get("event_type") == "task_failed" and e.get("task_id"):
                fail_counts[e["task_id"]] = fail_counts.get(e["task_id"], 0) + 1
        for tid, n in sorted(fail_counts.items()):
            if n >= threshold:
                signals.append(M.make_signal(
                    M.SIGNAL_REPEATED_FAILURE, "HIGH", task_id=tid,
                    message="task %s failed %d times" % (tid, n),
                    relevant_state="fails:%d" % n))

        # ---- replan health ---------------------------------------------- #
        for r in replans:
            if r.get("status") == "no_change":
                signals.append(M.make_signal(
                    M.SIGNAL_REPLAN_NO_CHANGE, "MEDIUM",
                    message="replan %s reproduced the same graph"
                            % r.get("replan_id", ""),
                    relevant_state="no_change"))
            if r.get("status") in ("failed", "rejected"):
                signals.append(M.make_signal(
                    M.SIGNAL_TASK_FAILURE, "MEDIUM",
                    message="replan %s ended %s" % (r.get("replan_id", ""),
                                                    r.get("status")),
                    relevant_state="replan:%s" % r.get("status")))
        effective_budget = max(1, max_replans or self.config["max_replans"])
        if len(replans) >= effective_budget \
                and any(r.get("status") != "accepted" for r in replans):
            signals.append(M.make_signal(
                M.SIGNAL_REPLAN_EXHAUSTED, "HIGH",
                message="replan budget exhausted (%d attempts)" % len(replans),
                relevant_state="replans:%d" % len(replans)))

        # ---- budgets ------------------------------------------------------ #
        if len(tasks) > self.config["max_tasks"]:
            signals.append(M.make_signal(
                M.SIGNAL_BUDGET_EXCEEDED, "MEDIUM",
                message="task budget exceeded: %d > %d"
                        % (len(tasks), self.config["max_tasks"]),
                relevant_state="tasks:%d" % len(tasks)))
        repair_total = sum(max(0, int(t.get("attempt") or 0) - 1)
                           for t in tasks
                           if t.get("status") in ("NEEDS_REVIEW", "FAILED"))
        if repair_total > self.config["max_repairs"]:
            signals.append(M.make_signal(
                M.SIGNAL_BUDGET_EXCEEDED, "MEDIUM",
                message="repair budget exceeded: %d > %d"
                        % (repair_total, self.config["max_repairs"]),
                relevant_state="repairs:%d" % repair_total))

        # ---- long running (wall-clock by nature) ------------------------- #
        import time as _time
        now = _time.time()
        for t in tasks:
            if t.get("status") == "RUNNING":
                age = now - _ts(t.get("updated_at"))
                if age > self.config["long_running_seconds"]:
                    signals.append(M.make_signal(
                        M.SIGNAL_LONG_RUNNING, "MEDIUM", task_id=t["task_id"],
                        message="task %s running for %.0fs" % (t["task_id"], age),
                        relevant_state="age:%d" % int(age)))

        # ---- high-impact graph change (reuses the Phase 8 diff verbatim) -- #
        for r in replans:
            diff = r.get("diff") or {}
            if diff.get("removed") or diff.get("dependency_changes"):
                signals.append(M.make_signal(
                    M.SIGNAL_GRAPH_CHANGE_HIGH_IMPACT, "HIGH",
                    message="replan %s removed %d task(s), changed %d dep(s)"
                            % (r.get("replan_id", ""),
                               len(diff.get("removed") or []),
                               len(diff.get("dependency_changes") or [])),
                    relevant_state="removed:%d,deps:%d"
                                   % (len(diff.get("removed") or []),
                                      len(diff.get("dependency_changes") or []))))
                break   # one signal per replan-ledger is enough

        risk = self.risk_level(signals)
        return M.make_observation(getattr(project, "project_id", ""),
                                  risk, signals, recommended_intervention="")

    # ------------------------------------------------------------------ #
    @staticmethod
    def risk_level(signals: list) -> str:
        """Deterministic severity → risk roll-up (§11)."""
        risk = M.RISK_LOW
        for s in signals:
            sev = M.SEVERITY_TO_RISK.get(s.get("severity"), M.RISK_LOW)
            if _risk_rank(sev) > _risk_rank(risk):
                risk = sev
        return risk


_KNOWN_TASK_STATUSES = {"PENDING", "RUNNING", "PASSED", "FAILED", "BLOCKED",
                        "NEEDS_REVIEW", "COMPLETED"}
_RISK_ORDER = {M.RISK_LOW: 0, M.RISK_MEDIUM: 1, M.RISK_HIGH: 2,
               M.RISK_CRITICAL: 3}


def _risk_rank(level: str) -> int:
    return _RISK_ORDER.get(level, 0)


def _ts(iso: Optional[str]) -> float:
    import calendar
    try:
        return calendar.timegm(_parse_iso(iso))
    except Exception:  # noqa: BLE001 — unparsable timestamps read as fresh
        import time as _time
        return _time.time()


def _parse_iso(iso):
    from datetime import datetime, timezone
    if not iso:
        return datetime.now(timezone.utc).timetuple()
    return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timetuple()
