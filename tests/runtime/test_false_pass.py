"""Phase 11 — False-pass adversarial suite (§11).

Each section deliberately feeds the system something BAD and proves it is
NOT wrongly accepted: bad artifacts, missing provenance, invalid products,
unknown task types / agents, invalid dependencies, forged eval PASS,
missing evidence, duplicate tasks, cycles, removed dependencies,
unauthorized commands, invalid A2A. false_pass_count must stay 0.
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

sys.path.insert(0, REPO)
from runtime import eval_engine as ev  # noqa: E402
from runtime import artifact_registry as reg  # noqa: E402
from runtime.planner import validator  # noqa: E402
from runtime.planner.planner import FakePlannerProvider  # noqa: E402
from runtime.agents import MessageBus, validate_assignment  # noqa: E402
from runtime.harness import LongRunningHarness  # noqa: E402

SECTIONS = []
FALSE_PASS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="fp_", dir=os.path.join(REPO, "tmp"))


def record(c, name, accepted_wrongly, detail=""):
    """accepted_wrongly=True would be a FALSE PASS — record it loudly."""
    c.chk(name, not accepted_wrongly, detail)
    if accepted_wrongly:
        FALSE_PASS.append(name)


# ------------------------------------------------------------------------- #
@section
def test_bad_artifact_and_provenance(c: Checks):
    rules = ev.load_rules()
    from runtime.state import transitions as _tr
    from runtime import orchestrator as _orch
    wf = _orch.load_workflow()
    risk_stage = _tr.stage_by_id(wf, "risk-analysis")  # carries the contract
    bad_artifact = {"payload": {}}          # missing required fields
    rec = ev.evaluate({"evaluations": [], "artifacts": {}, "artifact_registry": {}},
                      "risk-assessment", bad_artifact, risk_stage, rules=rules)
    record(c, "FP: bad artifact (empty risk-assessment) does not PASS",
           rec["status"] == "PASS", rec["checks"])

    # contamination: concrete product leak into an analysis artifact
    leak = {"payload": {"requirements": [
        {"requirement_id": "R1", "requirement_type": "medical",
         "summary": "需要购买 P001 demo-product", "priority": "P1_HIGH",
         "boundary": "requirement_only", "reason": "x", "source": "s"}]}}
    req_stage = _tr.stage_by_id(wf, "requirement-analysis")
    rec2 = ev.evaluate({"evaluations": [], "artifacts": {}, "artifact_registry": {}},
                       "requirement-analysis", leak, req_stage, rules=rules)
    record(c, "FP: product-contaminated analysis does not PASS",
           rec2["status"] == "PASS", rec2["checks"])

    # provenance: registered artifact whose fingerprint no longer matches
    state = {"artifacts": {"risk-assessment": {"payload": {"risks": []}}},
             "artifact_registry": {"risk-assessment": {
                 "artifact_id": "ART-001", "artifact_type": "risk-assessment",
                 "producer_skill": "s", "producer_stage": "st",
                 "input_artifacts": [], "status": "VALID",
                 "content_ref": "x", "fingerprint": "deadbeef",
                 "evidence_refs": []}},
             "evaluations": []}
    ok, problems = reg.verify(state)
    record(c, "FP: mutated artifact fails registry verification", ok, problems)

    # invalid product id in candidates → catalog invariant FAIL
    bad_product = {"candidates": [{"candidate_id": "C1", "product_id": "NOPE",
                                   "product_name": "x", "company": "y",
                                   "admissible": True}]}
    prod_stage = _tr.stage_by_id(wf, "product-candidate-provider")
    rec3 = ev.evaluate({"evaluations": [], "artifacts": {}, "artifact_registry": {}},
                       "product-candidates", bad_product, prod_stage, rules=rules)
    record(c, "FP: invalid product_id does not PASS catalog invariant",
           rec3["status"] == "PASS", rec3["checks"])


@section
def test_graph_and_assignment_false_pass(c: Checks):
    ok, errs = validator.validate_graph({"tasks": [
        {"task_id": "task_a", "task_type": "not_a_type"}]})
    record(c, "FP: unknown task_type rejected", ok, errs)

    ok, errs = validator.validate_graph({"tasks": [
        {"task_id": "task_a", "task_type": "client_profile"},
        {"task_id": "task_a", "task_type": "risk_analysis",
         "dependencies": ["task_a"]}]})
    record(c, "FP: duplicate task_id rejected", ok, errs)

    ok, errs = validator.validate_graph({"tasks": [
        {"task_id": "task_a", "task_type": "client_profile"},
        {"task_id": "task_b", "task_type": "risk_analysis",
         "dependencies": ["task_a"]},
        {"task_id": "task_c", "task_type": "coverage_gap",
         "dependencies": ["task_b", "task_a"]},
        {"task_id": "task_a2", "task_type": "solution",
         "dependencies": ["task_c", "task_b", "task_a"]}]})
    # craft an actual cycle: a→b→c→a
    ok, errs = validator.validate_graph({"tasks": [
        {"task_id": "task_a", "task_type": "risk_analysis",
         "dependencies": ["task_c", "task_0"]},
        {"task_id": "task_b", "task_type": "coverage_gap",
         "dependencies": ["task_a"]},
        {"task_id": "task_c", "task_type": "solution",
         "dependencies": ["task_b"]},
        {"task_id": "task_0", "task_type": "client_profile"}]})
    record(c, "FP: dependency cycle rejected", ok, errs)

    ok, errs = validator.validate_graph({"tasks": [
        {"task_id": "task_a", "task_type": "risk_analysis",
         "dependencies": ["task_ghost"]},
        {"task_id": "task_0", "task_type": "client_profile"}]})
    record(c, "FP: dependency on removed/unknown task rejected", ok, errs)

    ok, errs = validate_assignment("risk_analysis", "knowledge_specialist")
    record(c, "FP: wrong agent for task rejected", ok, errs)
    ok, errs = validate_assignment("risk_analysis", "agent_that_does_not_exist")
    record(c, "FP: unknown agent rejected", ok, errs)


@section
def test_message_and_command_false_pass(c: Checks):
    d = fresh_dir()
    try:
        h = LongRunningHarness(d)
        p = h.create_project("fp", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        bus = MessageBus(p._dir)
        try:
            bus.send(from_agent="insurance_analyst",
                     to_agent="report_specialist",   # policy-denied pair
                     message_type="TASK_HANDOFF")
            accepted = True
        except ValueError:
            accepted = False
        record(c, "FP: policy-denied A2A target refused", accepted)

        try:
            bus.send(from_agent="insurance_analyst",
                     to_agent="knowledge_specialist",
                     message_type="MAKE_COFFEE")     # not in the vocabulary
            accepted = True
        except ValueError:
            accepted = False
        record(c, "FP: unknown message type refused", accepted)

        out = h._control_plane(p).command("PAUSE", actor="agent:someone")
        record(c, "FP: agent-actor control command refused", out.get("ok"),
               out.get("error"))
        out = h._control_plane(p).command("RETRY_TASK", actor="human",
                                          payload={"task_id": "task_ghost"})
        record(c, "FP: retry of unknown task refused", out.get("ok"))
        p._set_task("task_a", status="PASSED")
        out = h._control_plane(p).command("RETRY_TASK", actor="human",
                                          payload={"task_id": "task_a"})
        record(c, "FP: retry of terminal-ok task refused", out.get("ok"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_forged_eval_pass(c: Checks):
    """A worker claiming OK without an artifact can never yield a PASS —
    the eval boundary refuses to invent quality."""
    d = fresh_dir()
    try:
        class SelfPass:
            name = model = "selfpass"
            def execute(self, **kw):
                from runtime.agents.executor import AgentExecutionResult
                return AgentExecutionResult("OK")
        h = LongRunningHarness(d, agent_executor=SelfPass(), max_replans=0)
        p = h.create_project("fp2", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "requirement_analysis"}]})
        from runtime import orchestrator as orch
        from runtime.state import store as ss
        state = orch.seed_case(orch.load_workflow(), p.case_id, {})
        ss.save(state, os.path.join(d, p.project_id, "case"))
        r = h.run(p)
        from runtime.state import store as ss2
        final = ss2.load(os.path.join(d, p.project_id, "case"), p.case_id) or {}
        passed = [e for e in final.get("evaluations", [])
                  if e["status"] == "PASS"]
        record(c, "FP: forged worker OK yields no eval PASS",
               bool(passed) or p.get_task("task_a")["status"] == "PASSED",
               (r["status"], passed))
        record(c, "FP: forged worker OK does not complete the task",
               p.get_task("task_a")["status"] in ("PASSED", "COMPLETED"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    code = run_sections(SECTIONS, "webui_test_false_pass_log.txt",
                        "RUNTIME FALSE-PASS SUITE")
    print("false_pass_count = %d" % len(FALSE_PASS))
    return code


if __name__ == "__main__":
    sys.exit(main())
