"""Intent Routing tests (agent intent classification in agent_decide).

Validates that the agent's FIRST decision per turn carries the right `intent`
and that the corresponding tool routing matches §13 of the spec. FakeLLM only.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_agent_intent.py`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime.agent import FakeLLMProvider, run_agent_turn  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402
from runtime.agent.tools import ToolContext  # noqa: E402

SECTIONS = []
WF = orch.load_workflow()

PROFILE = {"family_profile": {"age": {"value": 4}},
           "financial_profile": {"budget": {"value": "1万/年"}},
           "existing_protection": {"existing_insurance": {"value": "无"}}}


def section(fn):
    SECTIONS.append(fn)
    return fn


def drive(script, user_text):
    """One turn; returns (outcome, agent_state, case_state, events)."""
    events = []

    def emit(event_type, data):
        events.append({"event_type": event_type, "data": data})

    state = cs.new_case_state("agentcase-intent", WF)
    tk.init_tasks(state, WF)
    ctx = ToolContext(state, WF, "run_intent", persist=lambda: None)
    a = AgentState("run_intent", "agentcase-intent", "chat_intent")
    p = FakeLLMProvider(script)
    out = run_agent_turn(p, a, user_text, ctx, emit)
    return out, a, state, events


def first_intent(events):
    for e in events:
        if e["event_type"] == "agent_decision" and e["data"].get("intent"):
            return e["data"]["intent"]
    return None


def tools_called(events):
    return [e["data"].get("tool") or e.get("skill")
            for e in events if e["event_type"] in ("tool_started", "tool_completed")]


def _d(intent, action, **kw):
    """Helper: build an agent_decide script item."""
    args = {"intent": intent, "action": action}
    args.update(kw)
    return ("agent_decide", args)


@section
def test_1_general_knowledge(c: Checks):
    out, a, state, events = drive([
        ("knowledge_search", {"query": "什么是百万医疗险"}),
        _d("GENERAL_KNOWLEDGE", "finish",
           message="百万医疗险是报销住院费用的高额医疗保险…"),
    ], "什么是百万医疗险？")
    c.chk("T1 intent=GENERAL_KNOWLEDGE", first_intent(events) == "GENERAL_KNOWLEDGE",
          first_intent(events))
    tools = tools_called(events)
    c.chk("T1 only knowledge_search called", set(tools) <= {"knowledge_search"}, tools)
    c.chk("T1 no client-intake or pipeline tools",
          not any(t in ("record_client_profile", "coverage_gap_analysis",
                        "recommendation", "report_generation") for t in tools), tools)
    _t1_arts = [a for a in (state.get("artifacts") or {}) if a != "knowledge-evidence"]
    c.chk("T1 no ANALYSIS artifacts (knowledge-evidence acceptable)",
          len(_t1_arts) == 0, sorted((state.get("artifacts") or {}).keys()))


@section
def test_2_general_guidance(c: Checks):
    out, a, state, events = drive([
        _d("GENERAL_GUIDANCE", "call_tool", tool="knowledge_search",
           arguments={"query": "儿童重疾险 配置 考虑因素"},
           reason="通用选择思路问题，非个性化咨询"),
        _d("GENERAL_GUIDANCE", "finish",
           message="给孩子配置重疾险前，建议考虑：1) 想解决什么风险 2) 已有保障 "
                   "3) 孩子健康与投保条件 4) 需要多少保额 5) 家庭预算 6) 保障期限 "
                   "7) 疾病定义 8) 产品差异。如果你想进一步做个性化规划，我可以根据"
                   "孩子的具体情况帮你分析。"),
    ], "给孩子配置重疾险前，我应该先考虑什么？")
    c.chk("T2 intent=GENERAL_GUIDANCE", first_intent(events) == "GENERAL_GUIDANCE",
          first_intent(events))
    tools = tools_called(events)
    c.chk("T2 knowledge_search allowed", "knowledge_search" in tools, tools)
    c.chk("T2 NO record_client_profile / intake",
          "record_client_profile" not in tools, tools)
    _t2_arts = [a for a in (state.get("artifacts") or {}) if a != "knowledge-evidence"]
    c.chk("T2 no ANALYSIS artifacts", len(_t2_arts) == 0,
          sorted((state.get("artifacts") or {}).keys()))
    c.chk("T2 answer covers key factors + soft CTA",
          "保额" in out.message or "预算" in out.message,
          out.message[:60])


@section
def test_3_client_advisory(c: Checks):
    out, a, state, events = drive([
        _d("CLIENT_ADVISORY", "call_tool", tool="record_client_profile",
           arguments=PROFILE, reason="个性化规划请求"),
        _d("CLIENT_ADVISORY", "ask_user",
           message="还想了解孩子健康情况和已有保险。",
           required_fields=["健康情况", "已有保险"],
           reason="insufficient_client_information"),
    ], "我想给4岁的孩子买重疾险，你帮我规划一下。")
    c.chk("T3 intent=CLIENT_ADVISORY", first_intent(events) == "CLIENT_ADVISORY",
          first_intent(events))
    tools = tools_called(events)
    c.chk("T3 record_client_profile called", "record_client_profile" in tools, tools)
    c.chk("T3 client-profile artifact stored",
          "client-profile" in (state.get("artifacts") or {}))


@section
def test_4_client_advisory_with_facts(c: Checks):
    out, a, state, events = drive([
        _d("CLIENT_ADVISORY", "call_tool", tool="record_client_profile",
           arguments=PROFILE),
        _d("CLIENT_ADVISORY", "call_tool", tool="record_requirement_analysis",
           arguments={"requirements": [
               {"requirement_id": "R", "requirement_type": "critical_illness",
                "summary": "少儿重疾保障", "priority": "P1_HIGH"}]}),
        _d("CLIENT_ADVISORY", "call_tool", tool="record_risk_assessment",
           arguments={"risks": [
               {"risk_id": "R2", "risk_category": "R2_critical_illness",
                "risk_name": "少儿重疾", "priority": "P1_HIGH"}]}),
        ("coverage_gap_analysis", {}), ("solution", {}),
        ("product_candidate_provider", {}), ("recommendation", {}),
        ("report_generation", {}),
        _d("CLIENT_ADVISORY", "finish", message="分析完成，报告已生成。"),
    ], "我家孩子4岁，身体健康，预算每年1万元，帮我看看重疾险怎么买。")
    c.chk("T4 intent=CLIENT_ADVISORY", first_intent(events) == "CLIENT_ADVISORY")
    tools = tools_called(events)
    c.chk("T4 full chain ran", "record_client_profile" in tools
          and "report_generation" in tools, tools)
    c.chk("T4 9 artifacts", len(state.get("artifacts") or {}) == 9)


@section
def test_5_knowledge_vs_pipeline(c: Checks):
    out, a, state, events = drive([
        ("knowledge_search", {"query": "重疾险 百万医疗险 区别"}),
        _d("GENERAL_KNOWLEDGE", "finish",
           message="重疾险定额给付，百万医疗险报销住院费用…"),
    ], "重疾险和百万医疗险有什么区别？")
    c.chk("T5 intent=GENERAL_KNOWLEDGE", first_intent(events) == "GENERAL_KNOWLEDGE")
    tools = tools_called(events)
    c.chk("T5 NO pipeline tools",
          not any(t in ("record_client_profile", "coverage_gap_analysis",
                        "recommendation") for t in tools), tools)
    _t5_arts = [a for a in (state.get("artifacts") or {}) if a != "knowledge-evidence"]
    c.chk("T5 no ANALYSIS artifacts", len(_t5_arts) == 0,
          sorted((state.get("artifacts") or {}).keys()))


@section
def test_6_product_lookup(c: Checks):
    out, a, state, events = drive([
        ("check_catalog_product", {"query": "P001"}),
        _d("PRODUCT_LOOKUP", "finish",
           message="P001是demo-百万医疗险A（标准版）…"),
    ], "P001的免赔额是多少？")
    c.chk("T6 intent=PRODUCT_LOOKUP", first_intent(events) == "PRODUCT_LOOKUP")
    tools = tools_called(events)
    c.chk("T6 check_catalog_product called", "check_catalog_product" in tools, tools)
    c.chk("T6 no client profile demanded",
          "record_client_profile" not in tools, tools)
    c.chk("T6 no artifacts", not state.get("artifacts"))


@section
def test_7_personalized_question(c: Checks):
    out, a, state, events = drive([
        _d("CLIENT_ADVISORY", "ask_user",
           message="要根据你家情况算保额，我需要了解：1) 家庭年收入 2) 房贷/负债 "
                   "3) 已有重疾保障 4) 孩子数量。方便告诉我吗？",
           required_fields=["家庭年收入", "负债", "已有重疾保障"],
           reason="个性化保额决策问题，需要客户事实"),
    ], "我家这种情况应该买多少重疾险？")
    c.chk("T7 intent=CLIENT_ADVISORY (personal decision question)",
          first_intent(events) == "CLIENT_ADVISORY", first_intent(events))
    c.chk("T7 ask_user for SPECIFIC items (not 6-item generic form)",
          out.action == "ask_user" and len(out.required_fields) <= 4,
          out.required_fields)


@section
def test_8_ambiguous_one_clarification(c: Checks):
    out, a, state, events = drive([
        _d("GENERAL_GUIDANCE", "ask_user",
           message="你是想先了解一般的选择思路，还是希望我根据你家孩子的具体情况帮你做规划？",
           required_fields=["clarify_intent"],
           reason="ambiguous_general_vs_personal"),
    ], "怎么给孩子买重疾险？")
    c.chk("T8 ambiguous → ONE lightweight clarification (not 6-item form)",
          out.action == "ask_user"
          and ("一般" in out.message or "规划" in out.message)
          and len(out.required_fields) <= 2,
          (out.action, out.required_fields, out.message[:50]))
    c.chk("T8 no tools executed during clarification",
          not tools_called(events), tools_called(events))


@section
def test_intent_flows_through_events_and_state(c: Checks):
    out, a, state, events = drive([
        _d("GENERAL_GUIDANCE", "finish", message="通用回答。"),
    ], "买重疾险主要看什么？")
    decisions = [e for e in events if e["event_type"] == "agent_decision"]
    c.chk("events: intent recorded in every agent_decision",
          all(d["data"].get("intent") for d in decisions),
          [d["data"] for d in decisions])
    c.chk("state: agent_state.intent set", a.intent == "GENERAL_GUIDANCE", a.intent)
    blob = str(events)
    c.chk("events: no CoT / no key material",
          all(k not in blob.lower() for k in ("思考过程", "我猜测", "api_key")))


def main():
    return run_sections(SECTIONS, "webui_test_agent_intent_log.txt", "RUNTIME AGENT INTENT")


if __name__ == "__main__":
    sys.exit(main())
