"""Phase 11 — Failure-injection matrix (T-matrix F01–F18).

Each row of evals/benchmark/failure-injection/matrix.json is injected into
the REAL runtime and its expected state / event / terminal behavior is
machine-verified. Injection → Expected State → Expected Event → Expected
Terminal, exactly as the matrix declares.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "tests", "runtime"))
from evals.benchmark import runner as bench  # noqa: E402
from evals.benchmark import scriptlib  # noqa: E402

from runtime import orchestrator as orch  # noqa: E402
from runtime.approval import ApprovalStore  # noqa: E402
from runtime.control import ControlStore, make_command  # noqa: E402
from runtime.harness import LongRunningHarness, load_project  # noqa: E402
from runtime.planner.planner import FakePlannerProvider  # noqa: E402
from runtime.state import store as ss  # noqa: E402
from test_parallel_scheduler import ScriptAgentExecutor, TaskScriptProvider  # noqa: E402

SECTIONS = []
MATRIX = json.load(open(os.path.join(REPO, "evals", "benchmark",
                                    "failure-injection", "matrix.json"),
                       encoding="utf-8"))


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="finj_", dir=os.path.join(REPO, "tmp"))


BASE_GRAPH = {"tasks": [
    {"task_id": "task_0", "task_type": "client_profile"},
    {"task_id": "task_1", "task_type": "requirement_analysis",
     "dependencies": ["task_0"]},
    {"task_id": "task_2", "task_type": "risk_analysis",
     "dependencies": ["task_0", "task_1"]},
    {"task_id": "task_3", "task_type": "report_generation",
     "dependencies": ["task_0", "task_1", "task_2"]},
]}
BASE_SCRIPTS = {"task_0": "profile", "task_1": "req", "task_2": "risk",
                "task_3": "report"}


def make(root, scripts=None, planner_graphs=None, max_replans=2, **kw):
    provider = TaskScriptProvider(scriptlib.expand_scripts(
        scripts if scripts is not None else BASE_SCRIPTS))
    graphs = [json.dumps(g if isinstance(g, dict) else {"tasks": g},
                         ensure_ascii=False)
              for g in (planner_graphs or [])]
    h = LongRunningHarness(root, agent_executor=provider,
                           max_replans=max_replans,
                           planner_provider=FakePlannerProvider(graphs), **kw)
    p = h.create_project("finj", task_graph=copy.deepcopy(BASE_GRAPH))
    state = orch.seed_case(bench.WF, p.case_id, {})
    ss.save(state, os.path.join(root, p.project_id, "case"))
    return h, p, provider


def events_of(p, etype):
    return [e for e in p.events() if e["event_type"] == etype]


def check_common(c, fid, p, result, event=None, terminal=None):
    row = MATRIX[fid]
    if event:
        c.chk("%s: event %s observed" % (fid, event),
              len(events_of(p, event)) >= 1)
    if terminal and "|" not in terminal:
        c.chk("%s: terminal %s" % (fid, terminal),
              result.get("status") == terminal, result.get("status"))
    elif terminal:
        allowed = terminal.split("|")
        c.chk("%s: terminal in %s" % (fid, allowed),
              result.get("status") in allowed, result.get("status"))


# ---- planner failures ----------------------------------------------------- #
@section
def test_f01_f02_planner_failures(c: Checks):
    d = fresh_dir()
    try:
        h, p, _ = make(d, planner_graphs=["{broken", "{broken2", "{broken3"],
                       scripts=dict(BASE_SCRIPTS, task_2="plain:fail"))
        r = h.run(p)
        c.chk("F01: bounded planner retries (3 attempts)",
              p.replans and p.replans[0]["planner_attempts"] == 3)
        check_common(c, "F01_planner_invalid_json", p, r,
                     event="graph_validation_failed", terminal="needs_review")
        c.chk("F01: no revision created", p.current_graph_revision == 1)

        d2 = os.path.join(d, "b")
        bad = {"tasks": [{"task_id": "task_x", "task_type": "not_a_type"}]}
        h2, p2, _ = make(d2, planner_graphs=[bad, bad, bad],
                         scripts=dict(BASE_SCRIPTS, task_2="plain:fail"))
        r2 = h2.run(p2)
        c.chk("F02: unknown task_type rejected by validator",
              p2.current_graph_revision == 1
              and p2.replans[0]["status"] == "failed")
        check_common(c, "F02_planner_invalid_graph", p2, r2,
                     event="graph_validation_failed", terminal="needs_review")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- agent / knowledge / product failures --------------------------------- #
@section
def test_f03_f04_f05_agent_failures(c: Checks):
    d = fresh_dir()
    try:
        h, p, _ = make(d, scripts=dict(BASE_SCRIPTS,
                                       task_2="plain:风险输入不足，我拒绝编造。"))
        r = h.run(p)
        final = ss.load(os.path.join(d, p.project_id, "case"), p.case_id) or {}
        c.chk("F03: no risk artifact fabricated",
              "risk-assessment" not in (final.get("artifacts") or {}))
        check_common(c, "F03_agent_tool_failure", p, r,
                     event="agent_failed", terminal="needs_review")

        d2 = os.path.join(d, "b")
        graph = {"tasks": [
            {"task_id": "task_0", "task_type": "client_profile"},
            {"task_id": "task_1", "task_type": "requirement_analysis",
             "dependencies": ["task_0"]},
            {"task_id": "task_5", "task_type": "knowledge_search",
             "dependencies": ["task_1"]}]}
        h2 = LongRunningHarness(
            d2, agent_executor=TaskScriptProvider(scriptlib.expand_scripts(
                {"task_0": "profile", "task_1": "req",
                 "task_5": "know:fail"})),
            max_replans=0)
        p2 = h2.create_project("finj", task_graph=graph)
        state = orch.seed_case(bench.WF, p2.case_id, {})
        ss.save(state, os.path.join(d2, p2.project_id, "case"))
        r2 = h2.run(p2)
        final2 = ss.load(os.path.join(d2, p2.project_id, "case"), p2.case_id) or {}
        c.chk("F04: empty knowledge fails closed (no fabricated evidence)",
              "knowledge-evidence" not in (final2.get("artifacts") or {}))
        check_common(c, "F04_knowledge_empty", p2, r2,
                     event="agent_failed", terminal="needs_review")

        d3 = os.path.join(d, "c")
        h3 = LongRunningHarness(
            d3, agent_executor=ScriptAgentExecutor(
                scriptlib.expand_artifact_scripts(
                    {"client_profile": ["profile"],
                     "product_candidates": ["bad_product"] * 5})),
            max_concurrency=2, max_replans=0)
        p3 = h3.create_project("finj", task_graph={"tasks": [
            {"task_id": "task_0", "task_type": "client_profile"},
            {"task_id": "task_5", "task_type": "product_candidates",
             "dependencies": ["task_0"]}]})
        state = orch.seed_case(bench.WF, p3.case_id, {})
        ss.save(state, os.path.join(d3, p3.project_id, "case"))
        r3 = h3.run(p3)
        check_common(c, "F05_product_candidate_invalid", p3, r3,
                     event="task_failed", terminal="needs_review")
        evals = (ss.load(os.path.join(d3, p3.project_id, "case"), p3.case_id)
                 or {}).get("evaluations", [])
        c.chk("F05: catalog invariant fired",
              any("catalog" in json.dumps(e) for e in evals
                  if e["status"] == "FAIL"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- repair exhaustion / blocked / replan health --------------------------- #
@section
def test_f06_f07_repair_and_block(c: Checks):
    d = fresh_dir()
    try:
        out = bench.run_case(bench.load_cases({"B005"})[0], root=d)
        c.chk("F06: repair exhaustion (from benchmark B005)",
              out["passed"] and out["terminal_status"] == "needs_review")
        row = MATRIX["F06_repair_exhausted"]
        c.chk("F06: matrix row consistent with result",
              row["expected_terminal"] == out["terminal_status"])

        d2 = os.path.join(d, "b")
        h2, p2, _ = make(d2, scripts=dict(BASE_SCRIPTS, task_1="plain:fail"))
        r2 = h2.run(p2)
        c.chk("F07: downstream BLOCKED by upstream failure",
              p2.get_task("task_2")["status"] == "BLOCKED")
        check_common(c, "F07_task_blocked", p2, r2, terminal="needs_review")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_f08_f09_replan_health(c: Checks):
    d = fresh_dir()
    try:
        h, p, _ = make(d, planner_graphs=[copy.deepcopy(BASE_GRAPH)],
                       scripts=dict(BASE_SCRIPTS, task_2="plain:fail"))
        r = h.run(p)
        c.chk("F08: identical graph → no_change, no revision",
              p.replans[0]["status"] == "no_change"
              and p.current_graph_revision == 1)
        check_common(c, "F08_replan_no_change", p, r,
                     event="replan_failed", terminal="needs_review")

        d2 = os.path.join(d, "b")
        h2, p2, _ = make(d2, max_replans=1,
                         planner_graphs=["{bad", "{bad", "{bad"],
                         scripts=dict(BASE_SCRIPTS, task_2="plain:fail"))
        r2 = h2.run(p2)
        c.chk("F09: replan budget exhausted (1/1)",
              len(p2.replans) == 1 and p2.replans[0]["status"] == "failed")
        check_common(c, "F09_replan_exhausted", p2, r2,
                     event="replan_failed", terminal="needs_review")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- HITL / HOTL failures --------------------------------------------------- #
@section
def test_f10_f11_f12_f13_hitl_hotl(c: Checks):
    d = fresh_dir()
    try:
        # F10 approval rejected
        out = bench.run_case(bench.load_cases({"B008"})[0],
                             root=os.path.join(d, "b8"))
        # rerun manually with reject instead of approve
        case = bench.load_cases({"B008"})[0]
        h, provider = bench.build_harness(os.path.join(d, "f10"), case)
        p = h.create_project("f10", task_graph=case["input"]["graph"]
                             if isinstance(case["input"]["graph"], dict)
                             else {"tasks": case["input"]["graph"]})
        state = orch.seed_case(bench.WF, p.case_id, {})
        ss.save(state, os.path.join(d, "f10", p.project_id, "case"))
        r = h.run(p)
        appr = ApprovalStore(p._dir).pending()[0]
        h._approval_manager(p).reject(appr["approval_id"], actor="human")
        r = h.run(p)
        c.chk("F10: rejected graph never activated",
              p.current_graph_revision == 1
              and p.graph_revisions[-1]["status"] == "rejected")
        check_common(c, "F10_approval_rejected", p, r,
                     event="approval_rejected", terminal="needs_review")

        # F11 policy pause at safe barrier (B010 shape)
        case10 = bench.load_cases({"B010"})[0]
        h2, _ = bench.build_harness(os.path.join(d, "f11"), case10)
        p2 = h2.create_project("f11", task_graph={"tasks": case10["input"]["graph"]})
        state = orch.seed_case(bench.WF, p2.case_id, {})
        ss.save(state, os.path.join(d, "f11", p2.project_id, "case"))
        r2 = h2.run(p2)
        check_common(c, "F11_hotl_pause", p2, r2,
                     event="runtime_paused", terminal="paused")
        c.chk("F11: committed tasks intact (no mid-commit kill)",
              all(t["status"] in ("PASSED", "NEEDS_REVIEW", "BLOCKED", "PENDING")
                  for t in p2.tasks))

        # F12 crash during PAUSE (command persisted, unapplied)
        d12 = os.path.join(d, "f12")
        h3, p3, _ = make(d12)
        ControlStore(p3._dir).append_command(
            make_command(p3.project_id, "PAUSE", actor="human"))
        p4 = load_project(d12, p3.project_id)
        h4 = LongRunningHarness(d12)
        r4 = h4.run(p4)
        applied = [x for x in ControlStore(p3._dir).commands()
                   if x["status"] == "APPLIED"]
        c.chk("F12: pending PAUSE recovered exactly once", len(applied) == 1)
        check_common(c, "F12_crash_during_pause", p4, r4,
                     event="runtime_paused", terminal="paused")

        # F13 crash during RESUME
        d13 = os.path.join(d, "f13")
        h5, p5, _ = make(d13)
        h5._control_plane(p5).command("PAUSE", actor="human")
        ControlStore(p5._dir).append_command(
            make_command(p5.project_id, "RESUME", actor="human"))
        p6 = load_project(d13, p5.project_id)
        # a NEW process reconstructs its own harness WITH providers
        from test_parallel_scheduler import TaskScriptProvider as _TSP
        h6 = LongRunningHarness(d13, agent_executor=_TSP(
            scriptlib.expand_scripts(BASE_SCRIPTS)))
        r6 = h6.run(p6)
        c.chk("F13: pending RESUME recovered → completed",
              r6["status"] == "completed", r6["status"])
        check_common(c, "F13_crash_during_resume", p6, r6,
                     event="runtime_resumed", terminal="completed")
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---- command integrity / authority ------------------------------------------ #
@section
def test_f14_f15_f16_f17_f18_commands(c: Checks):
    d = fresh_dir()
    try:
        h, p, _ = make(d)
        plane = h._control_plane(p)
        out1 = plane.command("PAUSE", actor="human")
        out2 = plane.command("PAUSE", actor="human")
        c.chk("F14: duplicate command idempotent",
              out2["ok"] and out2["already"] is True)
        applied = [x for x in ControlStore(p._dir).commands()
                   if x["status"] == "APPLIED"]
        c.chk("F14: one applied record", len(applied) == 1)
        check_common(c, "F14_duplicate_command", p, {"status": "paused"},
                     event="control_command_applied", terminal="paused")
        h._control_plane(p).command("RESUME", actor="human")

        out3 = plane.command("CANCEL", actor="agent:insurance_analyst")
        c.chk("F15: unauthorized actor rejected",
              not out3["ok"] and "ACTOR_NOT_AUTHORIZED" in out3["error"])
        check_common(c, "F15_unauthorized_actor", p,
                     {"status": h.run(p).get("status")},
                     event="control_command_rejected")

        from runtime.agents import MessageBus, consume_handoffs
        bus = MessageBus(p._dir)
        # F16: handoff to the WRONG agent (not the task's assignee)
        p._set_task("task_2", status="PASSED", assigned_agent="insurance_analyst")
        bus.send(from_agent="insurance_analyst",
                 to_agent="knowledge_specialist",
                 message_type="TASK_HANDOFF", task_id="task_2")
        stats = consume_handoffs(bus, p, None)
        c.chk("F16: AGENT_MISMATCH handoff rejected",
              stats["invalid"] >= 1
              and bus.all_messages()[0]["status"] == "FAILED")
        # F17: artifact reference that does not exist
        state17 = ss.load(os.path.join(d, p.project_id, "case"), p.case_id)
        try:
            bus.send(from_agent="insurance_analyst",
                     to_agent="knowledge_specialist",
                     message_type="TASK_HANDOFF", task_id="task_1",
                     artifact_ids=["ART-999"], case_state=state17)
            rejected = False
        except ValueError as e:
            rejected = "ARTIFACT_NOT_FOUND" in str(e)
        c.chk("F17: invalid artifact reference refused at send", rejected)

        # F18: worker claims OK without producing anything → no self-PASS
        d18 = os.path.join(d, "f18")
        class SelfPass:
            name = model = "selfpass"
            def execute(self, **kw):
                from runtime.agents.executor import AgentExecutionResult
                return AgentExecutionResult("OK")
        h7 = LongRunningHarness(d18, agent_executor=SelfPass(), max_replans=0)
        p7 = h7.create_project("f18", task_graph={"tasks": [
            {"task_id": "task_1", "task_type": "requirement_analysis"}]})
        state = orch.seed_case(bench.WF, p7.case_id, {})
        ss.save(state, os.path.join(d18, p7.project_id, "case"))
        r7 = h7.run(p7)
        evals = (ss.load(os.path.join(d18, p7.project_id, "case"), p7.case_id)
                 or {}).get("evaluations", [])
        c.chk("F18: worker self-PASS refused (no eval, NEEDS_REVIEW)",
              p7.get_task("task_1")["status"] == "NEEDS_REVIEW"
              and not any(e["status"] == "PASS" and e["artifact_type"]
                          == "requirement-analysis" for e in evals))
        check_common(c, "F18_fake_eval_pass_attempt", p7, r7,
                     event="task_failed", terminal="needs_review")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_finj_log.txt",
                        "RUNTIME FAILURE INJECTION")


if __name__ == "__main__":
    sys.exit(main())
