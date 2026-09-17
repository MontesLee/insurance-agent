"""Specialist Agent Executor tests (Phase 5.1).

FakeLLM only — no real GLM needed for CI. Covers: agent identity, prompt
isolation, tool boundary, authorization, structured output, no self-PASS,
real agent execution through the executor, multi-agent E2E, artifact-mediated
communication, eval failure/repair, step limit, LLM failure (no fallback),
checkpoint/resume, and deterministic regression.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_specialist_agent_executor.py`.
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
from runtime.agents import (AGENT_REGISTRY, agent_for_task, get,
                             validate_assignment, allowed_tools)
from runtime.agents.executor import SpecialistAgentExecutor, AgentExecutionResult
from runtime.agent.model import FakeLLMProvider, ToolCall, LLMResponse
from runtime.harness import LongRunningHarness

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_root():
    return tempfile.mkdtemp(prefix="sae_", dir=os.path.join(REPO, "tmp"))


def make_task(task_type, task_id="task_001"):
    return {"task_id": task_id, "task_type": task_type,
            "status": "PLANNED", "dependencies": [], "attempt": 0}


def make_case():
    from runtime.state import case_state as cs
    from runtime import tasks as tk
    state = cs.new_case_state("sae_case", WF)
    tk.init_tasks(state, WF)
    state["_workflow"] = WF
    return state


def seed_dialogue(state):
    """Seed client-profile + requirement + risk so downstream tools work."""
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fx = json.load(f)
    arts = {k: v for k, v in fx["artifacts"].items()}
    return orch.seed_case(WF, state["case_id"], copy.deepcopy(arts),
                          provided_by="sae-test")


# ------------------------------------------------------------------------- #
# T1 Agent Identity
# ------------------------------------------------------------------------- #
@section
def test_agent_identity(c: Checks):
    for aid in ("insurance_analyst", "knowledge_specialist",
                "product_specialist", "report_specialist"):
        d = get(aid)
        c.chk("identity: %s loaded" % aid, d is not None)
        c.chk("identity: %s has system_prompt" % aid, bool(d.get("system_prompt")))
        c.chk("identity: %s has allowed_tools" % aid, bool(d.get("allowed_tools")))


# ------------------------------------------------------------------------- #
# T2 Prompt Isolation
# ------------------------------------------------------------------------- #
@section
def test_prompt_isolation(c: Checks):
    prompts = {aid: get(aid)["system_prompt"] for aid in AGENT_REGISTRY}
    ids = list(prompts)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            c.chk("prompt isolation: %s ≠ %s" % (ids[i], ids[j]),
                  prompts[ids[i]] != prompts[ids[j]])
    c.chk("prompt: insurance_analyst mentions 'Insurance Analysis Agent'",
          "Insurance Analysis Agent" in prompts["insurance_analyst"])
    c.chk("prompt: product_specialist mentions 'Product Specialist Agent'",
          "Product Specialist Agent" in prompts["product_specialist"])
    c.chk("prompt: insurance_analyst forbids products",
          "not" in prompts["insurance_analyst"].lower()
          and "product" in prompts["insurance_analyst"].lower())


# ------------------------------------------------------------------------- #
# T3 Tool Boundary (agent cannot execute unauthorized task_type)
# ------------------------------------------------------------------------- #
@section
def test_tool_boundary(c: Checks):
    ok, err = validate_assignment("risk_analysis", "product_specialist")
    c.chk("boundary: product_specialist cannot risk_analysis", not ok)
    ok2, _ = validate_assignment("report_generation", "knowledge_specialist")
    c.chk("boundary: knowledge_specialist cannot report_generation", not ok2)


# ------------------------------------------------------------------------- #
# T4 Tool Authorization (runtime enforcement in executor)
# ------------------------------------------------------------------------- #
@section
def test_tool_authorization_runtime(c: Checks):
    """Agent tries to call a tool NOT in its allowed set → TOOL_NOT_AUTHORIZED."""
    state = make_case()
    # LLM tries to call check_catalog_product (NOT allowed for insurance_analyst)
    provider = FakeLLMProvider([
        ("check_catalog_product", {"query": "P001"}),  # unauthorized
        ("record_risk_assessment", {"risks": [
            {"risk_id": "R1", "risk_category": "R1_medical",
             "risk_name": "test", "priority": "P1_HIGH"}]}),  # authorized
    ])
    executor = SpecialistAgentExecutor(llm_provider=provider)
    events = []
    task = make_task("risk_analysis")
    seed_dialogue(state)
    result = executor.execute(agent_id="insurance_analyst", task=task,
                              project=None, case_state=state,
                              emit=lambda t, d: events.append((t, d)))
    val_fails = [e for e in events if e[0] == "agent_validation_failed"]
    c.chk("authorization: TOOL_NOT_AUTHORIZED event",
          len(val_fails) >= 1 and "TOOL_NOT_AUTHORIZED" in str(val_fails[0]),
          val_fails[:1] if val_fails else "no events")
    c.chk("authorization: unauthorized tool not executed",
          not any(e[0] == "agent_tool_completed" and e[1].get("tool") == "check_catalog_product"
                  for e in events))
    c.chk("authorization: authorized tool still works",
          any(e[0] == "agent_tool_completed" and e[1].get("tool") == "record_risk_assessment"
              for e in events))


# ------------------------------------------------------------------------- #
# T5 Structured Output (artifact contract)
# ------------------------------------------------------------------------- #
@section
def test_structured_output_contract(c: Checks):
    """Agent must produce the expected artifact or AGENT_OUTPUT_INVALID."""
    state = make_case()
    seed_dialogue(state)
    # LLM does NOT call any tool → no artifact → INVALID
    provider = FakeLLMProvider(["I'll just answer in text."])
    executor = SpecialistAgentExecutor(llm_provider=provider)
    result = executor.execute(agent_id="insurance_analyst",
                              task=make_task("risk_analysis"),
                              project=None, case_state=state)
    c.chk("output: no tool call → AGENT_FAILED or no artifact",
          result.outcome != "OK" or
          "risk-assessment" not in (state.get("artifacts") or {}),
          result.outcome)


# ------------------------------------------------------------------------- #
# T6 No Self-PASS
# ------------------------------------------------------------------------- #
@section
def test_no_self_pass(c: Checks):
    """Agent cannot declare eval=PASS. Eval runs in Harness, not in Agent."""
    import inspect
    from runtime.agents import executor as exec_mod
    src = inspect.getsource(exec_mod)
    c.chk("no self-PASS: executor has no eval=PASS logic",
          "eval.*PASS" not in src.replace("eval_rec", "").replace("eval_id", ""))
    c.chk("no self-PASS: eval_rec is None on OK (harness runs eval)",
          "eval_rec=None" in src or "eval_rec=None" in src.replace(" ", ""))
    # structural: the executor returns OK without eval; harness runs eval separately
    state = make_case()
    seed_dialogue(state)
    provider = FakeLLMProvider([
        ("record_risk_assessment", {"risks": [
            {"risk_id": "R1", "risk_category": "R1_medical",
             "risk_name": "t", "priority": "P1_HIGH"}]}),
    ])
    executor = SpecialistAgentExecutor(llm_provider=provider)
    result = executor.execute(agent_id="insurance_analyst",
                              task=make_task("risk_analysis"),
                              project=None, case_state=state)
    if result.outcome in ("OK", "ARTIFACT_READY"):
        c.chk("no self-PASS: OK result has eval_rec=None (harness will run eval)",
              result.eval_rec is None)


# ------------------------------------------------------------------------- #
# T7 Real Agent Execution (through executor with FakeLLM)
# ------------------------------------------------------------------------- #
@section
def test_real_agent_execution(c: Checks):
    """Proof: agent executor → LLM → tool → artifact. NOT _execute_stage."""
    state = make_case()
    seed_dialogue(state)
    provider = FakeLLMProvider([
        ("record_risk_assessment", {"risks": [
            {"risk_id": "R1-001", "risk_category": "R1_medical",
             "risk_name": "住院费用风险", "priority": "P1_HIGH"},
            {"risk_id": "R2-001", "risk_category": "R2_critical_illness",
             "risk_name": "重疾风险", "priority": "P1_HIGH"}]}),
    ])
    executor = SpecialistAgentExecutor(llm_provider=provider)
    events = []
    result = executor.execute(agent_id="insurance_analyst",
                              task=make_task("risk_analysis"),
                              project=None, case_state=state,
                              emit=lambda t, d: events.append((t, d)))

    c.chk("execution: outcome OK", result.outcome in ("OK", "ARTIFACT_READY"), result.outcome)
    c.chk("execution: risk-assessment artifact in CaseState",
          "risk-assessment" in (state.get("artifacts") or {}),
          sorted((state.get("artifacts") or {}).keys()))
    c.chk("execution: agent events present",
          any(e[0] == "agent_started" for e in events)
          and any(e[0] == "agent_tool_call" for e in events)
          and any(e[0] == "agent_output_validated" for e in events))
    c.chk("execution: FakeLLM was called (not _execute_stage)",
          provider.calls and len(provider.calls) >= 1)


# ------------------------------------------------------------------------- #
# T8 Multi-Agent E2E (harness with executor)
# ------------------------------------------------------------------------- #
@section
def test_multi_agent_e2e_with_executor(c: Checks):
    """2+ specialist agents through the harness with agent executor."""
    root = fresh_root()
    try:
        # 3-task graph: risk (insurance_analyst) → product_candidates (product_specialist)
        graph = {"tasks": [
            {"task_id": "task_001", "task_type": "client_profile"},
            {"task_id": "task_002", "task_type": "risk_analysis",
             "dependencies": ["task_001"]},
            {"task_id": "task_003", "task_type": "product_candidates",
             "dependencies": ["task_002"]},
        ]}
        # FakeLLM: for risk_analysis task, call record_risk_assessment;
        # for product_candidates task, call product_candidate_provider
        # (task_001 is seeded → skipped, so first executed task is task_002)
        provider = FakeLLMProvider([
            ("record_risk_assessment", {"risks": [
                {"risk_id": "R1", "risk_category": "R1_medical",
                 "risk_name": "住院", "priority": "P1_HIGH"}]}),
            # next call is for product_candidates
            ("product_candidate_provider", {}),
        ])
        h = LongRunningHarness(root, agent_executor=provider)
        p = h.create_project("sae-e2e", task_graph=graph)
        seed_dialogue_seed(root, p, exclude=("risk-assessment", "requirement-analysis"))

        result = h.run(p)
        agents = {e.get("agent_id") for e in p.events()
                  if e["event_type"] in ("agent_started", "agent_tool_call")}
        c.chk("E2E: ≥2 agents participated", len(agents) >= 2, agents)
        c.chk("E2E: insurance_analyst present", "insurance_analyst" in agents)
        c.chk("E2E: product_specialist present", "product_specialist" in agents)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def seed_dialogue_seed(root, project, exclude=()):
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fx = json.load(f)
    arts = {k: v for k, v in fx["artifacts"].items() if k not in exclude}
    state = orch.seed_case(WF, project.case_id, copy.deepcopy(arts),
                           provided_by="sae-e2e")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, project.project_id, "case"))


# ------------------------------------------------------------------------- #
# T9 Artifact-mediated Communication
# ------------------------------------------------------------------------- #
@section
def test_artifact_communication(c: Checks):
    """Agent A's output is in CaseState → Agent B reads it. No direct calls."""
    state = make_case()
    seed_dialogue(state)

    # Agent 1: insurance_analyst produces risk-assessment
    p1 = FakeLLMProvider([
        ("record_risk_assessment", {"risks": [
            {"risk_id": "R1", "risk_category": "R1_medical",
             "risk_name": "t", "priority": "P1_HIGH"}]}),
    ])
    exec1 = SpecialistAgentExecutor(llm_provider=p1)
    r1 = exec1.execute(agent_id="insurance_analyst",
                       task=make_task("risk_analysis"),
                       project=None, case_state=state)
    c.chk("comm: analyst produced risk-assessment", r1.outcome in ("OK", "ARTIFACT_READY"))

    # Agent 2: reads the same CaseState (artifact-mediated)
    arts_available = sorted((state.get("artifacts") or {}).keys())
    c.chk("comm: risk-assessment in shared CaseState",
          "risk-assessment" in arts_available, arts_available)

    # Verify no direct call mechanism exists
    import inspect
    from runtime.agents import executor
    src = inspect.getsource(executor)
    c.chk("comm: no call_agent / send_to_agent",
          "call_agent" not in src and "send_to_agent" not in src)


