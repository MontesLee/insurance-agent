"""Phase 28.K.1 — needs_review consumer-copy boundary (P2-① hotfix).

The eval-blocked finish path must deliver the fixed natural-language
template ONLY: the raw tool summary (internal stage/tool ids such as
"product_candidate_provider") stays in the event stream for internal
diagnostics and never reaches the consumer-visible message.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from runtime import orchestrator as orch  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.agent import FakeLLMProvider, run_agent_turn  # noqa: E402
from runtime.agent.agent import NEEDS_REVIEW_MESSAGE  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402
from runtime.agent.tools import Tool, ToolContext  # noqa: E402

WF = orch.load_workflow()

LEAK_SUMMARIES = [
    # Case A — the exact 28.K pilot leak
    "product_candidate_provider did not pass evaluation after repair — "
    "needs human review",
    # Case B — any unknown internal stage/tool name
    "unknown_internal_stage did not pass evaluation after repair — "
    "needs human review",
    # adversarial: summary carrying other internal families
    "run_abc123 agent insurance-planning-agent registry_lookup provider "
    "QA_REFUSED did not pass evaluation after repair",
]


def _drive(monkeypatch, summary):
    """One agent turn whose only tool returns needs_review with the given
    (possibly poisonous) summary; returns (outcome, events)."""
    from runtime.agent import agent as agent_mod

    def fake_registry():
        return {"record_client_profile": Tool(
            "record_client_profile", "test double",
            {"type": "object", "properties": {}, "additionalProperties": True},
            lambda args, ctx: {"status": "needs_review", "summary": summary,
                               "eval_id": "E-K1"})}

    monkeypatch.setattr(agent_mod, "build_registry", fake_registry)

    events = []

    def emit(event_type, data):
        events.append({"event_type": event_type, "data": data})

    state = cs.new_case_state("agentcase-k1", WF)
    tk.init_tasks(state, WF)
    ctx = ToolContext(state, WF, "run_k1", persist=lambda: None)
    agent_state = AgentState("run_k1", "agentcase-k1", "chat_k1")
    outcome = run_agent_turn(
        FakeLLMProvider([("record_client_profile", {})]),
        agent_state, "K.1 copy boundary probe", ctx, emit)
    return outcome, events, agent_state


@pytest.mark.parametrize("summary", LEAK_SUMMARIES,
                         ids=["pilot-leak", "unknown-stage", "internal-family"])
def test_needs_review_message_is_fixed_consumer_copy(monkeypatch, summary):
    """Case A/B: whatever the tool summary says, the delivered message is
    the natural-language template with ZERO occurrences of it."""
    outcome, _, agent_state = _drive(monkeypatch, summary)
    assert outcome.status == "needs_review"
    assert outcome.message == NEEDS_REVIEW_MESSAGE
    for token in summary.split():
        assert token not in outcome.message, (
            "internal token %r leaked into consumer message" % token)
    # the chat transcript message (what the consumer reads) is the same
    last = agent_state.assistant_messages[-1]
    assert last["kind"] == "finish"
    assert last["text"] == NEEDS_REVIEW_MESSAGE


def test_internal_diagnostics_unchanged(monkeypatch):
    """Case C: Developer/Operator diagnostics keep the internal detail —
    the event stream still carries the tool summary and the machine
    reason; only the MESSAGE is consumerized."""
    summary = LEAK_SUMMARIES[0]
    outcome, events, _ = _drive(monkeypatch, summary)
    tool_events = [e for e in events if e["event_type"].startswith("tool_")]
    assert any(summary[:40] in (e["data"].get("summary") or "")
               for e in tool_events), "tool summary must stay in events"
    finals = [e for e in events
              if e["event_type"] == "agent_decision" and e["data"].get("final")]
    assert finals and finals[0]["data"]["status"] == "needs_review"
    assert finals[0]["data"]["reason"] == "eval_failed_after_repair"
    assert outcome.reason == "eval_failed_after_repair"


def test_template_copy_has_no_internal_markers():
    """The fixed template itself is natural language only: no ascii
    identifiers of any kind (pure Chinese + punctuation)."""
    assert not [c for c in NEEDS_REVIEW_MESSAGE if c.isascii() and c.isalnum()]
