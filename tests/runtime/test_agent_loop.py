"""Phase 2.6 — Agent Loop tests (runtime/agent/agent.py), FakeLLM only.

Covers the spec's real-agent cases and failure disciplines:
  A/B: information scarcity ⇒ ask_user (NEVER a report);
  C:   full chain through the EXISTING deterministic engines + evals;
  D:   knowledge Q&A via knowledge_search then finish;
  E:   premature product asks refused by tool preconditions;
  §28: input "test" must end waiting_user with NO report artifact;
  §34: malformed structured output retries are bounded, then fail closed;
  §35: step limit ⇒ needs_review with a clear event;
  §20/§44: eval failure after repair stops the agent (fail closed);
  §23/§42: events contain actions/summaries only — no CoT, no key material.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_agent_loop.py`.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime.state import case_state as cs  # noqa: E402
from runtime import tasks as tk  # noqa: E402
from runtime import trace as tr  # noqa: E402
from runtime.agent import FakeLLMProvider, run_agent_turn, MAX_AGENT_STEPS  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402
from runtime.agent.tools import ToolContext  # noqa: E402
from runtime.events import TraceEventAdapter  # noqa: E402

SECTIONS = []

def section(fn):
    SECTIONS.append(fn)
    return fn
WF = orch.load_workflow()

PROFILE = {
    "family_profile": {"age": {"value": 4}},
    "financial_profile": {"annual_income": {"value": "30万"}, "budget": {"value": "1万/年"}},
    "existing_protection": {"existing_insurance": {"value": "无"}},
}
ASK = ("agent_decide", {"action": "ask_user", "reason": "insufficient_client_information",
                        "required_fields": ["age", "health", "goal", "budget"],
                        "message": "还需要了解：1) 年龄 2) 健康情况 3) 保障目标 4) 预算"})


def drive(script, user_text):
    """Drive one turn the way the SERVER does: agent events direct + a trace tap
    converting tool-driven tr.emit records (stage/eval/artifact/repair) to events."""
    events = []

    def emit(event_type, data):
        events.append({"event_type": event_type, "data": data})

    state = cs.new_case_state("agentcase-loop", WF)
    tk.init_tasks(state, WF)
    run_dir = os.path.join(REPO, "tmp", "agent-loop-test")
    os.makedirs(run_dir, exist_ok=True)

    def persist():
        from runtime import checkpoint as cp
        cp.save(state, run_dir, None)   # real checkpoint (like the server worker)

    ctx = ToolContext(state, WF, "run_loop", persist=persist)
    agent_state = AgentState("run_loop", "agentcase-loop", "chat_loop")

    adapter = TraceEventAdapter()

    def tap(rec):
        ev = adapter.to_event(rec, "run_loop", len(events) + 1)
        if ev is not None:
            events.append(ev.to_dict())

    remove_tap = tr.add_sink(tap)
    provider = FakeLLMProvider(script)
    try:
        outcome = run_agent_turn(provider, agent_state, user_text, ctx, emit)
    finally:
        remove_tap()
    return outcome, agent_state, state, events


def tool(name, args=None):
    return ("agent_decide", {"action": "call_tool", "tool": name, "arguments": args or {}})


def no_report(state):
    return "insurance-report" not in (state.get("artifacts") or {})


@section
def test_case_a_test_input_asks_not_reports(c: Checks):
    out, a, state, events = drive([ASK], "test")
    c.chk("A('test'): outcome ask_user / waiting_user",
          out.action == "ask_user" and out.status == "waiting_user", (out.action, out.status))
    c.chk("A('test'): assistant asks a numbered clarification",
          "1" in out.message and "2" in out.message, out.message[:80])
    c.chk("A('test'): NO report, NO demo seeding, NO pipeline",
          no_report(state) and len(state.get("artifacts") or {}) == 0,
          sorted((state.get("artifacts") or {}).keys()))
    c.chk("A('test'): required fields recorded for follow-up",
          a.facts_asked[:4] == ["age", "health", "goal", "budget"], a.facts_asked)
    c.chk("A('test'): events are agent vocabulary only (no stage/eval lies)",
          {e["event_type"] for e in events} <= {"agent_step_started", "agent_decision"},
          {e["event_type"] for e in events})


@section
def test_case_b_simple_need_asks_for_core_fields(c: Checks):
    ask = ("agent_decide", {"action": "ask_user", "reason": "insufficient_information",
                            "required_fields": ["age", "health_status", "goal", "budget"],
                            "message": "需要先了解年龄、健康情况、想解决的问题和预算。"})
    out, _, state, _ = drive([ask], "我想给孩子买保险")
    c.chk("B: ask_user with age/health/goal/budget",
          out.status == "waiting_user"
          and all(f in out.required_fields for f in ("age", "health_status", "goal", "budget")))
    c.chk("B: no analysis ran", no_report(state) and not state.get("artifacts"))


@section
def test_case_c_full_real_chain(c: Checks):
    script = [
        tool("record_client_profile", PROFILE),
        tool("record_requirement_analysis", {"requirements": [
            {"requirement_id": "REQ-MED", "requirement_type": "medical",
             "summary": "大额住院医疗", "priority": "P1_HIGH"},
            {"requirement_id": "REQ-CI", "requirement_type": "critical_illness",
             "summary": "少儿重疾保障", "priority": "P1_HIGH"}]}),
        tool("record_risk_assessment", {"risks": [
            {"risk_id": "R1-001", "risk_category": "R1_medical",
             "risk_name": "住院医疗费用风险", "priority": "P1_HIGH"},
            {"risk_id": "R2-001", "risk_category": "R2_critical_illness",
             "risk_name": "少儿重疾治疗与康复支出", "priority": "P1_HIGH"}]}),
        ("coverage_gap_analysis", {}),
        ("solution", {}),
        ("product_candidate_provider", {}),
        ("recommendation", {}),
        ("report_generation", {}),
        ("agent_decide", {"action": "finish",
                          "message": "分析完成，报告已生成，可点击查看。"}),
    ]
    out, a, state, events = drive(script, "我想给4岁孩子买保险。身体健康，没有保险，预算1万，担心大病和住院。")
    c.chk("C: agent finishes naturally", out.action == "finish" and out.status == "completed",
          (out.action, out.status))
    arts = sorted((state.get("artifacts") or {}).keys())
    c.chk("C: all 9 canonical artifacts produced through real engines",
          len(arts) == 9 and "insurance-report" in arts, arts)
    evals = [e for e in state["evaluations"]]
    c.chk("C: existing eval engine judged every artifact",
          len(evals) >= 9 and all(e["status"] == "PASS" for e in evals),
          [e["status"] for e in evals])
    types = [e["event_type"] for e in events]
    for needed in ("agent_step_started", "agent_decision", "tool_started",
                   "tool_completed", "stage_started", "stage_completed",
                   "eval_started", "eval_passed", "artifact_created",
                   "checkpoint_created"):
        c.chk("C: event vocabulary covers %s" % needed, needed in types)
    c.chk("C: report content is the runtime's own artifact",
          "insurance-report" in state["artifacts"]
          and state["artifacts"]["insurance-report"].get("payload", {}).get("status") == "success")


@section
def test_case_d_knowledge_qa(c: Checks):
    script = [
        ("knowledge_search", {"query": "百万医疗险 重疾险 区别"}),
        ("agent_decide", {"action": "finish",
                          "message": "两者区别：医疗险报销住院费用，重疾险定额给付收入补偿（依据知识库证据）。"}),
    ]
    out, a, state, events = drive(script, "百万医疗险和重疾险有什么区别？")
    c.chk("D: knowledge_search tool called then natural finish",
          out.status == "completed" and a.tool_history[0]["tool"] == "knowledge_search")
    c.chk("D: Q&A turn runs NO analysis pipeline",
          no_report(state) and "client-profile" not in (state.get("artifacts") or {}))


@section
def test_case_e_premature_product_request_refused(c: Checks):
    # the LLM might try to jump straight to products — the TOOL must refuse
    state = cs.new_case_state("agentcase-e", WF)
    tk.init_tasks(state, WF)
    ctx = ToolContext(state, WF, "run_e", persist=lambda: None)
    out = build_registry()["recommendation"].execute({}, ctx)
    c.chk("E: recommendation tool refuses without ClientState/Requirement/Risk",
          out["status"] == "failed" and "prerequisite" in out["summary"], out["summary"])

    out2, _, state2, _ = drive([ASK], "根据我的情况推荐产品")
    c.chk("E: with no facts the agent asks instead of recommending",
          out2.status == "waiting_user" and no_report(state2))


@section
def test_malformed_output_bounded_retry(c: Checks):
    # two malformed decisions, then a valid ask_user — feedback loop recovers
    out, _, state, events = drive([
        "INVALID:{oops",
        ("agent_decide", {"action": "fly_to_moon"}),
        ASK,
    ], "test")
    c.chk("retry: recovers after malformed/invalid decisions",
          out.status == "waiting_user" and out.action == "ask_user", out.action)
    c.chk("retry: no side effects during malformed turns", no_report(state))

    # decision exhaustion is impossible (loop continues) but step limit bites:
    script = [("agent_decide", {"action": "call_tool", "tool": "no_such_tool",
                                "arguments": {}})] * 20
    out2, _, _, ev2 = drive(script, "test")
    c.chk("retry: endless invalid decisions stop at step limit",
          out2.status == "needs_review" and "上限" in out2.message, out2.status)


@section
def test_step_limit(c: Checks):
    script = [("knowledge_search", {"query": "x"})] * (MAX_AGENT_STEPS + 3)
    out, a, _, events = drive(script, "长问题")
    c.chk("steps: hard cap at %d" % MAX_AGENT_STEPS,
          out.status == "needs_review" and a.turn == MAX_AGENT_STEPS, a.turn)
    decisions = [e for e in events if e["event_type"] == "agent_decision"]
    c.chk("steps: explicit stop decision recorded",
          any(d["data"].get("reason") == "max_agent_steps_exceeded" for d in decisions))


@section
def test_provider_failure_fails_closed(c: Checks):
    out, _, state, _ = drive([RuntimeError("provider down"), RuntimeError("still down"),
                              RuntimeError("nope")], "test")
    c.chk("provider error: needs_review, honest message",
          out.status == "needs_review" and "转人工" in out.message, out.status)
    c.chk("provider error: nothing executed", no_report(state) and not state.get("artifacts"))


@section
def test_eval_failure_stops_agent(c: Checks):
    import runtime.orchestrator as orch_mod

    original = orch_mod._invoke_python_stage

    def exploding(state, stage, input_override=None):
        if stage["id"] == "coverage-gap-analysis":
            raise RuntimeError("engine exploded")
        return original(state, stage, input_override=input_override)

    orch_mod._invoke_python_stage = exploding
    try:
        script = [tool("record_client_profile", PROFILE),
                  tool("record_requirement_analysis", {"requirements": [
                      {"requirement_id": "R", "requirement_type": "medical",
                       "summary": "s", "priority": "P1_HIGH"}]}),
                  tool("record_risk_assessment", {"risks": [
                      {"risk_id": "R1", "risk_category": "R1_medical",
                       "risk_name": "n", "priority": "P1_HIGH"}]}),
                  ("coverage_gap_analysis", {})]
        out, _, state, events = drive(script, "给4岁孩子买保险，预算1万，担心住院。")
        c.chk("eval fail: agent STOPS with needs_review (no fake success)",
              out.status == "needs_review" and "质量校验" in out.message, out.status)
        c.chk("eval fail: repair events from the existing loop present",
              any(e["event_type"] == "repair_started" for e in events))
        c.chk("eval fail: no report produced",
              no_report(state))
    finally:
        orch_mod._invoke_python_stage = original


@section
def test_event_hygiene_no_cot_no_secrets(c: Checks):
    script = [tool("record_client_profile", PROFILE), ASK]
    out, _, _, events = drive(script, "我想给4岁孩子买保险，预算1万，担心大病和住院。")
    blob = json.dumps(events, ensure_ascii=False)
    for banned in ("思考过程", "我认为下一步", "我猜测", "chain of thought",
                   "api_key", "apikey", "sk-", "authorization", "prompt"):
        c.chk("hygiene: events contain no %r" % banned, banned not in blob.lower())
    c.chk("hygiene: decision events carry schema-safe fields (incl. intent)",
          all(set(e["data"].keys()) <= {"step", "action", "intent", "reason", "final",
                                        "status", "tool", "artifact_id", "eval_id", "summary"}
              for e in events if e["event_type"] == "agent_decision"))


def build_registry():
    from runtime.agent.tools import build_registry as br
    return br()



def main():
    return run_sections(SECTIONS, "webui_test_agent_loop_log.txt", "RUNTIME AGENT LOOP")


if __name__ == "__main__":
    sys.exit(main())
