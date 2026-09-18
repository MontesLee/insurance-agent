"""ControlPlane (Phase 10 §5) — the human intervention boundary.

The control plane NEVER mutates runtime state itself. Every command flows:

    ControlPlane → persist command (audit) → Harness validates →
    Harness mutates state → checkpoint → events

and every observation flows:

    state/events → deterministic RuntimeMonitor → signals →
    deterministic InterventionPolicy → NONE / NOTIFY / PAUSE / WAIT_APPROVAL

Human-on-the-loop: the default outcome is NONE — agents keep executing;
the human is notified or the runtime pauses only when deterministic
thresholds say so. Phase 9's approval gateway remains a separate,
unchanged boundary.
"""
from __future__ import annotations

import hashlib
import json
from typing import Optional

from runtime.control import models as M
from runtime.control.monitor import RuntimeMonitor
from runtime.control.policy import InterventionPolicy
from runtime.control.store import ControlStore


class ControlPlane:
    def __init__(self, harness, project,
                 monitor: Optional[RuntimeMonitor] = None,
                 policy: Optional[InterventionPolicy] = None):
        self.harness = harness
        self.project = project
        self.store = ControlStore(project._dir)
        self.monitor = monitor or RuntimeMonitor()
        self.policy = policy or InterventionPolicy()

    # ------------------------------------------------------------------ #
    # observation (HOTL) — never mutates tasks/graphs
    # ------------------------------------------------------------------ #
    def observe(self, executed: Optional[list] = None) -> dict:
        project = self.project
        supervisor = self.store.load_supervisor(project.project_id)
        events = project.events()
        self._emit("monitor_started", {"signal_count_pending": True})
        observation = self.monitor.observe(
            project, events=events, max_replans=self.harness.max_replans)

        # ---- dedup + alert lifecycle (§34/§35) -------------------------- #
        # Signals the human has ACKNOWLEDGED by resuming are suppressed until
        # their state actually changes (a changed relevant_state produces a
        # new fingerprint and fires again) — otherwise a persistent signal
        # would re-pause the runtime immediately after every human resume.
        acknowledged = set(supervisor.get("acknowledged_fingerprints") or [])
        current_fingerprints = set()
        effective_signals = []
        graph_revision = getattr(project, "current_graph_revision", 1) or 1
        for signal in observation["signals"]:
            fp = M.signal_fingerprint(
                project.project_id, signal["signal_type"],
                signal.get("task_id", ""), graph_revision,
                signal.get("relevant_state", ""))
            current_fingerprints.add(fp)
            if fp in acknowledged:
                continue   # human reviewed this exact condition already
            effective_signals.append(signal)
            if self.store.find_open_alert(fp) is not None:
                continue   # dedup: same signal/state fires once
            alert = M.make_alert(project.project_id, signal, fp, graph_revision)
            self.store.append_alert(alert)
            self._emit("monitor_signal_detected", {
                "signal_type": signal["signal_type"],
                "task_id": signal.get("task_id", ""),
                "severity": signal["severity"],
                "fingerprint": fp[:16]})
        # resolve alerts whose condition no longer holds
        for alert in self.store.open_alerts():
            if alert.get("fingerprint") not in current_fingerprints:
                self.store.resolve_alert(alert["alert_id"], M._now())
                if alert["alert_id"] in (supervisor.get("active_alerts") or []):
                    supervisor["active_alerts"].remove(alert["alert_id"])
        # the intervention decision uses only UNacknowledged signals
        observation["risk_level"] = self.monitor.risk_level(effective_signals)
        observation["signals"] = effective_signals

        # ---- risk + intervention decision -------------------------------- #
        waiting = bool(self.harness._waiting_approvals(project))
        decision = self.policy.decide(observation, supervisor, project,
                                      waiting_approval=waiting)
        if observation["risk_level"] != supervisor.get("risk_level"):
            self._emit("risk_level_changed", {
                "from": supervisor.get("risk_level"),
                "to": observation["risk_level"]})
        supervisor["risk_level"] = observation["risk_level"]
        supervisor["active_alerts"] = [a["alert_id"] for a in
                                       self.store.open_alerts()]

        action = decision["action"]
        if action == M.INTERVENTION_WAIT_APPROVAL:
            supervisor["status"] = "WAITING_HUMAN"
        elif action == M.INTERVENTION_NOTIFY:
            self._notify_open_alerts(project)
            self._emit("intervention_notified", {
                "risk_level": observation["risk_level"],
                "reason": decision["reason"][:160]})
            supervisor["pending_interventions"] = []
        elif action == M.INTERVENTION_PAUSE:
            # a pause is also a notification — the human must learn why
            self._notify_open_alerts(project)
            supervisor["status"] = "PAUSING"   # honored at the safe barrier
            supervisor["pending_interventions"] = [{
                "action": "PAUSE", "reason": decision["reason"][:200]}]
            self._emit("intervention_required", {
                "action": "PAUSE", "risk_level": observation["risk_level"],
                "reason": decision["reason"][:160]})
        observation["recommended_intervention"] = action
        observation["decision_reason"] = decision["reason"]
        self.store.save_supervisor(supervisor)
        return observation

    def request_intervention(self, reason: str, requested_by: str = "agent",
                             context: Optional[dict] = None,
                             requested_action: str = M.INTERVENTION_NOTIFY) -> dict:
        """Phase 10 §25: an AGENT-side request — a SIGNAL, never a command.
        The requested_action is recorded (and NOTIFY-honoured as a
        notification) but the deterministic Monitor/Policy remain the
        authority: a request can never pause, resume or mutate anything."""
        project = self.project
        signal = M.make_signal(
            "SIGNAL_AGENT_REQUEST", "MEDIUM",
            message="intervention requested by %s: %s"
                    % (requested_by, reason[:160]),
            relevant_state="requested_action:%s" % requested_action)
        fp = M.signal_fingerprint(
            project.project_id, signal["signal_type"], requested_by,
            getattr(project, "current_graph_revision", 1) or 1,
            signal["relevant_state"] + reason[:120])
        if self.store.find_open_alert(fp) is None:
            alert = M.make_alert(project.project_id, signal, fp,
                                 getattr(project, "current_graph_revision", 1)
                                 or 1)
            self.store.append_alert(alert)
            self.store.append_notification(
                M.make_notification(project.project_id, alert))
            self._emit("intervention_notified", {
                "requested_by": requested_by[:120],
                "requested_action": requested_action,
                "reason": reason[:160]})
            return {"ok": True, "alert_id": alert["alert_id"],
                    "note": "request recorded; policy remains the authority"}
        return {"ok": True, "already": True,
                "note": "identical request already active"}

    def _notify_open_alerts(self, project) -> None:
        for alert in self.store.open_alerts():
            if not any(n.get("alert_id") == alert["alert_id"]
                       for n in self.store.notifications()):
                self.store.append_notification(
                    M.make_notification(project.project_id, alert))

    def supervisor(self) -> dict:
        return self.store.load_supervisor(self.project.project_id)

    def set_status(self, status: str) -> dict:
        sup = self.supervisor()
        sup["status"] = status
        sup["updated_at"] = M._now()
        return self.store.save_supervisor(sup)

    # ------------------------------------------------------------------ #
    # commands — audited, idempotent, applied BY THE HARNESS
    # ------------------------------------------------------------------ #
    def command(self, command: str, actor: str = "human",
                payload: Optional[dict] = None) -> dict:
        project = self.project
        cmd = M.make_command(project.project_id, command, actor=actor,
                             payload=payload or {})
        # idempotency (§29): an identical APPLIED command is returned as-is.
        # The fingerprint includes the ACTOR — an identical payload from a
        # different (unauthorized) actor must never ride an applied command
        # and skip the permission check.
        fp = self._payload_fingerprint(cmd)
        for prior in self.store.commands():
            if prior.get("status") == "APPLIED" \
                    and prior.get("command") == command \
                    and prior.get("_fingerprint") == fp:
                return {"ok": True, "already": True, "command": prior,
                        "result": prior.get("result")}
        cmd["_fingerprint"] = fp
        self.store.append_command(cmd)
        self._emit("control_command_received", {
            "command_id": cmd["command_id"], "command": command,
            "actor": actor})
        result = self.harness._apply_control_command(project, cmd)
        if result.get("ok"):
            self.store.update_command(cmd["command_id"], status="APPLIED",
                                      applied_at=M._now(),
                                      result=result.get("result"))
            self._emit("control_command_applied", {
                "command_id": cmd["command_id"], "command": command})
        else:
            self.store.update_command(cmd["command_id"], status="REJECTED",
                                      error=str(result.get("error", ""))[:300])
            self._emit("control_command_rejected", {
                "command_id": cmd["command_id"], "command": command,
                "reason": str(result.get("error", ""))[:160]})
        return {"ok": result.get("ok", False), "already": False,
                "command": self.store.get_command(cmd["command_id"]),
                "result": result.get("result"),
                "error": result.get("error")}

    def recover_pending_commands(self) -> int:
        """§29: commands persisted but not applied (crash) are re-applied
        idempotently on the next harness contact."""
        applied = 0
        for cmd in self.store.commands():
            if cmd.get("status") in ("RECEIVED", "VALIDATED"):
                result = self.harness._apply_control_command(self.project, cmd)
                self.store.update_command(
                    cmd["command_id"],
                    status="APPLIED" if result.get("ok") else "REJECTED",
                    applied_at=M._now() if result.get("ok") else None,
                    error="" if result.get("ok")
                    else str(result.get("error", ""))[:300])
                applied += 1
        return applied

    # ------------------------------------------------------------------ #
    def _payload_fingerprint(self, cmd: dict) -> str:
        blob = json.dumps([cmd["project_id"], cmd["command"], cmd["actor"],
                           cmd["payload"]],
                          ensure_ascii=False, sort_keys=True,
                          default=str, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def _emit(self, event_type: str, data: dict) -> None:
        project = self.project
        self.harness.emit(event_type, {"project_id": project.project_id,
                                       **(data or {})})
        safe = {k: v for k, v in (data or {}).items()
                if isinstance(v, (str, int, float, bool)) or v is None
                or (isinstance(v, list) and all(isinstance(x, str) for x in v))}
        project._event(event_type, **safe)
