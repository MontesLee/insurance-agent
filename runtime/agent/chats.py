"""Agent chat sessions (Phase 2.6) — in-memory V0.1.

Chat is the USER ENTRY, not the runtime (spec §25/§55): a chat owns messages and
references runs; a run owns execution. Client facts live only in the run's
CaseState — the chat never becomes the fact database.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Optional


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class ChatManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._chats: dict = {}   # chat_id -> {"chat_id", "created_at", "messages", "runs"}

    def get_or_create(self, chat_id: Optional[str],
                      owner: Optional[str] = None) -> dict:
        """Create (or fetch) a chat. 28.G: a NEW chat is bound at creation
        to the authenticated subject (`owner`) — server-side only; clients
        never supply ownership. High-entropy id (D-API-2)."""
        with self._lock:
            cid = chat_id or ("chat_%s" % uuid.uuid4().hex[:16])
            if cid not in self._chats:
                self._chats[cid] = {"chat_id": cid, "created_at": _now(),
                                    "owner": owner,
                                    "messages": [], "runs": []}
            return dict(self._chats[cid])

    def exists(self, chat_id: str) -> bool:
        with self._lock:
            return chat_id in self._chats

    def add_user_message(self, chat_id: str, text: str) -> dict:
        with self._lock:
            chat = self._chats[chat_id]
            msg = {"role": "user", "content": text, "at": _now()}
            chat["messages"].append(msg)
            return dict(msg)

    def add_assistant_message(self, chat_id: str, text: str, kind: str,
                              run_id: str) -> dict:
        with self._lock:
            chat = self._chats[chat_id]
            msg = {"role": "assistant", "content": text, "kind": kind,
                   "run_id": run_id, "at": _now()}
            chat["messages"].append(msg)
            return dict(msg)

    def link_run(self, chat_id: str, run_id: str) -> None:
        with self._lock:
            self._chats[chat_id]["runs"].append(run_id)

    def view(self, chat_id: str) -> Optional[dict]:
        with self._lock:
            chat = self._chats.get(chat_id)
            return dict(chat) if chat else None

    def delete(self, chat_id: str) -> Optional[dict]:
        """28.I (D-GOV-3): physically remove the conversation record (the
        caller owns policy/audit/tombstone). Returns the removed record —
        content NEVER survives here; only the governance tombstone
        (identity/timestamp/reason, no content) remains."""
        with self._lock:
            return self._chats.pop(chat_id, None)
