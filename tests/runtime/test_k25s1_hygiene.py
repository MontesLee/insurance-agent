"""Phase 28.K.25-S1 — Consumer content hygiene tests (ART-xxx et al.)."""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from runtime.consumer_hygiene import (  # noqa: E402
    sanitize_consumer_text, strip_internal_ids_for_llm)


def test_t2_t4_t5_sanitizer_variants_and_multiples():
    assert "ART-009" not in sanitize_consumer_text("请查看 ART-009。")
    out = sanitize_consumer_text("ART-001 ART-009 ART-123 已生成。")
    for bad in ("ART-001", "ART-009", "ART-123"):
        assert bad not in out
    assert "已生成" in out
    assert "ART-ABC" not in sanitize_consumer_text("ref: ART-ABC done")
    assert "EVAL-007" not in sanitize_consumer_text("EVAL-007 未过")
    assert "run_0e708c9397844389" not in sanitize_consumer_text(
        "见 run_0e708c9397844389")
    assert "chat_ba7a470648c94be3" not in sanitize_consumer_text(
        "chat_ba7a470648c94be3 中")


def test_t2b_parenthetical_collapses_sentence_stays_natural():
    out = sanitize_consumer_text("你的分析结果见 ART-009，已生成。")
    assert "ART" not in out and "，已生成。" in out and "见 ，" not in out
    out2 = sanitize_consumer_text("正式报告已更新生成（ART-009）。")
    assert "ART" not in out2 and "（）" not in out2
    assert "正式报告已更新生成" in out2


def test_t6_business_text_untouched():
    safe = ("保额50万元 P001 产品 2026-01-01 生效 SMART-1条款 "
            "等待期90天 版本v1.0 编号HB2026-012 QR-2级 医院3000")
    assert sanitize_consumer_text(safe) == safe


def test_t1_source_hygiene_llm_projection():
    tool = {"status": "ok", "summary": "solution completed",
            "artifact_id": "ART-005", "artifact_type": "solution-plan",
            "eval_id": "EVAL-003", "run_id": "run_abcdef1234567890",
            "data": {"nested": {"artifact_id": "ART-006", "x": 1}}}
    out = strip_internal_ids_for_llm(tool)
    blob = str(out)
    for bad in ("ART-005", "ART-006", "EVAL-003", "run_abcdef"):
        assert bad not in blob, bad
    assert out["status"] == "ok" and out["data"]["nested"]["x"] == 1
    # original untouched
    assert tool["artifact_id"] == "ART-005"


def test_t3_streaming_chunks_sanitized_before_split():
    """K.22: the FULL validated answer is sanitized BEFORE 48-char
    chunking — an id spanning a chunk boundary cannot survive."""
    from runtime.grounding.loop import generate_grounded
    from runtime.llm.gateway import LLMGateway
    from runtime.llm.mock import MockLLMProvider
    from knowledge.service import reset_default_service
    from runtime.intent.classifier import classify
    from runtime.qa_agent import run_qa_turn
    reset_default_service()
    answer = ("重大疾病保险常见等待期为90天[E1]。见 ART-009。"
              "等待期内确诊一般仅退还保费[E1]。")
    gw = LLMGateway(MockLLMProvider(content=answer), max_retries=0)
    chunks = []

    def emit(t, d):
        chunks.append(d.get("text", ""))
    ctx = run_qa_turn("重疾险的等待期是什么",
                      classify("重疾险的等待期是什么"),
                      gateway=gw, emit=emit)
    assert ctx["grounding_status"] == "grounded"
    joined = "".join(chunks)
    assert "ART-009" not in joined
    # sentence-level id replaced naturally, rest intact
    assert "等待期为90天[E1]" in joined


def test_t9_internal_linkage_untouched():
    """The sanitizer never mutates internal structures — registry ids,
    tool_history and event payloads keep real IDs."""
    tool = {"artifact_id": "ART-009"}
    sanitize_consumer_text("x ART-009 y")
    assert tool["artifact_id"] == "ART-009"


def test_t10_finish_run_sanitizes_chat_message():
    from _common import make_client
    client, mgr, _ = make_client()
    with mgr._lock:
        mgr._runs["run_h"] = {"run_id": "run_h", "status": "running"}
    mgr.chats.get_or_create("chat_h")
    mgr._finish_run("run_h", "c", "run_completed", "completed",
                    result_status="COMPLETED", message="done",
                    chat_id="chat_h",
                    chat_message="报告（ART-009）已生成，见 run_h。")
    msg = mgr.chats.view("chat_h")["messages"][-1]
    assert "ART-009" not in msg["content"]
    assert "报告" in msg["content"] and "已生成" in msg["content"]
