"""Control-plane persistence (Phase 10 §30).

JSONL/JSON per project — the same house pattern as MessageBus/approvals:

    <project_dir>/supervisor.json        durable SupervisorState
    <project_dir>/alerts.jsonl           alert log (dedup by fingerprint)
    <project_dir>/notifications.jsonl    human notifications
    <project_dir>/control_commands.jsonl audited human commands

No external stores (§45): file JSON only.
"""
from __future__ import annotations

import json
import os


class ControlStore:
    def __init__(self, project_dir: str):
        self._dir = project_dir
        os.makedirs(project_dir, exist_ok=True)

    # ---------------- supervisor state ---------------- #
    def load_supervisor(self, project_id: str) -> dict:
        from runtime.control import models
        path = os.path.join(self._dir, "supervisor.json")
        if not os.path.exists(path):
            return models.make_supervisor_state(project_id)
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def save_supervisor(self, state: dict) -> dict:
        path = os.path.join(self._dir, "supervisor.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return state

    # ---------------- jsonl helpers ---------------- #
    def _read(self, name: str) -> list:
        path = os.path.join(self._dir, name)
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def _append(self, name: str, record: dict) -> dict:
        with open(os.path.join(self._dir, name), "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def _update(self, name: str, record_id: str, id_field: str,
                **fields) -> dict:
        rows = self._read(name)
        found = None
        with open(os.path.join(self._dir, name), "w", encoding="utf-8") as f:
            for r in rows:
                if r.get(id_field) == record_id:
                    r.update(fields)
                    found = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if found is None:
            raise KeyError("%s %s not found" % (name, record_id))
        return found

    # ---------------- alerts ---------------- #
    def alerts(self) -> list:
        return self._read("alerts.jsonl")

    def open_alerts(self) -> list:
        return [a for a in self.alerts() if a.get("status") == "OPEN"]

    def find_open_alert(self, fingerprint: str):
        for a in self.open_alerts():
            if a.get("fingerprint") == fingerprint:
                return a
        return None

    def append_alert(self, alert: dict) -> dict:
        return self._append("alerts.jsonl", alert)

    def resolve_alert(self, alert_id: str, resolved_at: str) -> dict:
        return self._update("alerts.jsonl", alert_id, "alert_id",
                            status="RESOLVED", resolved_at=resolved_at)

    # ---------------- notifications ---------------- #
    def notifications(self) -> list:
        return self._read("notifications.jsonl")

    def append_notification(self, notification: dict) -> dict:
        return self._append("notifications.jsonl", notification)

    # ---------------- control commands ---------------- #
    def commands(self) -> list:
        return self._read("control_commands.jsonl")

    def get_command(self, command_id: dict) -> dict:
        for c in self.commands():
            if c["command_id"] == command_id:
                return c
        return None

    def append_command(self, command: dict) -> dict:
        return self._append("control_commands.jsonl", command)

    def update_command(self, command_id: str, **fields) -> dict:
        return self._update("control_commands.jsonl", command_id,
                            "command_id", **fields)
