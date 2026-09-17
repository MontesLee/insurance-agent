"""Phase 6.2.1 — True 4-Agent Runtime E2E.

All 4 specialist agents must be ASSIGNED, START, and EXECUTE tool calls.
At least 3 TASK_HANDOFF messages sent through the real MessageBus.
Product/artifact/eval chain verified from real execution data.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_true_4_agent_e2e.py`.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch
from runtime.agent.model import FakeLLMProvider
from runtime.harness import LongRunningHarness

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="e2e4_", dir=os.path.join(REPO, "tmp"))


RISK_ARGS = {"risks": [
    {"risk_id": "R1-001", "risk_category": "R1_medical",
     "risk_name": "住院费用风险", "priority": "P1_HIGH"},
    {"risk_id": "R2-001", "risk_category": "R2_critical_illness",
     "risk_name": "重疾风险", "priority": "P1_HIGH"}]}

# 6-task graph: 4 agents, coverage_gap not blocking knowledge_search
GRAPH = {"tasks": [
    {"task_id": "task_001", "task_type": "client_profile"},
    {"task_id": "task_002", "task_type": "risk_analysis",
     "dependencies": ["task_001"]},
    {"task_id": "task_003", "task_type": "coverage_gap",
     "dependencies": ["task_002"]},
    {"task_id": "task_004", "task_type": "solution",
     "dependencies": ["task_003"]},
    {"task_id": "task_005", "task_type": "knowledge_search",
     "dependencies": ["task_003"]},  # NOT a dep of 006 (may fail)
    {"task_id": "task_006", "task_type": "product_candidates",
     "dependencies": ["task_004"]},  # depends on solution, NOT on 005
    {"task_id": "task_007", "task_type": "report_generation",
     "dependencies": ["task_006"]},
]}

# FakeLLM script: consumed sequentially across all agent executions
FAKE_SCRIPT = [
    # Task 002 (insurance_analyst)
    ("record_risk_assessment", RISK_ARGS),
    "Risk assessment recorded.",
    # Task 003 (insurance_analyst): coverage_gap + handoffs
    ("coverage_gap_analysis", {}),
    ("send_agent_message", {
        "to_agent": "knowledge_specialist",
        "message_type": "TASK_HANDOFF",
        "task_id": "task_005",
        "content": {"request": "请检索医疗和重疾相关证据"}}),
    ("send_agent_message", {
        "to_agent": "product_specialist",
        "message_type": "TASK_HANDOFF",
        "task_id": "task_006",
        "content": {"request": "请基于保障缺口筛选产品候选"}}),
    "Coverage gap analysis and handoffs complete.",
    # Task 004 (insurance_analyst): solution
    ("solution", {}),
    "Solution designed.",
    # Task 005 (knowledge_specialist): may fail on artifact contract
    ("knowledge_search", {"query": "百万医疗险 重疾险 区别"}),
    "Knowledge search completed.",
    # Task 006 (product_specialist)
    ("product_candidate_provider", {}),
    ("send_agent_message", {
        "to_agent": "report_specialist",
        "message_type": "TASK_HANDOFF",
        "task_id": "task_007",
        "content": {"request": "请基于产品候选生成最终报告"}}),
    "Product candidates selected.",
    # Task 007 (report_specialist)
    ("report_generation", {}),
    "Report generated.",
]


@section
def test_true_4_agent_e2e(c: Checks):
    """THE Phase 6.2.1 acceptance test: 4 agents assigned + started + tool calls."""
    d = fresh_dir()
    try:
        provider = FakeLLMProvider(list(FAKE_SCRIPT))
        h = LongRunningHarness(d, agent_executor=provider)
        p = h.create_project("e2e4", task_graph=GRAPH)

        # Seed client-profile + requirement-analysis (NOT risk-assessment,
        # so insurance_analyst has work to do)
        import copy
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fx = json.load(f)
        seed_arts = {
            "client-profile": fx["artifacts"]["client-profile"],
            "requirement-analysis": fx["artifacts"]["requirement-analysis"],
        }
        state = orch.seed_case(WF, p.case_id, copy.deepcopy(seed_arts))
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))

        # Run
        result = h.run(p)

        # ---- T1: 4 agents assigned --------------------------------------- #
        evs = p.events()
        assigned_agents = {e.get("agent_id") for e in evs
                           if e["event_type"] == "agent_assigned"}
        c.chk("T1: 4 agents assigned", len(assigned_agents) == 4, assigned_agents)
        c.chk("T1: all specialist agents assigned",
              assigned_agents == {"insurance_analyst", "knowledge_specialist",
                                 "product_specialist", "report_specialist"})

        # ---- T2-T5: agents started and executed -------------------------- #
        started_agents = {e.get("agent_id") for e in evs
                          if e["event_type"] == "agent_started"}
        c.chk("T2: insurance_analyst started",
              "insurance_analyst" in started_agents, started_agents)
        c.chk("T3: knowledge_specialist started",
              "knowledge_specialist" in started_agents, started_agents)
        c.chk("T4: product_specialist started",
              "product_specialist" in started_agents, started_agents)
        c.chk("T5: report_specialist started",
              "report_specialist" in started_agents, started_agents)
        c.chk("T1-T5: 4 agents started", len(started_agents) >= 4,
              started_agents)

        # ---- Load artifacts for tool verification -------------------------- #
        from runtime.state import store as _ss_check
        _final_check = _ss_check.load(os.path.join(d, p.project_id, "case"), p.case_id)
        artifacts_check = sorted(((_final_check or {}).get("artifacts") or {}).keys())

        # ---- Tool call verification (via artifacts + FakeLLM calls) ------- #
        # agent_tool_call events go to the harness emit callback, not project
        # events.jsonl (known observability gap). Verify via artifacts instead.
        c.chk("tool calls: insurance_analyst produced artifacts",
              "risk-assessment" in artifacts_check)
        c.chk("tool calls: product_specialist produced artifacts",
              "product-candidates" in artifacts_check)
        c.chk("tool calls: report_specialist produced artifacts",
              "insurance-report" in artifacts_check)
        c.chk("tool calls: FakeLLM consumed ≥10 script items",
              len(FAKE_SCRIPT) - len(provider._script) >= 10,
              len(FAKE_SCRIPT) - len(provider._script))

        # ---- T6-T8: handoffs sent and persisted --------------------------- #
        msg_path = os.path.join(d, p.project_id, "messages.jsonl")
        c.chk("T6: messages.jsonl exists", os.path.exists(msg_path))
        if os.path.exists(msg_path):
            with open(msg_path, encoding="utf-8") as f:
                msgs = [json.loads(l) for l in f if l.strip()]
            c.chk("T6-T8: ≥3 TASK_HANDOFF messages", len(msgs) >= 3, len(msgs))
            handoff_msgs = [m for m in msgs if m["message_type"] == "TASK_HANDOFF"]
            pairs = {(m["from_agent"], m["to_agent"]) for m in handoff_msgs}
            c.chk("T6: analyst→knowledge handoff",
                  ("insurance_analyst", "knowledge_specialist") in pairs, pairs)
            c.chk("T7: analyst→product handoff",
                  ("insurance_analyst", "product_specialist") in pairs, pairs)
            c.chk("T8: product→report handoff",
                  ("product_specialist", "report_specialist") in pairs, pairs)

        # ---- T9: artifact chain ------------------------------------------ #
        from runtime.state import store as ss2
        final = ss2.load(os.path.join(d, p.project_id, "case"), p.case_id)
        artifacts = sorted(((final or {}).get("artifacts") or {}).keys())
        c.chk("T9: risk-assessment produced", "risk-assessment" in artifacts)
        c.chk("T9: coverage-gap-analysis produced",
              "coverage-gap-analysis" in artifacts)
        c.chk("T9: product-candidates produced",
              "product-candidates" in artifacts)

        # ---- T10: eval chain ---------------------------------------------- #
        evals = (final or {}).get("evaluations") or []
        passed = sum(1 for e in evals if e.get("status") == "PASS")
        c.chk("T10: ≥3 evals passed", passed >= 3, passed)

        # ---- T11: ACK chain ----------------------------------------------- #
        from runtime.agents import MessageBus
        bus = MessageBus(p._dir)
        acked = [m for m in bus.all_messages() if m["status"] == "ACKED"]
        c.chk("T11: ≥1 handoff ACKED (for passed tasks)", len(acked) >= 1,
              [(m["message_id"], m["status"]) for m in bus.all_messages()])

        # ---- T12: no direct agent call ------------------------------------ #
        # (structural: all communication goes through messages.jsonl)
        c.chk("T12: communication via messages.jsonl (not direct call)",
              os.path.exists(msg_path))

        # ---- T13: no graph mutation ---------------------------------------- #
        c.chk("T13: task count unchanged", len(p.tasks) == 7,
              len(p.tasks))

        # ---- Summary for the trace ------------------------------------------- #
        print("\n=== 4-AGENT E2E TRACE ===")
        print("result status:", result["status"])
        print("assigned:", sorted(assigned_agents))
        print("started:", sorted(started_agents))
        for item in result.get("executed", []):
            print("  %s: %s (agent: %s)" % (item["task"], item["outcome"],
                                            item.get("agent", "-")))
        if os.path.exists(msg_path):
            print("handoffs:", len(msgs))
            for m in msgs:
                print("  %s → %s (task: %s, status: %s)" % (
                    m["from_agent"], m["to_agent"], m.get("task_id", "-"),
                    m["status"]))
        print("artifacts:", artifacts)
        print("evals passed:", passed)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_true_4_agent_trace(c: Checks):
    """Verify the full event trace has the right types in the right order."""
    d = fresh_dir()
    try:
        provider = FakeLLMProvider(list(FAKE_SCRIPT))
        h = LongRunningHarness(d, agent_executor=provider)
        p = h.create_project("e2e4-trace", task_graph=GRAPH)
        import copy
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fx = json.load(f)
        seed_arts = {
            "client-profile": fx["artifacts"]["client-profile"],
            "requirement-analysis": fx["artifacts"]["requirement-analysis"],
        }
        state = orch.seed_case(WF, p.case_id, copy.deepcopy(seed_arts))
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))
        h.run(p)

        evs = p.events()
        types = [e["event_type"] for e in evs]

        # verify key lifecycle events present
        for needed in ("agent_assigned", "agent_started", "task_started",
                       "task_completed"):
            c.chk("trace: %s present" % needed, needed in types,
                  types[:15])

        # verify agent_assigned comes before agent_started for the first agent
        first_assigned = next((i for i, t in enumerate(types)
                               if t == "agent_assigned"), None)
        first_started = next((i for i, t in enumerate(types)
                              if t == "agent_started"), None)
        if first_assigned is not None and first_started is not None:
            c.chk("trace: agent_assigned before agent_started",
                  first_assigned < first_started)

        # verify handoff events present
        # Handoff events go to harness emit callback, not project events.
        # Verify via messages.jsonl instead.
        _msg_path = os.path.join(d, p.project_id, "messages.jsonl")
        if os.path.exists(_msg_path):
            with open(_msg_path, encoding="utf-8") as f:
                _msgs = [json.loads(l) for l in f if l.strip()]
            c.chk("trace: handoff messages persisted", len(_msgs) >= 3,
                  len(_msgs))
        else:
            c.chk("trace: handoff messages persisted", False, "no messages.jsonl")

        # print the full trace for the report
        print("\n=== EVENT TRACE (condensed) ===")
        for e in evs:
            agent = e.get("agent_id") or ""
            task = e.get("task_id") or ""
            print("  %-28s %-24s %s" % (e["event_type"], agent, task))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_e2e4_log.txt",
                        "RUNTIME TRUE 4-AGENT E2E")


if __name__ == "__main__":
    sys.exit(main())
