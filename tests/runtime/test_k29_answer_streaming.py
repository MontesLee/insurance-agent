"""28.K.29-A — planning-path user-visible answer streaming.

The final answer (and ask_user clarify) streams as agent_decide's
`message` tool-argument fragments: real provider deltas, JSON-aware
incremental extraction, answer-channel routing. Raw tool args of ANY
other tool never surface; reasoning deltas keep their kind; a retry
resets the partial stream.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime.agent import agent as agent_mod  # noqa: E402
from runtime.agent.agent import run_agent_turn  # noqa: E402
from runtime.agent.model import LLMResponse, ToolCall  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402
from runtime.orchestrator import load_workflow  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.agent.tools import ToolContext  # noqa: E402

SECTIONS = []


try:                       # hermetic obs: never append test records to
    import runtime.obs as _obs_mod          # the real tmp/obs/agent.jsonl
    from runtime.obs.log import JsonlLogger as _JL
    import pytest as _pytest

    @_pytest.fixture(autouse=True)
    def _null_obs_log():
        _obs_mod.set_default_logger(_JL(None))
        yield
        _obs_mod.set_default_logger(None)
except ImportError:        # script mode: run_sections drives directly
    pass


def section(fn):
    SECTIONS.append(fn)
    return fn


WF = load_workflow()


class ScriptedStreamProvider:
    """Provider whose stream_generate replays scripted delta lists, one
    per LLM call (mirrors the GLM adapter's delta contract)."""

    name = "scripted"
    model = "scripted-1"

    def __init__(self, calls):
        self._calls = list(calls)

    def generate(self, messages, tools):  # non-stream fallback: unused
        raise AssertionError("streaming provider must not fall back")

    def stream_generate(self, messages, tools):
        deltas = self._calls.pop(0)

        def gen():
            for d in deltas:
                if isinstance(d, BaseException):
                    raise d
                yield d
            # assembled response from the tool-call fragments
            calls = {}
            for d in deltas:
                if d.get("kind") == "tool_args" and d.get("tool"):
                    slot = calls.setdefault(d["tool"], {"id": "c1",
                                                        "args": ""})
                    slot["args"] += d.get("text") or ""
            parsed = [ToolCall(id=v["id"], name=k,
                               arguments=json.loads(v["args"] or "{}"))
                      for k, v in calls.items()]
            return LLMResponse(text=None, tool_calls=parsed,
                               usage={"input_tokens": 1,
                                      "output_tokens": 1},
                               latency_ms=1.0)

        return gen()


def _args_fragments(args: dict, chunk: int = 17):
    """Split a JSON args string into tool_args delta fragments the way
    the provider adapter forwards them (tool name on every fragment)."""
    raw = json.dumps(args, ensure_ascii=False)
    return [{"type": "delta", "kind": "tool_args",
             "tool": "agent_decide", "text": raw[i:i + chunk]}
            for i in range(0, len(raw), chunk)]


def _call_gen(provider):
    """Drive ONE _generate_with_retry call, capturing emitted deltas."""
    events = []

    def emit(event_type, data):
        events.append({"event_type": event_type, "data": data})

    st = AgentState("run_k29", "agentcase-k29", "chat_k29")
    resp = agent_mod._generate_with_retry(provider, [], [], st, emit)
    return resp, events


def _answer_text(events):
    """Consumer-side accumulation WITH reset semantics (mirrors the
    reducer): a reset marker discards the partial answer before it."""
    buf = ""
    for e in events:
        if e["event_type"] != "agent_stream_delta":
            continue
        d = e["data"]
        if d.get("channel") != "answer":
            continue
        if d.get("reset"):
            buf = ""
            continue
        buf += d.get("text") or ""
    return buf


def _kinds(events):
    return [(e["data"].get("kind"), e["data"].get("channel"))
            for e in events if e["event_type"] == "agent_stream_delta"]


@section
def test_finish_message_streams_on_answer_channel(c: Checks):
    msg = "我建议先配置百万医疗险，再补充定期寿险。"
    deltas = ([{"type": "delta", "kind": "reasoning", "text": "思考中…"},
               {"type": "delta", "kind": "reasoning", "text": "继续思考"}]
              + _args_fragments({"action": "finish", "message": msg,
                                 "reason": "done"}))
    resp, events = _call_gen(ScriptedStreamProvider([deltas]))
    c.chk("response message intact",
          resp.tool_calls[0].arguments["message"] == msg)
    c.chk("streamed answer == message", _answer_text(events) == msg)
    kinds = _kinds(events)
    c.chk("reasoning keeps its kind/channel",
          ("reasoning", None) in kinds)
    c.chk("only reasoning + content/answer deltas emitted",
          all(k in (("reasoning", None), ("content", "answer"))
              for k in kinds))
    c.chk("raw tool_args never cross as a delta kind",
          not any(k[0] == "tool_args" for k in kinds))


@section
def test_other_tool_arguments_never_surface(c: Checks):
    deltas = ([{"type": "delta", "kind": "reasoning", "text": "查资料"}]
              + _args_fragments({"action": "call_tool",
                                 "tool": "knowledge_search",
                                 "message": "内部叙述不应外发",
                                 "arguments": {"query": "百万医疗 免赔额"}},
                                chunk=11))
    _, events = _call_gen(ScriptedStreamProvider([deltas]))
    c.chk("call_tool decision: no answer stream",
          _answer_text(events) == "")
    c.chk("no answer-channel delta at all",
          not any(e["data"].get("channel") == "answer" for e in events))
    raw = json.dumps(events, ensure_ascii=False)
    c.chk("raw query args never in events", "百万医疗 免赔额" not in raw)
    c.chk("call_tool incidental message never in events",
          "内部叙述不应外发" not in raw)


@section
def test_partial_fragments_and_escapes(c: Checks):
    msg = "第一行\n第二行 \"引号\" 中"
    deltas = _args_fragments({"action": "finish", "message": msg},
                             chunk=7)
    _, events = _call_gen(ScriptedStreamProvider([deltas]))
    c.chk("escapes decoded across fragment boundaries",
          _answer_text(events) == msg)
    # finish-only gate: an ask_user attempt must NOT stream (its schema
    # may be rejected after partial emission — K.29 benchmark finding)
    ask = _args_fragments({"action": "ask_user", "message": "追问？",
                           "required_fields": ["budget"]}, chunk=5)
    _, ev2 = _call_gen(ScriptedStreamProvider([ask]))
    c.chk("ask_user does not stream (finish-only gate)",
          _answer_text(ev2) == "")


@section
def test_retry_emits_reset_then_new_answer(c: Checks):
    good = _args_fragments({"action": "finish",
                            "message": "第二次的完整回答。"})
    bad = ([{"type": "delta", "kind": "reasoning", "text": "…"}]
           + _args_fragments({"action": "finish",
                              "message": "第一次的部分回答"})[:-1]
           + [RuntimeError("provider transient failure")])
    _, events = _call_gen(ScriptedStreamProvider([bad, good]))
    resets = [e for e in events
              if e["event_type"] == "agent_stream_delta"
              and e["data"].get("reset") is True]
    c.chk("exactly one reset marker", len(resets) == 1)
    c.chk("streamed text converges to the winning attempt",
          _answer_text(events) == "第二次的完整回答。")


@section
def test_answer_emission_capped_at_1200(c: Checks):
    msg = "长" * 3000
    deltas = _args_fragments({"action": "finish", "message": msg},
                             chunk=100)
    resp, events = _call_gen(ScriptedStreamProvider([deltas]))
    c.chk("streamed emission capped (mirrors _clip 1200)",
          len(_answer_text(events)) == 1200)
    c.chk("assembled response keeps the full message",
          len(resp.tool_calls[0].arguments["message"]) == 3000)


@section
def test_full_turn_finish_streams_and_converges(c: Checks):
    """run_agent_turn integration: one tool step then finish — the
    streamed answer text equals the delivered outcome message."""
    msg = "这是最终回答，会流式出现。"
    provider = ScriptedStreamProvider([
        [{"type": "delta", "kind": "reasoning", "text": "分析"}]
        + _args_fragments({"action": "call_tool",
                           "tool": "record_client_profile",
                           "reason": "记录",
                           "arguments": {"family_profile":
                                         {"age": {"value": 35}}}}),
        [{"type": "delta", "kind": "reasoning", "text": "总结"}]
        + _args_fragments({"action": "finish", "message": msg}),
    ])
    events = []

    def emit(event_type, data):
        events.append({"event_type": event_type, "data": data})

    state = cs.new_case_state("agentcase-k29i", WF)
    tk.init_tasks(state, WF)
    ctx = ToolContext(state, WF, "run_k29i", persist=lambda: None)
    st = AgentState("run_k29i", "agentcase-k29i", "chat_k29i")
    outcome = run_agent_turn(provider, st, "帮我规划", ctx, emit)
    c.chk("turn completes", outcome.status == "completed")
    c.chk("delivered message", outcome.message == msg)
    c.chk("streamed text == delivered message (convergence)",
          _answer_text(events) == msg)


@section
def test_no_stream_provider_no_fake_streaming(c: Checks):
    """A provider without stream_generate keeps the pre-K.29 behaviour —
    no answer deltas are invented (spec §9)."""

    class Plain:
        name = "plain"
        model = "p1"

        def generate(self, messages, tools):
            return LLMResponse(text="直接文本回答", tool_calls=[],
                               usage={}, latency_ms=1.0)

    _, events = _call_gen(Plain())
    c.chk("no answer-channel deltas",
          _answer_text(events) == "")
    c.chk("no channel deltas at all",
          not any(e["data"].get("channel") == "answer" for e in events))


def main():
    return run_sections(SECTIONS, "webui_test_k29_answer_streaming.txt",
                        "K.29-A ANSWER STREAMING")


if __name__ == "__main__":
    sys.exit(main())


@section
def test_k30_observation_record_per_llm_call(c: Checks):
    """28.K.30: every agent-loop LLM call writes an agent.llm_call obs
    record (model/step/duration/tokens/tool names) — pure observation."""
    import runtime.obs as obs
    from runtime.obs.log import JsonlLogger

    sink: list = []

    class _Capture(JsonlLogger):
        def emit(self, *a, **kw):
            rec = {"event": a[0] if a else kw.get("event"),
                   **{k: v for k, v in kw.items() if k != "event"}}
            sink.append(rec)
            return rec

    obs.set_default_logger(_Capture(None))
    try:
        msg = "观察记录测试。"
        provider = ScriptedStreamProvider([
            _args_fragments({"action": "finish", "message": msg})])
        events = []
        state = cs.new_case_state("agentcase-k30", WF)
        tk.init_tasks(state, WF)
        ctx = ToolContext(state, WF, "run_k30", persist=lambda: None)
        st = AgentState("run_k30", "agentcase-k30", "chat_k30")
        outcome = run_agent_turn(provider, st, "测试", ctx,
                                 lambda t, d: events.append((t, d)))
        recs = [r for r in sink if r.get("event") == "agent.llm_call"]
        c.chk("one obs record per LLM call", len(recs) == 1)
        if recs:
            r = recs[0]
            c.chk("model recorded", r.get("model") == "scripted-1")
            c.chk("step recorded", r.get("step") == 1)
            c.chk("tool call names recorded",
                  r.get("tool_calls") == ["agent_decide"])
            c.chk("run_id recorded", r.get("run_id") == "run_k30")
        c.chk("turn still completes", outcome.message == msg)
    finally:
        obs.set_default_logger(None)   # autouse fixture resets after