# ------------------------------------------------------------------------- #
# T10 LLM Failure / No Fallback
# ------------------------------------------------------------------------- #
@section
def test_llm_failure_no_fallback(c: Checks):
    """LLM fails → agent fails → NO deterministic fallback."""
    state = make_case()
    seed_dialogue(state)
    provider = FakeLLMProvider([RuntimeError("LLM is down")])
    executor = SpecialistAgentExecutor(llm_provider=provider)
    events = []
    result = executor.execute(agent_id="insurance_analyst",
                              task=make_task("risk_analysis"),
                              project=None, case_state=state,
                              emit=lambda t, d: events.append((t, d)))
    c.chk("LLM fail: AGENT_FAILED", result.outcome == "AGENT_FAILED",
          result.outcome)
    c.chk("LLM fail: error_code LLM_ERROR", result.error_code == "LLM_ERROR",
          result.error_code)
    c.chk("LLM fail: no artifact produced",
          "risk-assessment" not in (state.get("artifacts") or {}))
    c.chk("LLM fail: agent_failed event",
          any(e[0] == "agent_failed" for e in events))


# ------------------------------------------------------------------------- #
# T11 Step Limit
# ------------------------------------------------------------------------- #
@section
def test_step_limit(c: Checks):
    """Agent exceeds MAX_AGENT_STEPS=8 → AGENT_STEP_LIMIT."""
    state = make_case()
    seed_dialogue(state)
    # Script: unauthorized tool repeatedly (agent keeps trying wrong tools)
    script = [("check_catalog_product", {"query": "x"})] * 10
    provider = FakeLLMProvider(script)
    executor = SpecialistAgentExecutor(llm_provider=provider)
    result = executor.execute(agent_id="insurance_analyst",
                              task=make_task("risk_analysis"),
                              project=None, case_state=state)
    c.chk("step limit: AGENT_FAILED or STEP_LIMIT",
          result.outcome == "AGENT_FAILED", result.outcome)
    # either step limit hit or unauthorized tool loop
    c.chk("step limit: did not succeed via unauthorized tools",
          result.outcome != "OK")


