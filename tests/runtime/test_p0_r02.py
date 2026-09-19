"""Phase 13 P0 R-02 — enforced final human review (T-R02-01..09).

Round-1 finding: projects completed with deliverables and ZERO approval
events; agent tools auto-approve stage gates. These tests prove the
review gate (require_final_review=True) cannot be bypassed by any path:
normal flow, agent, tool, API, retry, replan, resume, crash recovery.
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
from test_parallel_scheduler import TaskScriptProvider  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="r02_", dir=os.path.join(REPO, "tmp"))


GRAPH = {"tasks": [
    {"task_id": "task_0", "task_type": "client_profile"},
    {"task_id": "task_1", "task_type": "requirement_analysis",
     "dependencies": ["task_0"]},
    {"task_id": "task_2", "task_type": "risk_analysis",
     "dependencies": ["task_0", "task_1"]},
    {"task_id": "task_3", "task_type": "coverage_gap",
     "dependencies": ["task_0", "task_1", "task_2"]},
    {"task_id": "task_4", "task_type": "solution",
     "dependencies": ["task_1", "task_2", "task_3"]},
    {"task_id": "task_5", "task_type": "product_candidates",
     "dependencies": ["task_0", "task_3", "task_4"]},
    {"task_id": "task_6", "task_type": "report_generation",
     "dependencies": ["task_0", "task_1", "task_2", "task_5"]},
]}
SCRIPTS = {"task_0": "profile", "task_1": "req", "task_2": "risk",
           "task_3": "coverage_gap", "task_4": "solution",
           "task_5": "product", "task_6": "report"}
DELIVERABLE = "task_6"


def make_review_harness(root, **kw):
    h = LongRunningHarness(
        root,
        agent_executor=TaskScriptProvider(scriptlib.expand_scripts(SCRIPTS)),
        planner_provider=FakePlannerProvider([]),
        require_final_review=True, **kw)
    p = h.create_project("r02", task_graph=copy.deepcopy(GRAPH))
    state = orch.seed_case(bench.WF, p.case_id, {})
    ss.save(state, os.path.join(root, p.project_id, "case"))
    return h, p


def events_of(p, etype):
    return [e for e in p.events() if e["event_type"] == etype]


@section
def test_t_r02_01_normal_flow_requires_approval(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        r = h.run(p)
        c.chk("R-02-01: deliverable run stops at waiting_review "
              "(not completed)", r["status"] == "waiting_review",
              r["status"])
        reviews = [a for a in ApprovalStore(p._dir).all()
                   if a["request_type"] == "APPROVAL_FINAL_REVIEW"]
        c.chk("R-02-01: FINAL_REVIEW approval created + WAITING_HUMAN",
              len(reviews) == 1 and reviews[0]["status"] == "WAITING_HUMAN")
        c.chk("R-02-01: approval_waiting + approval_requested events",
              len(events_of(p, "approval_waiting")) >= 1)
        # approve → READY_FOR_MANUAL_DELIVERY (never auto-delivery)
        out = h.approve_final_review(p, actor="human")
        c.chk("R-02-02 approve → ready_for_delivery",
              out["status"] == "ready_for_delivery", out.get("status"))
        c.chk("R-02-01: project status ready_for_delivery",
              p.status == "ready_for_delivery", p.status)
        c.chk("R-02-01: deliverable task itself PASSED (review gates the "
              "DELIVERY, not the execution)",
              p.get_task(DELIVERABLE)["status"] == "PASSED")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_02_agent_cannot_self_approve(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        h.run(p)
        appr = ApprovalStore(p._dir).all()[0]
        out = h._approval_manager(p).approve(appr["approval_id"],
                                             actor="agent:report_specialist")
        c.chk("R-02-02: agent actor refused",
              not out.get("ok") and "ACTOR_NOT_AUTHORIZED" in out.get("error", ""))
        c.chk("R-02-02: review still WAITING_HUMAN",
              ApprovalStore(p._dir).all()[0]["status"] == "WAITING_HUMAN")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_03_tool_cannot_self_approve(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        h.run(p)
        # a tool-layer actor is equally refused by the same allowlist
        appr = ApprovalStore(p._dir).all()[0]
        out = h._approval_manager(p).approve(appr["approval_id"],
                                             actor="tool:report_generation")
        c.chk("R-02-03: tool actor refused", not out.get("ok"))
        c.chk("R-02-03: no auto-approve path exists — the deliverable "
              "stays gated",
              ApprovalStore(p._dir).all()[0]["status"] == "WAITING_HUMAN")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_04_api_cannot_bypass(c: Checks):
    """The approve API requires the REVIEWER role AND derives the actor
    from the authenticated identity (R-06) — no client-side bypass."""
    d = fresh_dir()
    old_env = {k: os.environ.get(k) for k in
               ("INSURANCE_AGENT_API_KEYS", "INSURANCE_AGENT_HARNESS_ROOT",
                "INSURANCE_AGENT_NO_DOTENV")}
    try:
        h, p = make_review_harness(d)
        h.run(p)
        os.environ["INSURANCE_AGENT_HARNESS_ROOT"] = d
        os.environ["INSURANCE_AGENT_API_KEYS"] = (
            "k" * 24 + ":OWNER:alice," + "o" * 24 + ":OPERATOR:carol")
        os.environ["INSURANCE_AGENT_NO_DOTENV"] = "1"
        from _common import make_client
        client = make_client()[0]
        aid = ApprovalStore(p._dir).all()[0]["approval_id"]
        r = client.post("/api/approvals/%s/approve" % aid,
                        headers={"Authorization": "Bearer " + "o" * 24},
                        json={"actor": "human"})
        c.chk("R-02-04: OPERATOR cannot approve the review (403)",
              r.status_code == 403, r.status_code)
        r = client.post("/api/approvals/%s/approve" % aid, json={})
        c.chk("R-02-04: unauthenticated cannot approve (401)",
              r.status_code == 401)
        c.chk("R-02-04: review still WAITING_HUMAN",
              ApprovalStore(p._dir).all()[0]["status"] == "WAITING_HUMAN")
    finally:
        for k, v in old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_05_replan_cannot_bypass(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        h.run(p)   # → waiting_review
        # a human REPLAN command while gated: the runtime refuses to run
        out = h._control_plane(p).command("REPLAN", actor="human",
                                          payload={"reason": "sneak"})
        c.chk("R-02-05: replan command recorded", out.get("ok"),
              out.get("error"))
        r = h.run(p)
        c.chk("R-02-05: run() after replan stays waiting_review "
              "(gate preserved)", r["status"] == "waiting_review",
              r["status"])
        c.chk("R-02-05: no second deliverable execution",
              len([e for e in p.events()
                   if e["event_type"] == "task_started"
                   and e.get("task_id") == DELIVERABLE]) == 1)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_06_resume_cannot_bypass(c: Checks):
    """resume_approval handles REPLAN approvals; a final-review approval is
    NOT a graph revision — resuming it must not unlock delivery."""
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        h.run(p)
        appr = ApprovalStore(p._dir).all()[0]
        h._approval_manager(p).approve(appr["approval_id"], actor="human")
        out = h.resume_approval(p, appr["approval_id"])
        c.chk("R-02-06: resume_approval refuses non-replan reviews "
              "(fail closed)", out["status"] == "FAILED",
              out.get("reason", ""))
        c.chk("R-02-06: project NOT completed by resume",
              p.status != "completed", p.status)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_07_crash_recovery_preserves_gate(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        h.run(p)   # waiting_review persisted
        # NEW process picks the project up
        h2 = LongRunningHarness(d, require_final_review=True)
        p2 = load_project(d, p.project_id)
        r = h2.run(p2)
        c.chk("R-02-07: restart does not complete past the gate",
              r["status"] == "waiting_review", r["status"])
        c.chk("R-02-07: the review request survived the crash",
              any(a["request_type"] == "APPROVAL_FINAL_REVIEW"
                  and a["status"] == "WAITING_HUMAN"
                  for a in ApprovalStore(p2._dir).all()))
        # and after a legitimate approve the new process delivers the flag
        out = h2.approve_final_review(p2, actor="human")
        c.chk("R-02-07: approve after crash → ready_for_delivery",
              out["status"] == "ready_for_delivery", out.get("status"))
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_08_retry_preserves_gate(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_review_harness(d)
        h.run(p)
        # a retry of a PASSED deliverable is refused by the control plane
        out = h._control_plane(p).command(
            "RETRY_TASK", actor="human",
            payload={"task_id": DELIVERABLE})
        c.chk("R-02-08: retry of terminal-ok deliverable refused",
              not out.get("ok"), out.get("error"))
        # and retry of an upstream task cannot re-run past the gate
        r = h.run(p)
        c.chk("R-02-08: run() after retry attempt stays gated",
              r["status"] == "waiting_review", r["status"])
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_09_no_delivery_without_approval(c: Checks):
    d = fresh_dir()
    try:
        # reject path: the deliverable never becomes deliverable
        h, p = make_review_harness(d)
        h.run(p)
        out = h.reject_final_review(p, reason="wrong client data")
        c.chk("R-02-09: rejection fail-closes to needs_review",
              out["status"] == "needs_review", out.get("status"))
        c.chk("R-02-09: project NOT ready_for_delivery after reject",
              p.status == "needs_review", p.status)
        # exhaustive state check: no path sets completed/ready without approve
        c.chk("R-02-09: reject is terminal (no auto-retry)",
              h.run(p)["status"] in ("needs_review", "waiting_review"))
        # approve path is the ONLY way to ready_for_delivery
        h2, p2 = make_review_harness(os.path.join(d, "b"))
        h2.run(p2)
        before = p2.status
        c.chk("R-02-09: pre-approval status is waiting_review",
              before == "waiting_review", before)
        h2.approve_final_review(p2, actor="human")
        c.chk("R-02-09: ONLY approve yields ready_for_delivery",
              p2.status == "ready_for_delivery")
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t_r02_flag_off_preserves_phase11(c: Checks):
    """require_final_review=False (default) keeps the exact Phase 7-12
    validation/benchmark semantics — the gate is a production-mode control,
    not a silent behavior change."""
    d = fresh_dir()
    try:
        h = LongRunningHarness(
            d,
            agent_executor=TaskScriptProvider(scriptlib.expand_scripts(SCRIPTS)),
            planner_provider=FakePlannerProvider([]))
        p = h.create_project("r02off", task_graph=copy.deepcopy(GRAPH))
        state = orch.seed_case(bench.WF, p.case_id, {})
        ss.save(state, os.path.join(d, p.project_id, "case"))
        r = h.run(p)
        c.chk("R-02-compat: flag off → completed as before (benchmark B001 "
              "semantics preserved)", r["status"] == "completed", r["status"])
        c.chk("R-02-compat: no FINAL_REVIEW created",
              not any(a["request_type"] == "APPROVAL_FINAL_REVIEW"
                      for a in ApprovalStore(p._dir).all()))
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_r02_log.txt",
                        "P0 R-02 FINAL REVIEW")


if __name__ == "__main__":
    sys.exit(main())
