"""Phase 9 — Human-in-the-Loop Approval Gateway tests (T1–T28).

Covers: approval requests and persistence, the approval state machine,
permission boundaries (agents/planner/bus/tools cannot approve), approve →
Harness-resume activation, reject → fail-closed, idempotency, crash /
restart during approval, checkpoint integration, parallel-scheduler safe
barriers, eval-boundary preservation, determinism, and a four-agent
approval E2E.

The master flow reuses the Phase 8 replanning scenario with an
ApprovalPolicy installed: the validated replan candidate is high-impact
(it removes a task and reroutes a dependency) → the project pauses in
WAITING_HUMAN until a human approves and the Harness resumes.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_approval.py`.
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

import test_dynamic_replanning as PH8  # noqa: E402
from test_parallel_scheduler import TaskScriptProvider, load_state, cleanup  # noqa: E402
from runtime import orchestrator as orch
from runtime.approval import (ApprovalManager, ApprovalPolicy,  # noqa: E402
                              ApprovalStore, APPROVAL_REPLAN,
                              APPROVAL_EXTERNAL_ACTION, AUTO, HUMAN_APPROVAL,
                              create_request)
from runtime.harness import LongRunningHarness, load_project
from runtime.planner.planner import FakePlannerProvider

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="appr_", dir=os.path.join(REPO, "tmp"))


def make_approval_project(root, planner_graphs=None, max_concurrency=1,
                          max_replans=2, policy=None, graph=None):
    """Phase 8's master replanning scenario + the approval gateway on."""
    provider = TaskScriptProvider(copy.deepcopy(PH8.SCRIPTS))
    planner = FakePlannerProvider(
        list(planner_graphs if planner_graphs is not None
             else [PH8.graph_json(PH8.V2)]))
    h = LongRunningHarness(root, agent_executor=provider,
                           max_concurrency=max_concurrency,
                           max_replans=max_replans,
                           planner_provider=planner,
                           approval_policy=policy if policy is not None
                           else ApprovalPolicy())
    p = h.create_project("appr", task_graph=graph or copy.deepcopy(PH8.V1))
    state = orch.seed_case(WF, p.case_id, {})
    from runtime.state import store as ss
    ss.save(state, os.path.join(root, p.project_id, "case"))
    return h, p, provider


def run_waiting_flow(root, **kw):
    """Run until the replan pauses for a human. Returns (h, p, provider,
    result, approval)."""
    h, p, provider = make_approval_project(root, **kw)
    result = h.run(p)
    appr = ApprovalStore(p._dir).pending()
    return h, p, provider, result, (appr[0] if appr else None)


def events_of(p, etype):
    return [e for e in p.events() if e["event_type"] == etype]


def starts_of(p, tid):
    return [e for e in p.events()
            if e["event_type"] == "task_started" and e.get("task_id") == tid]


class FakeApprovalProvider:
    """§23: simulates the HUMAN decision — strictly THROUGH the real
    ApprovalManager (it cannot bypass state machine or permissions). Uses
    the harness's bridge-backed manager so decisions land in the project's
    durable event log like a real gateway adapter would."""

    def __init__(self, harness, project):
        self.project = project
        self.manager = harness._approval_manager(project)

    def approve(self, approval_id):
        return self.manager.approve(approval_id, actor="human")

    def reject(self, approval_id, reason="not allowed"):
        return self.manager.reject(approval_id, actor="human", reason=reason)


