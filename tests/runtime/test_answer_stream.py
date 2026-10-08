"""28.K.29-A answer_stream tests — incremental agent_decide message
extraction from raw tool-args fragments (JSON-aware, truncation-safe)."""
from __future__ import annotations

import json

from runtime.agent.answer_stream import scan_decide, visible_message


def test_complete_finish_args():
    raw = json.dumps({"action": "finish",
                      "message": "我建议先配置百万医疗险。",
                      "reason": "summary"}, ensure_ascii=False)
    action, msg_raw = scan_decide(raw)
    assert action == "finish"
    assert visible_message(msg_raw) == "我建议先配置百万医疗险。"


def test_incremental_fragments_converge():
    """The streaming case: arguments arrive in arbitrary small chunks —
    every prefix must extract a consistent partial message."""
    full = json.dumps({"action": "ask_user",
                       "message": "请问你的预算大概是多少？",
                       "required_fields": ["budget"]}, ensure_ascii=False)
    prev_visible = ""
    for cut in range(1, len(full) + 1):
        action, msg_raw = scan_decide(full[:cut])
        visible = visible_message(msg_raw)
        # monotonic growth (prefix-stable) once anything is visible
        if len(visible) >= len(prev_visible):
            assert visible.startswith(prev_visible)
        prev_visible = max(prev_visible, visible, key=len)
    assert prev_visible == "请问你的预算大概是多少？"


def test_action_gate_semantics():
    """call_tool decisions carry no user-facing message — the consumer
    gates on action; the scanner must still resolve action reliably,
    even when message text contains the literal word message."""
    raw = json.dumps({"action": "call_tool", "tool": "knowledge_search",
                      "reason": "the message field is absent here",
                      "arguments": {"query": "x"}}, ensure_ascii=False)
    action, msg_raw = scan_decide(raw)
    assert action == "call_tool"
    assert msg_raw == ""


def test_message_key_inside_another_string_not_mistaken():
    raw = json.dumps({"action": "finish",
                      "reason": "用户提到了\"message\"这个关键词",
                      "message": "真正要展示的回答"}, ensure_ascii=False)
    action, msg_raw = scan_decide(raw)
    assert action == "finish"
    assert visible_message(msg_raw) == "真正要展示的回答"


def test_escapes_and_truncation():
    raw = '{"action": "finish", "message": "第一行\\n第二行 \\"引号\\" 结束"}'
    action, msg_raw = scan_decide(raw)
    assert action == "finish"
    assert visible_message(msg_raw) == '第一行\n第二行 "引号" 结束'
    # truncated right after a lone backslash -> cut before it
    partial = raw[:raw.index("\\n") + 1]
    _, m2 = scan_decide(partial)
    assert visible_message(m2) == "第一行"
    # partial \uXXXX tail is held back
    partial_u = '{"action":"finish","message":"\\u4e2d\\u56"}'
    _, m3 = scan_decide(partial_u)
    assert visible_message(m3) == "中"
    # complete unicode escape decodes
    full_u = '{"action":"finish","message":"\\u4e2d\\u56fd"}'
    _, m4 = scan_decide(full_u)
    assert visible_message(m4) == "中国"


def test_message_before_action_order_independent():
    raw = json.dumps({"message": "顺序颠倒也流式",
                      "action": "finish"}, ensure_ascii=False)
    # the consumer HOLDS the message until action resolves; the scanner
    # reports both independently
    half = raw[:raw.index('"action"')]
    action, msg_raw = scan_decide(half)
    assert action is None
    assert visible_message(msg_raw) == "顺序颠倒也流式"
    action, _ = scan_decide(raw)
    assert action == "finish"


def test_empty_and_garbage_safe():
    assert scan_decide("") == (None, "")
    assert scan_decide("{") == (None, "")
    assert scan_decide("not json at all") == (None, "")
    action, msg = scan_decide('{"action":"finish","message":"')
    assert action == "finish" and msg == ""