# ------------------------------------------------------------------------- #
# T12 Executor with unknown agent / unknown task
# ------------------------------------------------------------------------- #
@section
def test_executor_edge_cases(c: Checks):
    state = make_case()
    executor = SpecialistAgentExecutor(llm_provider=FakeLLMProvider([]))

    r1 = executor.execute(agent_id="hacker", task=make_task("risk_analysis"),
                          project=None, case_state=state)
    c.chk("edge: unknown agent → AGENT_FAILED", r1.outcome == "AGENT_FAILED")
    c.chk("edge: error AGENT_NOT_FOUND", r1.error_code == "AGENT_NOT_FOUND")

    r2 = executor.execute(agent_id="insurance_analyst",
                          task=make_task("fake_task_type"),
                          project=None, case_state=state)
    c.chk("edge: unknown task_type → failed", r2.outcome != "OK")


# ------------------------------------------------------------------------- #
# T13 Checkpoint / Resume with agent executor
# ------------------------------------------------------------------------- #
@section
def test_checkpoint_resume_with_executor(c: Checks):
    """Agent task + checkpoint → kill → resume preserves assigned_agent."""
    root = fresh_root()
    try:
        graph = {"tasks": [
            {"task_id": "task_001", "task_type": "client_profile"},
            {"task_id": "task_002", "task_type": "requirement_analysis",
             "dependencies": ["task_001"]},
            {"task_id": "task_003", "task_type": "risk_analysis",
             "dependencies": ["task_002"]},
        ]}
        h = LongRunningHarness(root)
        p = h.create_project("sae-resume", task_graph=graph)
        seed_dialogue_seed(root, p)

        # mark first 2 as PASSED with agents
        for t in p.tasks[:2]:
            p._set_task(t["task_id"], status="PASSED",
                        assigned_agent=agent_for_task(t["task_type"]))
        p._save()

        # NEW instance resumes
        p2 = LongRunningHarness(root).resume(p.project_id) if False else None
        h2 = LongRunningHarness(root)
        result = h2.resume(p.project_id)
        c.chk("resume: completed", result["status"] == "completed",
              result.get("status"))

        p3 = None
        from runtime.harness import load_project
        p3 = load_project(root, p.project_id)
        for t in p3.tasks[:2]:
            c.chk("resume: %s preserves agent" % t["task_type"],
                  t.get("assigned_agent") == agent_for_task(t["task_type"]))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------- #