# ------------------------------------------------------------------------- #
# T1/T2 — create request + persistence
# ------------------------------------------------------------------------- #
@section
def test_t1_t2_create_and_persist(c: Checks):
    d = fresh_dir()
    try:
        h, p = LongRunningHarness(d), None
        p = h.create_project("t1", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        mgr = ApprovalManager(p._dir)
        appr = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN,
            reason="high-impact replan", task_id="task_a", graph_revision=2,
            context={"diff": {"added": ["task_x"]}}))
        c.chk("T1: request created PENDING", appr["status"] == "PENDING")
        for field in ("approval_id", "project_id", "task_id", "graph_revision",
                      "request_type", "reason", "context", "options",
                      "default_action", "status", "created_at", "resolved_at",
                      "resolved_by", "decision"):
            c.chk("T1: field %r present" % field, field in appr)
        # T2: persisted in approvals.jsonl, survives a new store instance
        path = os.path.join(p._dir, "approvals.jsonl")
        c.chk("T2: approvals.jsonl exists", os.path.exists(path))
        again = ApprovalStore(p._dir).get(appr["approval_id"])
        c.chk("T2: reload returns the same request", again == appr)
        c.chk("T2: list_pending sees it", len(ApprovalStore(p._dir).pending()) == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T3 — approval state machine (fail-closed transitions)
# ------------------------------------------------------------------------- #
@section
def test_t3_state_machine(c: Checks):
    d = fresh_dir()
    try:
        h = LongRunningHarness(d)
        p = h.create_project("t3", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        mgr = ApprovalManager(p._dir)
        appr = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN, reason="sm"))
        aid = appr["approval_id"]
        # PENDING → APPROVED directly is INVALID (must wait first)
        c.chk("T3: PENDING→APPROVED refused",
              not mgr.approve(aid, actor="human")["ok"])
        mgr.wait(aid)
        c.chk("T3: PENDING→WAITING_HUMAN ok",
              mgr.get(aid)["status"] == "WAITING_HUMAN")
        out = mgr.approve(aid, actor="human")
        c.chk("T3: WAITING_HUMAN→APPROVED ok",
              out["ok"] and mgr.get(aid)["status"] == "APPROVED")
        c.chk("T3: APPROVED→RESUMED via mark_resumed (Harness only)",
              mgr.mark_resumed(aid)["ok"]
              and mgr.get(aid)["status"] == "RESUMED")
        c.chk("T3: RESUMED is terminal (no further transitions)",
              not mgr.approve(aid, actor="human")["ok"]
              and not mgr.reject(aid)["ok"])
        # rejection path on a second request
        appr2 = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN, reason="sm2"))
        mgr.wait(appr2["approval_id"])
        mgr.reject(appr2["approval_id"], actor="human", reason="no")
        c.chk("T3: WAITING_HUMAN→REJECTED ok",
              mgr.get(appr2["approval_id"])["status"] == "REJECTED")
        c.chk("T3: REJECTED is terminal — approve after reject refused",
              not mgr.approve(appr2["approval_id"], actor="human")["ok"])
        # expiry path is fail-closed too
        appr3 = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN, reason="sm3"))
        mgr.wait(appr3["approval_id"])
        mgr.expire(appr3["approval_id"])
        c.chk("T3: WAITING_HUMAN→EXPIRED ok (explicit only)",
              mgr.get(appr3["approval_id"])["status"] == "EXPIRED")
        c.chk("T3: EXPIRED never continues (approve refused)",
              not mgr.approve(appr3["approval_id"], actor="human")["ok"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T4 — an agent-side layer may REQUEST an approval (reserved type)
# ------------------------------------------------------------------------- #
@section
def test_t4_agent_can_request(c: Checks):
    d = fresh_dir()
    try:
        h = LongRunningHarness(d)
        p = h.create_project("t4", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        mgr = h._approval_manager(p)
        appr = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_EXTERNAL_ACTION,
            reason="send_email requested by agent",
            requested_by="agent:knowledge_specialist",
            context={"action": "send_email"}))
        c.chk("T4: agent-originated REQUEST accepted (request-only)",
              appr["status"] == "PENDING"
              and appr["requested_by"] == "agent:knowledge_specialist")
        c.chk("T4: approval_requested event emitted",
              len(events_of(p, "approval_requested")) == 1)
        # and a request alone NEVER executes or resumes anything
        c.chk("T4: request changed no task state",
              p.get_task("task_a")["status"] == "PENDING")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T5/T6/T7 — nobody but a human may approve
# ------------------------------------------------------------------------- #
@section
def test_t5_t6_t7_permissions(c: Checks):
    d = fresh_dir()
    try:
        h = p = None
        h = LongRunningHarness(d)
        p = h.create_project("t5", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        mgr = ApprovalManager(p._dir)
        appr = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN, reason="sm"))
        mgr.wait(appr["approval_id"])
        aid = appr["approval_id"]
        # behavioral: non-human actors are refused by the allowlist
        c.chk("T5: agent actor refused",
              not mgr.approve(aid, actor="agent:insurance_analyst")["ok"])
        c.chk("T6: planner actor refused",
              not mgr.approve(aid, actor="planner:glm")["ok"])
        c.chk("T5: tool actor refused",
              not mgr.approve(aid, actor="tool:send_email")["ok"])
        c.chk("T7: message-bus actor refused",
              not mgr.approve(aid, actor="message_bus")["ok"])
        c.chk("permissions: still WAITING_HUMAN after refused attempts",
              mgr.get(aid)["status"] == "WAITING_HUMAN")
        # structural: agent/planner/bus layers have no approval capability
        import inspect
        from runtime.agents import executor as agents_executor
        from runtime.agent import tools as agent_tools
        from runtime.planner import planner as planner_mod
        from runtime.agents import message_bus as mb
        src = (inspect.getsource(agents_executor) + inspect.getsource(agent_tools)
               + inspect.getsource(planner_mod) + inspect.getsource(mb))
        # gateway-specific tokens — `orch.approve(` in tools.py is the
        # pre-existing STAGE-gate auto-approval (Phase 2.6 demo semantics),
        # a different mechanism from the Phase 9 approval gateway
        for banned in ("ApprovalManager", "ApprovalStore", "approval_id",
                       "resume_approval", "mark_resumed", "approval_policy",
                       "runtime.approval"):
            c.chk("T5-T7: agent/planner/bus layers never reference %r" % banned,
                  banned not in src)
        # messages cannot change approval state either
        from runtime.agents import MessageBus
        bus = MessageBus(p._dir)
        bus.send(from_agent="insurance_analyst",
                 to_agent="knowledge_specialist",
                 message_type="INFORMATION_REQUEST")
        c.chk("T7: messages did not resolve the approval",
              mgr.get(aid)["status"] == "WAITING_HUMAN")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T8 — approve + Harness resume activates the eligible graph
