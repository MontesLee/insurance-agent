"""Multi-Agent V0.1 tests (Phase 5).

Covers: Agent Registry, deterministic Assignment, unauthorized/unknown agent
validation, agent events, tool boundary, artifact-mediated communication,
Multi-Agent E2E (3 specialist agents), and checkpoint/resume with agent identity.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_multi_agent.py`.
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
from runtime.agents import (AGENT_REGISTRY, TASK_AGENT_MAP, agent_for_task,
                             get, is_valid_agent, can_execute, allowed_tools,
                             validate_assignment)
from runtime.harness import LongRunningHarness, load_project
from runtime.planner import FakePlannerProvider, plan, validate_graph

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_root():
    return tempfile.mkdtemp(prefix="multi_agent_", dir=os.path.join(REPO, "tmp"))


def seed_case(root, project):
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    state = orch.seed_case(WF, project.case_id,
                           copy.deepcopy(fixture["artifacts"]),
                           provided_by="multi-agent-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, project.project_id, "case"))
    return state


# ------------------------------------------------------------------------- #
# Test 1 — Registry
# ------------------------------------------------------------------------- #
@section
def test_agent_registry(c: Checks):
    expected = {"insurance_analyst", "knowledge_specialist",
                "product_specialist", "report_specialist"}
    c.chk("registry: 4 specialist agents", set(AGENT_REGISTRY) == expected,
          set(AGENT_REGISTRY))
    for aid, d in AGENT_REGISTRY.items():
        c.chk("registry: %s has agent_id" % aid, d["agent_id"] == aid)
        c.chk("registry: %s has name" % aid, bool(d.get("name")))
        c.chk("registry: %s has description" % aid, bool(d.get("description")))
        c.chk("registry: %s has allowed_task_types" % aid,
              bool(d.get("allowed_task_types")))
        c.chk("registry: %s has allowed_tools" % aid, bool(d.get("allowed_tools")))
        c.chk("registry: %s has system_prompt" % aid, bool(d.get("system_prompt")))


# ------------------------------------------------------------------------- #
# Test 2 — Deterministic Assignment
# ------------------------------------------------------------------------- #
@section
def test_agent_assignment(c: Checks):
    cases = [
        ("client_profile", "insurance_analyst"),
        ("requirement_analysis", "insurance_analyst"),
        ("risk_analysis", "insurance_analyst"),
        ("coverage_gap", "insurance_analyst"),
        ("solution", "insurance_analyst"),
        ("knowledge_search", "knowledge_specialist"),
        ("product_candidates", "product_specialist"),
        ("recommendation", "product_specialist"),
        ("report_generation", "report_specialist"),
    ]
    for tt, expected_agent in cases:
        c.chk("assignment: %s → %s" % (tt, expected_agent),
              agent_for_task(tt) == expected_agent,
              agent_for_task(tt))
    c.chk("assignment: all 9 task types covered", len(TASK_AGENT_MAP) == 9)


# ------------------------------------------------------------------------- #
# Test 3 — Unauthorized Agent
# ------------------------------------------------------------------------- #
@section
def test_unauthorized_agent(c: Checks):
    ok, err = validate_assignment("risk_analysis", "product_specialist")
    c.chk("unauthorized: product_specialist cannot do risk_analysis",
          not ok, ok)
    c.chk("unauthorized: error mentions 'not allowed'", "not allowed" in (err or ""),
          err)
    ok2, err2 = validate_assignment("report_generation", "insurance_analyst")
    c.chk("unauthorized: insurance_analyst cannot do report_generation",
          not ok2, ok2)


# ------------------------------------------------------------------------- #
# Test 4 — Unknown Agent
# ------------------------------------------------------------------------- #
@section
def test_unknown_agent(c: Checks):
    ok, err = validate_assignment("risk_analysis", "hacker_agent")
    c.chk("unknown: hacker_agent FAIL", not ok)
    c.chk("unknown: error mentions 'not in Agent Registry'",
          "not in Agent Registry" in (err or ""), err)
    c.chk("unknown: is_valid_agent returns False",
          not is_valid_agent("hacker_agent"))


# ------------------------------------------------------------------------- #
# Test 5 — Agent cannot self-mark PASS (eval is independent)
# ------------------------------------------------------------------------- #
@section
def test_agent_cannot_self_mark_pass(c: Checks):
    """Agent output → Artifact → Eval (independent). Agent saying COMPLETED
    doesn't mean PASSED. The harness uses _execute_stage which runs eval."""
    import inspect
    from runtime.agents import registry
    src = inspect.getsource(registry)
    c.chk("no self-PASS: registry has no mark_task_passed",
          "mark_task_passed" not in src)
    c.chk("no self-PASS: registry has no skip_eval",
          "skip_eval" not in src)
    c.chk("no bypass: registry has no modify_checkpoint",
          "modify_checkpoint" not in src)
    # structural: validate_assignment is a pure function, agents can't override
    c.chk("no bypass: validate_assignment is deterministic",
          validate_assignment("risk_analysis", "insurance_analyst") == (True, None))