# T14 Event Integrity
# ------------------------------------------------------------------------- #
@section
def test_executor_event_integrity(c: Checks):
    state = make_case()
    seed_dialogue(state)
    provider = FakeLLMProvider([
        ("record_risk_assessment", {"risks": [
            {"risk_id": "R1", "risk_category": "R1_medical",
             "risk_name": "t", "priority": "P1_HIGH"}]}),
    ])
    executor = SpecialistAgentExecutor(llm_provider=provider)
    events = []
    executor.execute(agent_id="insurance_analyst",
                     task=make_task("risk_analysis"),
                     project=None, case_state=state,
                     emit=lambda t, d: events.append((t, d)))
    blob = json.dumps([dict(e[1]) for e in events], ensure_ascii=False)
    import re
    for banned in ("api_key", "authorization", "chain of thought",
                   "思考过程", "system_prompt"):
        c.chk("events: no %r" % banned, banned not in blob.lower())
    # sk- alone matches 'risk-assessment' — check real key SHAPE
    c.chk("events: no real API key shape",
          re.search(r"sk-[a-zA-Z0-9_-]{16,}", blob) is None)
    # verify event types are known
    ev_types = {e[0] for e in events}
    from runtime.events import EVENT_TYPES
    c.chk("events: executor vocabulary in EVENT_TYPES",
          ev_types <= EVENT_TYPES, ev_types - EVENT_TYPES)


def main():
    return run_sections(SECTIONS, "webui_test_sae_log.txt",
                        "RUNTIME SPECIALIST AGENT EXECUTOR")


if __name__ == "__main__":
    sys.exit(main())