# ------------------------------------------------------------------------- #
@section
def test_t8_approve_activates(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        c.chk("T8: paused waiting for human",
              result["status"] == "waiting_approval" and appr is not None)
        human = FakeApprovalProvider(h, p)
        out = human.approve(appr["approval_id"])
        c.chk("T8: human approve ok", out["ok"])
        res = h.resume_approval(p, appr["approval_id"])
        c.chk("T8: resume completed the project",
              res["status"] == "completed", res["status"])
        c.chk("T8: approved graph became active (v2)",
              p.current_graph_revision == 2
              and p.get_task("task_risk") is None
              and p.get_task("task_risk2") is not None,
              [t["task_id"] for t in p.tasks])
        c.chk("T8: approval RESUMED",
              ApprovalStore(p._dir).get(appr["approval_id"])["status"] == "RESUMED")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T9 — reject fails closed; no alternative graph is generated
# ------------------------------------------------------------------------- #
@section
def test_t9_reject_fails_closed(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        human = FakeApprovalProvider(h, p)
        human.reject(appr["approval_id"], reason="not allowed")
        res = h.resume_approval(p, appr["approval_id"])
        c.chk("T9: resume after reject refused",
              res["status"] == "FAILED" and "APPROVED" in res["reason"], res)
        # a later run must not replan around the rejection (fail closed)
        r2 = h.run(p)
        c.chk("T9: no new replan after rejection",
              len(events_of(p, "replan_triggered")) == 1,
              len(events_of(p, "replan_triggered")))
        c.chk("T9: project surfaces needs_review, v1 intact",
              r2["status"] == "needs_review"
              and p.current_graph_revision == 1
              and [t["task_id"] for t in p.tasks] == PH8.V1_IDS,
              (r2["status"], [t["task_id"] for t in p.tasks]))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T10/T11 — idempotent approve; approve-after-reject refused
# ------------------------------------------------------------------------- #
@section
def test_t10_t11_idempotency(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        human = FakeApprovalProvider(h, p)
        first = human.approve(appr["approval_id"])
        second = human.approve(appr["approval_id"])
        c.chk("T10: double approve idempotent",
              first["ok"] and second["ok"] and second["already"] is True)
        c.chk("T10: exactly one approval_approved event",
              len(events_of(p, "approval_approved")) == 1)
        # T11: a rejected request can never be approved afterwards
        h2, p2, pr2, r2, appr2 = run_waiting_flow(os.path.join(d, "b"))
        human2 = FakeApprovalProvider(h2, p2)
        human2.reject(appr2["approval_id"])
        c.chk("T11: approve after reject refused",
              not human2.approve(appr2["approval_id"])["ok"])
        c.chk("T11: still REJECTED",
              ApprovalStore(p2._dir).get(appr2["approval_id"])["status"]
              == "REJECTED")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T12 — resume without approval is refused; waiting blocks plain run()
# ------------------------------------------------------------------------- #
@section
def test_t12_resume_requires_approval(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        res = h.resume_approval(p, appr["approval_id"])
        c.chk("T12: resume on WAITING_HUMAN refused",
              res["status"] == "FAILED"
              and "requires an APPROVED request" in res["reason"], res)
        calls_before = list(provider.calls)
        r2 = h.run(p)
        c.chk("T12: plain run() while waiting executes nothing",
              r2["status"] == "waiting_approval"
              and provider.calls == calls_before,
              (r2["status"], provider.calls[len(calls_before):]))
        c.chk("T12: v2 tasks never started while waiting",
              starts_of(p, "task_risk2") == [] and starts_of(p, "task_rep") == [])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T13/T14 — crash while waiting: state preserved, restart executes nothing
# ------------------------------------------------------------------------- #
@section
def test_t13_t14_crash_while_waiting(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        # a NEW process picks the project up from disk
        h2 = LongRunningHarness(d, agent_executor=None, approval_policy=ApprovalPolicy())
        p2 = load_project(d, p.project_id)
        appr2 = ApprovalStore(p2._dir).get(appr["approval_id"])
        c.chk("T13: approval survived the crash (WAITING_HUMAN)",
              appr2["status"] == "WAITING_HUMAN")
        c.chk("T13: candidate revision preserved as PENDING_APPROVAL",
              p2.graph_revisions[-1]["status"] == "pending_approval"
              and p2.graph_revisions[-1]["revision"] == 2)
        c.chk("T13: active graph still v1",
              p2.current_graph_revision == 1
              and [t["task_id"] for t in p2.tasks] == PH8.V1_IDS)
        # T14: restarting does NOT execute the waiting work
        provider2 = TaskScriptProvider(copy.deepcopy(PH8.SCRIPTS))
        h2.agent_executor = provider2
        r2 = h2.run(p2)
        c.chk("T14: restart returns waiting_approval without executing",
              r2["status"] == "waiting_approval"
              and provider2.calls == [], (r2["status"], provider2.calls))
        c.chk("T14: v2 tasks still never started",
              starts_of(p2, "task_risk2") == [])
        c.chk("T14: graph not activated by the restart",
              p2.current_graph_revision == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T15/T16 — explicit approve resumes; no duplicate execution after resume
# ------------------------------------------------------------------------- #
@section
def test_t15_t16_resume_and_no_duplicates(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        FakeApprovalProvider(h, p).approve(appr["approval_id"])
        res = h.resume_approval(p, appr["approval_id"])
        c.chk("T15: resume executed the approved graph to completion",
              res["status"] == "completed", res["status"])
        c.chk("T15: each task started exactly once across pause+resume",
              all(len(starts_of(p, t)) == 1 for t in
                  ("task_cli", "task_req", "task_risk2", "task_rep")),
              {t: len(starts_of(p, t)) for t in
               ("task_cli", "task_req", "task_risk2", "task_rep")})
        # T16: a second resume neither re-activates nor re-executes
        res2 = h.resume_approval(p, appr["approval_id"])
        c.chk("T16: second resume is a no-op (already_resumed)",
              res2.get("already_resumed") is True and res2["status"] == "completed",
              res2.get("status"))
        c.chk("T16: still exactly one start per task",
              all(len(starts_of(p, t)) == 1 for t in
                  ("task_cli", "task_req", "task_risk2", "task_rep")))
        c.chk("T16: no duplicate graph activation",
              p.current_graph_revision == 2
              and len([r for r in p.graph_revisions if r["revision"] == 2]) == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T17 — approval lifecycle event integrity
# ------------------------------------------------------------------------- #
@section
def test_t17_event_integrity(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        FakeApprovalProvider(h, p).approve(appr["approval_id"])
        h.resume_approval(p, appr["approval_id"])
        for etype, n in (("approval_requested", 1), ("approval_waiting", 1),
                         ("approval_approved", 1), ("approval_resumed", 1)):
            evs = events_of(p, etype)
            c.chk("T17: exactly %d %s" % (n, etype), len(evs) == n,
                  (etype, len(evs)))
        req = events_of(p, "approval_requested")[0]
        for field in ("project_id", "approval_id", "graph_revision",
                      "request_type"):
            c.chk("T17: %s carries %r" % (etype, field), field in req)
        evs = p.events()
        order = {}
        for i, e in enumerate(evs):
            if e["event_type"] not in order:
                order[e["event_type"]] = i
        c.chk("T17: order requested < waiting < approved < resumed",
              order["approval_requested"] < order["approval_waiting"]
              < order["approval_approved"] < order["approval_resumed"])
        c.chk("T17: events correlate on approval_id",
              all(e.get("approval_id") == appr["approval_id"]
                  for e in events_of(p, "approval_approved")
                  + events_of(p, "approval_resumed")))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T18 — checkpoint records approval state
# ------------------------------------------------------------------------- #
@section
def test_t18_checkpoint(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        cps = p.checkpoints()
        waiting_cp = [cp for cp in cps
                      if cp.get("approval_id") == appr["approval_id"]]
        c.chk("T18: a WAITING_HUMAN checkpoint exists",
              len(waiting_cp) == 1, len(waiting_cp))
        if waiting_cp:
            cp = waiting_cp[0]
            c.chk("T18: checkpoint carries approval_status + graph_revision",
                  cp.get("approval_status") == "WAITING_HUMAN"
                  and cp.get("graph_revision") == 1, cp)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T19/T20 — policy decides; low-impact stays automatic
# ------------------------------------------------------------------------- #
@section
def test_t19_t20_policy(c: Checks):
    d = fresh_dir()
    try:
        policy = ApprovalPolicy()  # default threshold: 2 added tasks
        high_removed = {"added": ["task_x"], "removed": ["task_core"],
                        "preserved": [], "rerun": [],
                        "dependency_changes": []}
        high_deps = {"added": [], "removed": [],
                     "preserved": ["task_a"], "rerun": [],
                     "dependency_changes": [{"task_id": "task_a",
                                             "from": [], "to": ["task_b"]}]}
        high_count = {"added": ["a", "b", "c"], "removed": [],
                      "preserved": [], "rerun": [], "dependency_changes": []}
        low = {"added": ["task_x"], "removed": [], "preserved": ["task_a"],
               "rerun": [], "dependency_changes": []}
        c.chk("T19: removed task → HUMAN",
              policy.evaluate_replan(high_removed, None)
              == (HUMAN_APPROVAL, policy.evaluate_replan(high_removed, None)[1]))
        c.chk("T19: dependency change → HUMAN",
              policy.evaluate_replan(high_deps, None)[0] == HUMAN_APPROVAL)
        c.chk("T19: added > threshold → HUMAN",
              policy.evaluate_replan(high_count, None)[0] == HUMAN_APPROVAL)
        c.chk("T20: low-impact diff → AUTO",
              policy.evaluate_replan(low, None)[0] == AUTO)
        c.chk("T20: disabled gateway → AUTO everywhere",
              ApprovalPolicy(enabled=False).evaluate_replan(
                  high_removed, None)[0] == AUTO)
        # integrated: no policy installed → replan applies automatically
        # (Phase 8 behaviour preserved — the gateway never blocks by default)
        h, p, provider, planner = PH8.make_replan_project(
            os.path.join(d, "auto"), [PH8.graph_json(PH8.V2)])
        r = h.run(p)
        c.chk("T20: without a policy the same replan is automatic",
              r["status"] == "completed" and p.current_graph_revision == 2
              and p.replans[0]["status"] == "accepted",
              (r["status"], p.replans[0]["status"]))
        c.chk("T20: no approval requested without the gateway",
              ApprovalStore(p._dir).all() == [])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T21/T22 — rejected graph never activates; revisions stay immutable
# ------------------------------------------------------------------------- #
@section
def test_t21_t22_graph_integrity(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        v1_snapshot = copy.deepcopy(p.graph_revisions[0])
        FakeApprovalProvider(h, p).reject(appr["approval_id"])
        h.run(p)  # sync the rejection into the ledger
        c.chk("T21: rejected graph never became active",
              p.current_graph_revision == 1
              and [t["task_id"] for t in p.tasks] == PH8.V1_IDS)
        c.chk("T21: candidate revision marked rejected",
              p.graph_revisions[-1]["status"] == "rejected")
        c.chk("T21: replan ledger records the rejection",
              p.replans[0]["status"] == "rejected", p.replans[0]["status"])
        c.chk("T22: v1 snapshot immutable across wait + reject + rerun",
              p.graph_revisions[0] == v1_snapshot)
        # T22 across the approve path too
        h2, p2, pr2, r2, appr2 = run_waiting_flow(os.path.join(d, "b"))
        v1b = copy.deepcopy(p2.graph_revisions[0])
        FakeApprovalProvider(h2, p2).approve(appr2["approval_id"])
        h2.resume_approval(p2, appr2["approval_id"])
        c.chk("T22: v1 snapshot immutable across approve + resume",
              p2.graph_revisions[0] == v1b)
        c.chk("T22: activation flipped only the revision status",
              p2.graph_revisions[1]["status"] == "active"
              and p2.graph_revisions[1]["revision"] == 2)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T23/T24 — parallel scheduler: approval only at the safe barrier;
#           workers never execute against an unapproved graph
# ------------------------------------------------------------------------- #
@section
def test_t23_t24_parallel_barrier(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(
            d, max_concurrency=2)
        c.chk("T23: parallel run pauses for approval",
              result["status"] == "waiting_approval" and appr is not None)
        evs = p.events()
        last_terminal = max(
            (i for i, e in enumerate(evs)
             if e["event_type"] in ("task_completed", "task_failed")), default=-1)
        req = next((i for i, e in enumerate(evs)
                    if e["event_type"] == "approval_requested"), -1)
        c.chk("T23: approval requested only after the round settled",
              req > last_terminal, (req, last_terminal))
        between = [e for e in evs[last_terminal:req]
                   if e["event_type"] == "task_started"]
        c.chk("T23: no execution between settle and approval request",
              between == [], between)
        # T24: nothing executed against the unapproved v2
        c.chk("T24: workers never executed unapproved-graph tasks",
              starts_of(p, "task_risk2") == [] and starts_of(p, "task_rep") == [])
        c.chk("T24: active graph still v1 while waiting",
              p.current_graph_revision == 1)
        # after approve+resume the approved graph executes normally
        FakeApprovalProvider(h, p).approve(appr["approval_id"])
        res = h.resume_approval(p, appr["approval_id"])
        c.chk("T24: approved graph executes after resume (parallel mode)",
              res["status"] == "completed"
              and len(starts_of(p, "task_risk2")) == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T25 — approval never bypasses Eval
# ------------------------------------------------------------------------- #
@section
def test_t25_eval_boundary(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        evals_before = [e["eval_id"] for e in
                        (load_state(d, p) or {}).get("evaluations", [])]
        FakeApprovalProvider(h, p).approve(appr["approval_id"])
        h.resume_approval(p, appr["approval_id"])
        final = load_state(d, p) or {}
        evals_after = final.get("evaluations") or []
        # the already-evaluated artifacts are NOT re-evaluated by the resume
        # (approval changed scheduling, not quality decisions)
        before_types = [e["artifact_type"] for e in final.get("evaluations", [])
                        if e["eval_id"] in evals_before]
        c.chk("T25: prior evals unchanged by approval/resume",
              all(e["status"] == "PASS" for e in evals_after
                  if e["eval_id"] in evals_before))
        # the new task's artifact went through the SAME Harness eval
        new_evals = [e for e in evals_after if e["eval_id"] not in evals_before]
        c.chk("T25: new work still eval-gated (risk-assessment eval exists)",
              any(e["artifact_type"] == "risk-assessment" for e in new_evals),
              [e["artifact_type"] for e in new_evals])
        c.chk("T25: every PASS has a real eval record",
              all(any(e["artifact_type"] == t and e["status"] == "PASS"
                      for e in evals_after)
                  for t in ("client-profile", "requirement-analysis",
                            "risk-assessment", "insurance-report")))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T26 — four-agent E2E with a full approval lifecycle
# ------------------------------------------------------------------------- #
@section
def test_t26_four_agent_approval_e2e(c: Checks):
    d = fresh_dir()
    try:
        provider = TaskScriptProvider(copy.deepcopy(PH8.T24_SCRIPTS))
        planner = FakePlannerProvider([PH8.graph_json(PH8.T24_V2)])
        h = LongRunningHarness(d, agent_executor=provider,
                               planner_provider=planner,
                               approval_policy=ApprovalPolicy())
        p = h.create_project("e2e-appr", task_graph=copy.deepcopy(PH8.T24_V1))
        state = orch.seed_case(WF, p.case_id, {})
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))
        r1 = h.run(p)
        appr = ApprovalStore(p._dir).pending()
        c.chk("T26: run paused at WAITING_HUMAN (project NOT completed)",
              r1["status"] == "waiting_approval" and len(appr) == 1, r1["status"])
        appr = appr[0]
        evs = p.events()
        started = {e.get("agent_id") for e in evs
                   if e["event_type"] == "agent_started"}
        c.chk("T26: 3 specialists executed before the pause",
              started == {"insurance_analyst", "knowledge_specialist",
                          "product_specialist"}, started)
        # human approves → Harness resumes → report specialist completes
        FakeApprovalProvider(h, p).approve(appr["approval_id"])
        r2 = h.resume_approval(p, appr["approval_id"])
        started = {e.get("agent_id") for e in p.events()
                   if e["event_type"] == "agent_started"}
        c.chk("T26: all 4 specialists after resume",
              started == {"insurance_analyst", "knowledge_specialist",
                          "product_specialist", "report_specialist"}, started)
        c.chk("T26: project COMPLETED after approval",
              r2["status"] == "completed", r2["status"])
        final = load_state(d, p) or {}
        c.chk("T26: report artifact produced",
              "insurance-report" in (final.get("artifacts") or {}))
        c.chk("T26: full lifecycle observed",
              all(len(events_of(p, t)) == 1 for t in
                  ("approval_requested", "approval_waiting",
                   "approval_approved", "approval_resumed")))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T27 — crash/restart across the approval lifecycle (incl. approved-not-
#       resumed): nothing executes until the Harness resumes
# ------------------------------------------------------------------------- #
@section
def test_t27_crash_restart_lifecycle(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, result, appr = run_waiting_flow(d)
        # human approves in "another process"; crash before Harness resume
        ApprovalManager(p._dir).approve(appr["approval_id"], actor="human")
        h2 = LongRunningHarness(d, approval_policy=ApprovalPolicy())
        p2 = load_project(d, p.project_id)
        provider2 = TaskScriptProvider(copy.deepcopy(PH8.SCRIPTS))
        h2.agent_executor = provider2
        r2 = h2.run(p2)
        c.chk("T27: approved-but-not-resumed still blocks plain run()",
              r2["status"] == "waiting_approval" and provider2.calls == [],
              (r2["status"], provider2.calls))
        c.chk("T27: graph not activated by the restart",
              p2.current_graph_revision == 1)
        # the explicit Harness resume is the only path onward
        res = h2.resume_approval(p2, appr["approval_id"])
        c.chk("T27: resume after restart completes",
              res["status"] == "completed", res["status"])
        c.chk("T27: approval RESUMED exactly once",
              ApprovalStore(p2._dir).get(appr["approval_id"])["status"]
              == "RESUMED")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T28 — deterministic approval decisions
# ------------------------------------------------------------------------- #
@section
def test_t28_determinism(c: Checks):
    runs = []
    for i in range(3):
        d = fresh_dir()
        try:
            h, p, provider, result, appr = run_waiting_flow(d)
            runs.append({
                "status": result["status"],
                "request_type": appr["request_type"],
                "fingerprint": appr["context"]["candidate_fingerprint"],
                "revision": appr["graph_revision"],
                "diff": p.replans[0]["diff"],
                "outcome": ApprovalPolicy().evaluate_replan(
                    p.replans[0]["diff"], p)[0],
            })
        finally:
            cleanup(d)
    first = runs[0]
    c.chk("T28: same decision requirement every run",
          all(r["outcome"] == HUMAN_APPROVAL for r in runs))
    c.chk("T28: same request type + revision",
          all(r["request_type"] == first["request_type"]
              and r["revision"] == first["revision"] for r in runs))
    c.chk("T28: same candidate fingerprint",
          all(r["fingerprint"] == first["fingerprint"] for r in runs))
    c.chk("T28: same diff + status",
          all(r["diff"] == first["diff"]
              and r["status"] == first["status"] for r in runs))



# ------------------------------------------------------------------------- #
# API — minimal human-approval endpoints (state only, idempotent)
# ------------------------------------------------------------------------- #
@section
def test_api_approval_endpoints(c: Checks):
    d = fresh_dir()
    old_root = os.environ.get("INSURANCE_AGENT_HARNESS_ROOT")
    try:
        h, p = LongRunningHarness(d), None
        p = h.create_project("api", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        mgr = h._approval_manager(p)
        appr = mgr.create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN,
            reason="api smoke", graph_revision=2))
        mgr.wait(appr["approval_id"])
        os.environ["INSURANCE_AGENT_HARNESS_ROOT"] = d
        from _common import make_client
        client, m, bus = make_client()
        r = client.get("/api/projects/%s/approvals" % p.project_id)
        c.chk("API: list 200 with one approval",
              r.status_code == 200 and len(r.json()["approvals"]) == 1)
        aid = appr["approval_id"]
        r = client.get("/api/approvals/%s" % aid)
        c.chk("API: get 200 WAITING_HUMAN",
              r.status_code == 200
              and r.json()["approval"]["status"] == "WAITING_HUMAN")
        r = client.get("/api/approvals/appr_nope")
        c.chk("API: unknown approval 404", r.status_code == 404)
        r = client.post("/api/approvals/%s/approve" % aid,
                        json={"actor": "agent:insurance_analyst"})
        c.chk("API: agent actor refused (409)",
              r.status_code == 409
              and "ACTOR_NOT_AUTHORIZED" in r.json().get("error", ""))
        r = client.post("/api/approvals/%s/approve" % aid,
                        json={"actor": "human"})
        c.chk("API: human approve 200 APPROVED",
              r.status_code == 200
              and r.json()["result"]["approval"]["status"] == "APPROVED")
        r = client.post("/api/approvals/%s/approve" % aid,
                        json={"actor": "human"})
        c.chk("API: approve idempotent",
              r.status_code == 200 and r.json()["result"]["already"] is True)
        # state-only: the API decision alone did not activate/execute anything
        c.chk("API: decision alone activated no graph",
              p.current_graph_revision == 1)
    finally:
        if old_root is None:
            os.environ.pop("INSURANCE_AGENT_HARNESS_ROOT", None)
        else:
            os.environ["INSURANCE_AGENT_HARNESS_ROOT"] = old_root
        cleanup(d)


def main():
    return run_sections(SECTIONS, "webui_test_approval_log.txt",
                        "RUNTIME APPROVAL GATEWAY")


if __name__ == "__main__":
    sys.exit(main())