# ------------------------------------------------------------------------- #
# Test 6 — Multi-Agent E2E (the main acceptance)
# ------------------------------------------------------------------------- #
@section
def test_multi_agent_e2e(c: Checks):
    """Full E2E: Planner → Graph → 3+ specialist agents → real execution → report."""
    root = fresh_root()
    try:
        # 1. Plan (FakePlanner, 9-task chain)
        graph_json = json.dumps({"tasks": [
            {"task_id": "task_%03d" % i, "task_type": tt,
             "dependencies": ["task_%03d" % (i-1)] if i > 1 else []}
            for i, tt in enumerate([
                "client_profile", "requirement_analysis", "risk_analysis",
                "coverage_gap", "solution", "knowledge_search",
                "product_candidates", "recommendation", "report_generation"], 1)
        ]})
        result = plan(FakePlannerProvider([graph_json]), "multi-agent e2e")
        c.chk("E2E: planner ok", result.ok)

        # 2. Harness accepts graph
        h = LongRunningHarness(root)
        p = h.create_project("ma-e2e", task_graph=result.graph)
        c.chk("E2E: harness accepted", len(p.tasks) == 9)

        # 3. Seed CaseState
        seed_case(root, p)

        # 4. Execute — different agents handle different tasks
        run_result = h.run(p)
        c.chk("E2E: completed", run_result["status"] == "completed",
              run_result["status"])

        # 5. Verify MULTIPLE agents participated
        evs = p.events()
        agents_seen = {e.get("agent_id") for e in evs
                       if e["event_type"] in ("agent_started", "agent_completed")}
        c.chk("E2E: ≥3 distinct agents participated",
              len(agents_seen) >= 3, agents_seen)
        c.chk("E2E: insurance_analyst participated",
              "insurance_analyst" in agents_seen)
        c.chk("E2E: product_specialist participated",
              "product_specialist" in agents_seen)
        c.chk("E2E: report_specialist participated",
              "report_specialist" in agents_seen)

        # 6. Verify artifacts
        from runtime.state import store as state_store
        state = state_store.load(os.path.join(root, p.project_id, "case"),
                                 p.case_id)
        arts = sorted((state or {}).get("artifacts", {}).keys())
        c.chk("E2E: insurance-report produced", "insurance-report" in arts)
        c.chk("E2E: 9 artifacts", len(arts) >= 9, arts)

        # 7. Verify executed results carry agent assignments
        for item in run_result["executed"]:
            if item["outcome"] == "PASS":
                c.chk("E2E: %s has agent" % item["task"], bool(item.get("agent")),
                      item)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------- #
# Test 7 — Artifact-mediated communication (no direct agent-to-agent)
# ------------------------------------------------------------------------- #
@section
def test_artifact_mediated_communication(c: Checks):
    """Agent A's artifact → CaseState → Agent B reads it via stage inputs.
    No direct calls between agents."""
    import inspect
    from runtime.agents import registry
    src = inspect.getsource(registry)
    c.chk("artifact-comm: no direct_call in registry",
          "direct_call" not in src)
    c.chk("artifact-comm: no message_bus", "message_bus" not in src)
    c.chk("artifact-comm: no send_to_agent", "send_to_agent" not in src)

    # structural: downstream agents read upstream artifacts via CaseState
    # (verified by the E2E test above where report_specialist reads
    #  recommendation produced by product_specialist)
    c.chk("artifact-comm: tool boundary enforced per agent",
          set(allowed_tools("insurance_analyst")) !=
          set(allowed_tools("product_specialist")))


