"""Agent conversation state (Phase 2.6).

NOT a second CaseState (spec §7): this is conversation bookkeeping plus a
REFERENCE to the run's CaseState. Client facts live only in CaseState; the
conversation never becomes the fact database.
"""
from __future__ import annotations

from typing import Any, Optional


class AgentState:
    def __init__(self, run_id: str, case_id: str, conversation_id: str):
        self.run_id = run_id
        self.case_id = case_id
        self.conversation_id = conversation_id
        self.status = "running"
        self.turn = 0
        self.intent: str = ""       # GENERAL_KNOWLEDGE | GENERAL_GUIDANCE | CLIENT_ADVISORY | ...
        self.user_messages: list = []      # {id, text}
        self.assistant_messages: list = [] # {id, text, kind: ask|finish|error}
        self.tool_history: list = []       # {tool, status, artifact_id, eval_id}
        self.facts_asked: list = []        # required_fields from ask_user turns
        self.usage = {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0,
                      "latency_ms": 0.0}
        self.provider: Optional[str] = None
        self.model: Optional[str] = None

    # ------------------------------------------------------------------ #
    # LLM-facing projections (summaries only — never hidden reasoning)
    # ------------------------------------------------------------------ #
    def messages_for_llm(self, max_turns: int = 12) -> list:
        out: list = []
        for um in self.user_messages[-max_turns:]:
            out.append({"role": "user", "content": um["text"]})
            reply = next((a for a in reversed(self.assistant_messages)
                          if a.get("after") == um["id"]), None)
            if reply:
                out.append({"role": "assistant", "content": reply["text"]})
        return out

    def add_user(self, text: str) -> str:
        mid = "um_%d" % (len(self.user_messages) + 1)
        self.user_messages.append({"id": mid, "text": text})
        return mid

    def add_assistant(self, text: str, kind: str, after: str) -> None:
        self.assistant_messages.append({"id": "am_%d" % (len(self.assistant_messages) + 1),
                                        "text": text, "kind": kind, "after": after})

    def context_summary(self, state: Any = None) -> str:
        """One-screen summary of what the runtime already has (artifact ids/types)."""
        lines = []
        if state is not None:
            arts = state.get("artifacts") or {}
            if arts:
                lines.append("stored artifacts: " + ", ".join(sorted(arts.keys())))
            evals = state.get("evaluations") or []
            if evals:
                bad = [e["eval_id"] for e in evals if e.get("status") == "FAIL"]
                lines.append("evals: %d (%s)" % (len(evals),
                                                 "all PASS" if not bad else "FAIL: " + ",".join(bad[-3:])))
            st = state.get("status")
            if st:
                lines.append("case status: %s" % st)
        if self.facts_asked:
            lines.append("previously asked for: " + "; ".join(self.facts_asked[-8:]))
        return "\n".join(lines)

    def to_public(self) -> dict:
        """Serializable view for the chat API (no provider secrets, no CoT)."""
        return {
            "run_id": self.run_id,
            "case_id": self.case_id,
            "conversation_id": self.conversation_id,
            "status": self.status,
            "intent": self.intent or None,
            "turn": self.turn,
            "user_messages": self.user_messages,
            "assistant_messages": self.assistant_messages,
            "tool_history": self.tool_history,
            "usage": self.usage,
            "provider": self.provider,
            "model": self.model,
        }
