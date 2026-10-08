# -*- coding: utf-8 -*-
"""K.29-B-FIX Phase 1 regression tests — adapter system_prompt delivery.

The bug (audit: docs/production/k29-bfix-prompt-delivery-audit.md):
_GatewayProviderAdapter forwarded only request.messages and dropped
request.system_prompt in BOTH generate() and generate_stream(), so the
QA slice's qa_system_prompt (qa-answer-v3) never reached the provider.

These tests lock the FIXED behavior at three levels:
  adapter unit  (T1-T4: delivery / empty / user-unchanged / streaming)
  QA chain      (T5: run_qa_turn through a REAL build_gateway
                 composition delivers the live qa-answer-v3 prompt)

Nothing here changes prompt content, user messages, retries, watchdog
semantics, or streaming behavior — those are asserted UNCHANGED.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from runtime.grounding.loop import _GatewayProviderAdapter, build_gateway  # noqa: E402
from runtime.llm.types import LLMRequest                      # noqa: E402


# ------------------------------------------------------------------ #
# capture provider (old protocol — the OpenAICompatProvider surface)
# ------------------------------------------------------------------ #
class _Capture:
    name = "capture"
    model = "capture-model"

    def __init__(self):
        self.seen = []

    def generate(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        return SimpleNamespace(text="等待期一般为90天[E1]。",
                               tool_calls=[],
                               usage={"input_tokens": 1,
                                      "output_tokens": 1},
                               latency_ms=1)

    def stream_generate(self, messages, tools):
        self.seen.append([dict(m) for m in messages])

        def _g():
            yield {"type": "delta", "kind": "reasoning", "text": "R"}
            yield {"type": "delta", "kind": "content", "text": "等"}
            yield {"type": "delta", "kind": "content", "text": "待[E1]。"}
            return SimpleNamespace(text="等待期[E1]。",
                                   tool_calls=[],
                                   usage={"input_tokens": 1,
                                          "output_tokens": 1},
                                   latency_ms=1)
        return _g()


def _req(system="TEST_SYSTEM"):
    return LLMRequest(
        messages=[{"role": "user", "content": "U1"}],
        system_prompt=system,
        timeout_s=5.0)


# ------------------------------------------------------------------ #
# T1 — system prompt delivered as the leading system message
# ------------------------------------------------------------------ #
def test_t1_system_prompt_delivered():
    cap = _Capture()
    _GatewayProviderAdapter(cap).generate(_req())
    msgs = cap.seen[-1]
    assert msgs[0] == {"role": "system", "content": "TEST_SYSTEM"}
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[1]["content"] == "U1"


# T2 — empty/absent system prompt keeps the OLD payload byte-for-byte
def test_t2_empty_system_prompt_old_behavior():
    for empty in ("", None):
        cap = _Capture()
        _GatewayProviderAdapter(cap).generate(_req(system=empty))
        msgs = cap.seen[-1]
        assert msgs == [{"role": "user", "content": "U1"}], (
            "empty system_prompt must reproduce the pre-fix payload")


# T3 — user messages unchanged (content, order, count)
def test_t3_user_messages_unchanged():
    cap = _Capture()
    req = LLMRequest(
        messages=[{"role": "user", "content": "A"},
                  {"role": "assistant", "content": "B"},
                  {"role": "user", "content": "C"}],
        system_prompt="S", timeout_s=5.0)
    _GatewayProviderAdapter(cap).generate(req)
    msgs = cap.seen[-1]
    assert msgs[1:] == [{"role": "user", "content": "A"},
                        {"role": "assistant", "content": "B"},
                        {"role": "user", "content": "C"}]
    assert len(msgs) == 4


# T4 — streaming path receives the system message too; deltas unchanged
def test_t4_streaming_path_delivers_system():
    cap = _Capture()
    got = []
    _GatewayProviderAdapter(cap).generate_stream(_req(), got.append)
    msgs = cap.seen[-1]
    assert msgs[0] == {"role": "system", "content": "TEST_SYSTEM"}
    assert msgs[-1]["content"] == "U1"
    # only CONTENT deltas are forwarded (reasoning consumed) — the
    # K.26 streaming contract is unchanged by the fix
    assert "".join(got) == "等待[E1]。"


# T5 — production QA chain: the live qa-answer-v3 prompt reaches the
# provider through the REAL build_gateway composition
def test_t5_production_qa_path_delivers_qa_system_prompt():
    from runtime.qa_agent import run_qa_turn
    from runtime.qa_agent.agent import system_prompt

    class _StubService:
        name = "stub"
        provider = SimpleNamespace(name="stub")

        def build_evidence(self, query, top_k=None, as_of=None,
                           jurisdiction="CN"):
            item = {
                "content": "%s：等待期一般为90天，等待期内确诊仅退保费。" % query,
                "source_name": "stub-source", "document_id": "d1",
                "document_name": "stub doc", "version": "v1",
                "authority_level": "A",
            }
            gov = SimpleNamespace(
                status="success", conflict=False, results=[item],
                retrieval_metadata={"governance": {"allowed": 1,
                                                   "rejected": 0}})
            return [item], gov, [], None

    cap = _Capture()
    gw = build_gateway(cap)          # production composition
    from runtime.intent.classifier import classify
    ir = classify("重疾险等待期一般为多少天？")   # schema-valid, insurance_qa
    assert ir["intent_id"] == "insurance_qa"
    ctx = run_qa_turn(
        "重疾险等待期一般为多少天？", ir,
        service=_StubService(), gateway=gw)
    assert cap.seen, "the provider must have been called"
    msgs = cap.seen[0]
    assert msgs[0]["role"] == "system"
    expected = system_prompt()
    assert msgs[0]["content"] == expected, (
        "the provider must receive the rules-yaml qa_system_prompt "
        "(qa-answer-v3) verbatim")
    assert any("User question:" in m["content"] for m in msgs)
    # grounding outcome itself (grounded or gate-refused) is NOT under
    # test here — only prompt delivery; but the record must be valid
    assert ctx["grounding_status"] in ("grounded", "partial_grounding",
                                       "refused")