# ------------------------------------------------------------------------- #
# Test 8 — Kill / Restart / Resume with agent identity
# ------------------------------------------------------------------------- #
@section
def test_kill_restart_resume_with_agents(c: Checks):
    """After kill+restart, agent assignments are preserved on disk."""
    root = fresh_root()
    try:
        h = LongRunningHarness(root)
        graph = {"tasks": [
            {"task_id": "task_%03d" % i, "task_type": tt,
             "dependencies": ["task_%03d" % (i-1)] if i > 1 else []}
            for i, tt in enumerate([
                "client_profile", "requirement_analysis", "risk_analysis",
                "coverage_gap", "solution", "knowledge_search",
                "product_candidates", "recommendation", "report_generation"], 1)
        ]}
        p = h.create_project("ma-resume", task_graph=graph)
        seed_case(root, p)

        # Run partially: seed_case marks first 3 stages COMPLETED
        # Manually mark first 4 tasks as PASSED + assign agents
        for i, t in enumerate(p.tasks[:4]):
            p._set_task(t["task_id"], status="PASSED",
                        assigned_agent=agent_for_task(t["task_type"]))
        p._save()

        # NEW harness instance resumes
        h2 = LongRunningHarness(root)
        p2 = load_project(root, p.project_id)
        c.chk("resume: project loadable", p2 is not None)

        # Verify agent assignments preserved
        for t in p2.tasks[:4]:
            c.chk("resume: %s has assigned_agent=%s preserved"
                  % (t["task_type"], agent_for_task(t["task_type"])),
                  t.get("assigned_agent") == agent_for_task(t["task_type"]),
                  t.get("assigned_agent"))

        # Resume execution
        result = h2.resume(p.project_id)
        c.chk("resume: completed", result["status"] == "completed",
              result.get("status"))

        # Verify agent events present after resume
        evs = p2.events()
        agents_after = {e.get("agent_id") for e in evs
                        if e["event_type"] == "agent_started"}
        c.chk("resume: agents participating after restart",
              len(agents_after) >= 2, agents_after)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------- #
