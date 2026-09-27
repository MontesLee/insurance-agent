"""Phase 28.K.26 — True LLM Streaming tests.

The QA path now streams SENTENCE-VALIDATED content DURING generation
(T_first_delta < T_final), replacing K.22's post-generation 48-char
chunking. The final gates still arbitrate the terminal result.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from knowledge.service import reset_default_service  # noqa: E402
from runtime.grounding import gate as ggate  # noqa: E402
from runtime.grounding.loop import build_gateway  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.qa_agent import run_qa_turn  # noqa: E402

S1 = "重大疾病保险常见等待期为90天[E1]。"
S2 = "等待期内确诊重疾一般仅退还保费[E1]。"
S3 = "百万医疗险主要用于报销符合约定的医疗费用[E2]。"
GOOD = S1 + S2 + S3
UNCITED_TAIL = "建议你直接买XX重疾险，越早越好。"


class StreamProvider:
    """Streams content-kind chunks with real delays (true streaming)."""

    def __init__(self, chunks, delay=0.05, fail_with=""):
        self.name = "streamprov"
        self.model = "m"
        self._chunks = list(chunks)
        self._delay = delay
        self._fail = fail_with
        self.calls = 0

    def generate(self, messages, tools):
        raise AssertionError("streaming path must not call generate()")

    def stream_generate(self, messages, tools):
        self.calls += 1
        if self._fail:
            raise RuntimeError(self._fail)
        text_parts = []
        for c in self._chunks:
            time.sleep(self._delay)
            yield {"kind": "content", "text": c}
            text_parts.append(c)
        yield {"kind": "reasoning", "text": "内部思考不应外流"}
        from runtime.agent.model import LLMResponse
        return LLMResponse(text="".join(text_parts), tool_calls=[],
                           usage={"input_tokens": 1, "output_tokens": 1},
                           latency_ms=10)


def _gw(provider, **kw):
    """The REAL QA wiring: provider -> _GatewayProviderAdapter (which
    provides generate_stream) -> LLMGateway governance."""
    gw = build_gateway(provider, refresh=True)
    gw.max_retries = kw.get("retries", 0)
    if kw.get("timeout"):
        gw.timeout_s = kw["timeout"]
    return gw


def _run(chunks, **kw):
    reset_default_service()
    prov = StreamProvider(chunks, **kw)
    gw = _gw(prov)
    events = []

    def emit(t, d):
        events.append({"t": t, "d": d, "at": time.time()})
    ctx = run_qa_turn("重疾险的等待期是什么",
                      classify("重疾险的等待期是什么"),
                      gateway=gw, emit=emit)
    return ctx, events, prov


def _deltas(events):
    return [e for e in events if e["t"] == "agent_stream_delta"]


def test_t1_t2_t3_provider_gateway_qa_streaming():
    """Chunks arrive progressively; QA emits deltas DURING generation."""
    chunks = [S1[:10], S1[10:], S2[:8], S2[8:], S3[:12], S3[12:]]
    ctx, events, prov = _run(chunks)
    assert ctx["grounding_status"] == "grounded"
    ds = _deltas(events)
    assert len(ds) >= 3, "sentence-level deltas expected"
    joined = "".join(d["d"]["text"] for d in ds)
    assert "等待期为90天[E1]" in joined
    assert "退还保费[E1]" in joined
    assert prov.calls == 1


def test_t4_timing_first_delta_before_final():
    """THE core acceptance: T_first_delta < T_final."""
    chunks = [S1, S2, S3]
    t0 = time.time()
    ctx, events, _ = _run(chunks, delay=0.15)
    t_final = time.time() - t0
    ds = _deltas(events)
    assert ds, "deltas must exist"
    t_first = ds[0]["at"] - t0
    assert t_first < t_final - 0.2, (
        "first delta (%.2fs) must precede final (%.2fs)" % (t_first, t_final))


def test_t5_no_fake_chunking_deltas_are_sentence_segments():
    """Provider emits AAA。BBB。CCC。 — consumer receives exactly those
    sentence segments (progressively), NOT post-hoc fixed-size slices."""
    a, b, c = "AAA。", "BBB。", "CCC。"
    ctx, events, _ = _run([a, b, c])
    texts = [d["d"]["text"] for d in _deltas(events)]
    assert texts == [a, b, c]  # sentence identity preserved, no re-chunk


def test_t6_t7_t8_citation_and_grounding_safety():
    """Uncited fact sentences are HELD (not streamed); final gate
    arbitrates. Valid cited sentences stream."""
    ctx, events, _ = _run([S1, UNCITED_TAIL, S2])
    streamed = "".join(d["d"]["text"] for d in _deltas(events))
    assert "等待期为90天" in streamed          # cited → streamed live
    assert "XX重疾险" not in streamed         # uncited → held
    # final gate on the full answer FAILS (uncited tail) → honest refusal
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "citation_gate_rejected"


def test_t9_final_gate_fail_honest_terminal():
    ctx, events, _ = _run([S1, UNCITED_TAIL])
    assert ctx["failure_reason"] == "citation_gate_rejected"
    streamed = "".join(d["d"]["text"] for d in _deltas(events))
    assert "XX重疾险" not in streamed  # held segment never streamed


def test_t10_provider_failure_no_deltas_honest():
    ctx, events, _ = _run([S1], fail_with="provider down")
    assert ctx["failure_reason"] == "llm_unavailable"
    assert _deltas(events) == []


def test_t11_hygiene_split_id_across_chunks():
    """'ART-' + '009' reassembled in the sentence buffer → sanitized."""
    poisoned = "见 ART-"          # chunk 1
    rest = "009。等待期为90天[E1]。"  # chunk 2 completes the id + sentence
    ctx, events, _ = _run([poisoned, rest])
    blob = "".join(d["d"]["text"] for d in _deltas(events))
    assert "ART-009" not in blob and "ART-" not in blob
    assert ctx["grounding_status"] in ("grounded", "refused")


def test_t12_reasoning_never_forwarded():
    ctx, events, _ = _run([S1, S2, S3])
    blob = "".join(d["d"]["text"] for d in _deltas(events))
    assert "内部思考" not in blob
    for d in _deltas(events):
        assert set(d["d"]) == {"kind", "text"}
        assert d["d"]["kind"] == "content"


def test_full_answer_convergence():
    """On final-gate PASS the residual flush completes the stream:
    joined deltas == sanitized(full answer)."""
    ctx, events, _ = _run([S1, S2, S3])
    assert ctx["grounding_status"] == "grounded"
    joined = "".join(d["d"]["text"] for d in _deltas(events))
    assert joined.replace(" ", "") == ctx["answer"].replace(" ", "")


def test_non_streaming_provider_fallback_still_governed():
    """A provider without stream_generate falls back to one-shot under
    the same watchdog — governance identical, deltas single-segment."""
    class OneShot:
        name = "oneshot"
        model = "m"

        def generate(self, messages, tools):
            from runtime.agent.model import LLMResponse
            return LLMResponse(text=GOOD, tool_calls=[],
                               usage={}, latency_ms=5)

    reset_default_service()
    gw = _gw(OneShot())
    events = []
    ctx = run_qa_turn("重疾险的等待期是什么",
                      classify("重疾险的等待期是什么"),
                      gateway=gw, emit=lambda t, d: events.append((t, d)))
    assert ctx["grounding_status"] == "grounded"
    ds = [d for (t, d) in events if t == "agent_stream_delta"]
    assert ds  # residual flush emits the validated content
    assert "等待期为90天" in "".join(d["text"] for d in ds)
