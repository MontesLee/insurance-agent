"""Phase 28.K.22 — QA generation streaming tests (Policy B).

Validated content is emitted as agent_stream_delta{kind:content} chunks
AFTER the citation gate passes. Reasoning never exists on this path;
gate failure / provider failure / insufficient evidence emit NOTHING.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from knowledge.service import reset_default_service  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.llm.mock import MockLLMProvider  # noqa: E402
from runtime.qa_agent import run_qa_turn  # noqa: E402

GOOD = ("重大疾病保险常见等待期为90天[E1]。"
        "等待期内确诊重疾一般仅退还保费[E1]。")
UNCITED = "建议你直接买XX重疾险，越早越好。"


class Collector:
    def __init__(self):
        self.events = []

    def __call__(self, event_type, data):
        self.events.append((event_type, data))


def _run(answer=GOOD, fail_with="", question="重疾险的等待期是什么"):
    reset_default_service()
    gw = LLMGateway(MockLLMProvider(content=answer, fail_with=fail_with),
                    max_retries=0)
    col = Collector()
    ctx = run_qa_turn(question, classify(question), gateway=gw, emit=col)
    return ctx, col


def _deltas(col):
    return [d for (t, d) in col.events if t == "agent_stream_delta"]


def test_t1_t6_grounded_emits_validated_content_no_duplication():
    ctx, col = _run()
    assert ctx["grounding_status"] == "grounded"
    ds = _deltas(col)
    assert ds, "citation-PASS answer must stream"
    joined = "".join(d["text"] for d in ds)
    assert joined == ctx["answer"]  # exact convergence, no duplication
    for d in ds:
        assert set(d) == {"kind", "text"}  # payload = existing schema only
        assert d["kind"] == "content"


def test_t2_t3_insufficient_or_empty_evidence_emits_nothing():
    reset_default_service()
    gw = LLMGateway(MockLLMProvider(content=GOOD), max_retries=0)
    col = Collector()
    ctx = run_qa_turn("量子保险精算的布里渊区是什么",
                      classify("量子保险精算的布里渊区是什么"),
                      gateway=gw, emit=col)
    assert ctx["failure_reason"] == "insufficient_evidence"
    assert _deltas(col) == []


def test_t7_citation_fail_emits_nothing():
    ctx, col = _run(answer=UNCITED)
    assert ctx["failure_reason"] == "citation_gate_rejected"
    assert _deltas(col) == []


def test_t8_provider_failure_before_content_emits_nothing():
    ctx, col = _run(fail_with="provider down")
    assert ctx["failure_reason"] == "llm_unavailable"
    assert _deltas(col) == []


def test_t13_payload_leakage_zero():
    _, col = _run()
    # 28.K.25: the collector now also sees the retrieval milestone
    # (tool_* events, existing vocabulary). The LEAKAGE contract applies
    # to the streaming DELTA payloads (what K.22 emits for content):
    deltas = [d for (t, d) in col.events if t == "agent_stream_delta"]
    blob = str(deltas)
    for bad in ("reasoning", "provider", "model", "tool", "skill",
                "run_", "artifact", "prompt", "system"):
        assert bad not in blob, bad
    for d in deltas:
        assert set(d) == {"kind", "text"}
    # the retrieval milestone payload carries only the fixed vocabulary
    for (t, d) in col.events:
        if t.startswith("tool_"):
            assert set(d) <= {"step", "tool"}
            assert d["tool"] == "knowledge_search"


def test_emit_never_breaks_generation():
    """A raising emit callback is presentation-only — answer unaffected."""
    reset_default_service()
    gw = LLMGateway(MockLLMProvider(content=GOOD), max_retries=0)

    def boom(event_type, data):
        raise RuntimeError("sink down")

    ctx = run_qa_turn("重疾险的等待期是什么",
                      classify("重疾险的等待期是什么"),
                      gateway=gw, emit=boom)
    assert ctx["grounding_status"] == "grounded"
