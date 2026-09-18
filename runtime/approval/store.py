"""Approval persistence — one approvals.jsonl per project (Phase 9 §10).

Mirrors the MessageBus persistence pattern (JSONL append + rewrite on
update). No external stores: file JSON only.
"""
from __future__ import annotations

import json
import os


class ApprovalStore:
    def __init__(self, project_dir: str):
        self._dir = project_dir
        self._path = os.path.join(project_dir, "approvals.jsonl")
        os.makedirs(project_dir, exist_ok=True)

    # ---------------- read ---------------- #
    def all(self) -> list:
        if not os.path.exists(self._path):
            return []
        with open(self._path, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def get(self, approval_id: str):
        for a in self.all():
            if a["approval_id"] == approval_id:
                return a
        return None

    def pending(self) -> list:
        return [a for a in self.all()
                if a["status"] in ("PENDING", "WAITING_HUMAN")]

    # ---------------- write ---------------- #
    def append(self, request: dict) -> dict:
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(request, ensure_ascii=False) + "\n")
        return request

    def update(self, approval_id: str, **fields) -> dict:
        """Rewrite the JSONL with the updated record (idempotent by id)."""
        rows = self.all()
        found = None
        with open(self._path, "w", encoding="utf-8") as f:
            for a in rows:
                if a["approval_id"] == approval_id:
                    a.update(fields)
                    found = a
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
        if found is None:
            raise KeyError("approval %s not found" % approval_id)
        return found