# Test 9 — Eval failure with agent identity
# ------------------------------------------------------------------------- #
@section
def test_eval_failure_with_agent(c: Checks):
    """When a task fails eval, agent_failed event carries the agent_id."""
    root = fresh_root()
    try:
        h = LongRunningHarness(root)
        # use Planner-names task_graph so agent assignment works
        graph = {"tasks": [
            {"task_id": "task_%03d" % i, "task_type": tt,
             "dependencies": ["task_%03d" % (i-1)] if i > 1 else []}
            for i, tt in enumerate([
                "client_profile", "requirement_analysis", "risk_analysis",
                "coverage_gap", "solution", "knowledge_search",
                "product_candidates", "recommendation", "report_generation"], 1)
        ]}
        p = h.create_project("ma-fail", task_graph=graph)
        # Seed WITHOUT risk-assessment → risk task will fail
        import copy
        with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                               "case-full-chain.json"), encoding="utf-8") as f:
            fixture = json.load(f)
        arts = copy.deepcopy(fixture["artifacts"])
        del arts["risk-assessment"]
        state = orch.seed_case(WF, p.case_id, arts, provided_by="ma-fail")
        from runtime.state import store as state_store
        state_store.save(state, os.path.join(root, p.project_id, "case"))

        result = h.run(p)
        c.chk("fail: project not completed", result["status"] != "completed")

        evs = p.events()
        failed_with_agent = [e for e in evs
                             if e["event_type"] == "agent_failed"
                             and e.get("agent_id")]
        c.chk("fail: agent_failed events carry agent_id",
              len(failed_with_agent) >= 1,
              [(e.get("agent_id"), e.get("task_type")) for e in failed_with_agent])

        val_fails = [e for e in evs if e["event_type"] == "agent_validation_failed"]
        c.chk("fail: no validation failures in valid setup", len(val_fails) == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------- #
# Test 10 — No agent bypass (boundary enforcement)
# ------------------------------------------------------------------------- #
@section
def test_no_agent_bypass(c: Checks):
    """Agent boundary is structural: tool lists are read-only constants."""
    # tool boundary: each agent has a distinct tool set
    ia_tools = set(allowed_tools("insurance_analyst"))
    ps_tools = set(allowed_tools("product_specialist"))
    ks_tools = set(allowed_tools("knowledge_specialist"))
    rs_tools = set(allowed_tools("report_specialist"))

    c.chk("boundary: insurance_analyst has no product tools",
          "recommendation" not in ia_tools and "product_candidate_provider" not in ia_tools)
    c.chk("boundary: product_specialist has no analysis tools",
          "risk_analysis" not in ps_tools and "coverage_gap_analysis" not in ps_tools)
    c.chk("boundary: knowledge_specialist only has knowledge_search",
          ks_tools == {"knowledge_search"})
    c.chk("boundary: report_specialist only has report_generation",
          rs_tools == {"report_generation"})

    # unauthorized agent → BLOCKED in harness
    root = fresh_root()
    try:
        h = LongRunningHarness(root)
        graph = {"tasks": [
            {"task_id": "task_%03d" % i, "task_type": tt,
             "dependencies": ["task_%03d" % (i-1)] if i > 1 else []}
            for i, tt in enumerate([
                "client_profile", "requirement_analysis", "risk_analysis"], 1)
        ]}
        p = h.create_project("ma-bypass", task_graph=graph)
        seed_case(root, p)
        # manually assign wrong agent to risk task
        risk_task = next((t for t in p.tasks if t["task_type"] == "risk_analysis"), None)
        if risk_task is None:
            c.chk("bypass: risk_analysis task found", False,
                  [t["task_type"] for t in p.tasks])
            shutil.rmtree(root, ignore_errors=True)
            return
        p._set_task(risk_task["task_id"], assigned_agent="product_specialist")
        p._save()

        result = h.run(p)
        evs = p.events()
        val_fails = [e for e in evs if e["event_type"] == "agent_validation_failed"]
        c.chk("bypass: agent_validation_failed event present",
              len(val_fails) >= 1,
              [(e.get("agent_id"), e.get("reason", "")[:60]) for e in val_fails])
        c.chk("bypass: risk_analysis not executed by wrong agent",
              not any(e["event_type"] == "agent_completed"
                      and e.get("task_type") == "risk_analysis"
                      and e.get("agent_id") == "product_specialist" for e in evs))
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------- #
# Event integrity
# ------------------------------------------------------------------------- #
@section
def test_multi_agent_event_integrity(c: Checks):
    root = fresh_root()
    try:
        h = LongRunningHarness(root)
        graph = {"tasks": [
            {"task_id": "task_%03d" % i, "task_type": tt,
             "dependencies": ["task_%03d" % (i-1)] if i > 1 else []}
            for i, tt in enumerate([
                "client_profile", "requirement_analysis", "risk_analysis",
                "coverage_gap", "solution", "knowledge_search",
                "product_candidates", "recommendation", "report_generation"], 1)
        ]}
        p = h.create_project("ma-events", task_graph=graph)
        seed_case(root, p)
        h.run(p)

        evs = p.events()
        blob = json.dumps(evs, ensure_ascii=False)
        c.chk("events: JSON-serializable", len(evs) > 0)
        for banned in ("api_key", "authorization", "sk-", "chain of thought",
                       "思考过程", "system_prompt"):
            c.chk("events: no %r" % banned, banned not in blob.lower())

        # verify agent event vocabulary
        agent_evs = {e["event_type"] for e in evs if e["event_type"].startswith("agent_")}
        from runtime.events import EVENT_TYPES
        c.chk("events: agent vocabulary in EVENT_TYPES",
              agent_evs <= EVENT_TYPES, agent_evs - EVENT_TYPES)

        # verify event ordering: agent_assigned before agent_started
        if agent_evs:
            assigns = [i for i, e in enumerate(evs) if e["event_type"] == "agent_assigned"]
            starts = [i for i, e in enumerate(evs) if e["event_type"] == "agent_started"]
            if assigns and starts:
                c.chk("events: agent_assigned precedes agent_started",
                      assigns[0] < starts[0])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_multi_agent_log.txt",
                        "RUNTIME MULTI-AGENT")


if __name__ == "__main__":
    sys.exit(main())
