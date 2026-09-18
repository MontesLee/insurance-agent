"""Phase 8 — Dynamic Replanning V0.1 tests (T1–T24).

Covers: deterministic triggers, safe-barrier enforcement, ReplanContext,
planner re-invocation + validation + bounded retry, graph revisions and
lineage immutability, completed-work preservation, artifact reuse,
deterministic graph diff, replan budget, no-change loop protection,
fail-closed planner failure, checkpoint/recovery, parallel + sequential
compatibility, A2A/agent authority boundaries, event integrity,
determinism and a realistic four-agent replan E2E.

The master flow runs the REAL SpecialistAgentExecutor: v1's risk task
fails without producing an artifact (plain-text reply → AGENT_FAILED),
the report task is BLOCKED, the Harness replans at the safe barrier, and
v2 retries the failed step under a NEW task id and completes the report.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_dynamic_replanning.py`.
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

from test_parallel_scheduler import (GOOD, BAD_PRODUCT, ScriptAgentExecutor,  # noqa: E402
                                     TaskScriptProvider, load_state, cleanup,
                                     RISK_ARGS, REQ_ARGS, PROFILE_ARGS)
from runtime import orchestrator as orch
from runtime.harness import LongRunningHarness, load_project
from runtime.planner.planner import FakePlannerProvider

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="replan_", dir=os.path.join(REPO, "tmp"))


def graph_json(g):
    return json.dumps(g, ensure_ascii=False)


# ------------------------------------------------------------------------- #
# The master flow (real executor). Both graphs satisfy the trusted
# registry's artifact contract (every required input produced upstream),
# so v2 passes the SAME Graph Validator as a fresh plan.
# ------------------------------------------------------------------------- #
V1 = {"tasks": [
    {"task_id": "task_cli", "task_type": "client_profile"},
    {"task_id": "task_req", "task_type": "requirement_analysis",
     "dependencies": ["task_cli"]},
    {"task_id": "task_risk", "task_type": "risk_analysis",
     "dependencies": ["task_cli", "task_req"]},
    {"task_id": "task_rep", "task_type": "report_generation",
     "dependencies": ["task_cli", "task_req", "task_risk"]},
], "source_request": "分析风险并生成报告"}

V2 = {"tasks": [
    {"task_id": "task_cli", "task_type": "client_profile"},
    {"task_id": "task_req", "task_type": "requirement_analysis",
     "dependencies": ["task_cli"]},
    # the failed step retried under a NEW task id (task_risk removed)
    {"task_id": "task_risk2", "task_type": "risk_analysis",
     "dependencies": ["task_cli", "task_req"]},
    {"task_id": "task_rep", "task_type": "report_generation",
     "dependencies": ["task_cli", "task_req", "task_risk2"]},
]}

V1_IDS = ["task_cli", "task_req", "task_risk", "task_rep"]

SCRIPTS = {
    "task_cli": [("record_client_profile", PROFILE_ARGS), "done"],
    "task_req": [("record_requirement_analysis", REQ_ARGS), "done"],
    # plain-text reply → no artifact → AGENT_FAILED → NEEDS_REVIEW
    "task_risk": ["无法完成风险分析，信息不足。"],
    "task_risk2": [("record_risk_assessment", RISK_ARGS), "done"],
    "task_rep": [("report_generation", {}), "done"],
}


def make_replan_project(root, planner_graphs, scripts=None, graph=None,
                        max_concurrency=1, max_replans=2):
    """Harness wired with the REAL specialist executor (scripted per task)
    + FakePlannerProvider for deterministic replans."""
    provider = TaskScriptProvider(copy.deepcopy(scripts or SCRIPTS))
    planner = FakePlannerProvider(list(planner_graphs))
    h = LongRunningHarness(root, agent_executor=provider,
                           max_concurrency=max_concurrency,
                           max_replans=max_replans,
                           planner_provider=planner)
    p = h.create_project("replan", task_graph=graph or copy.deepcopy(V1))
    state = orch.seed_case(WF, p.case_id, {})
    from runtime.state import store as ss
    ss.save(state, os.path.join(root, p.project_id, "case"))
    return h, p, provider, planner


def run_master_flow(root, max_concurrency=1, scripts=None):
    h, p, provider, planner = make_replan_project(
        root, [graph_json(V2)], scripts=scripts,
        max_concurrency=max_concurrency)
    result = h.run(p)
    return h, p, provider, planner, result


def events_of(p, etype):
    return [e for e in p.events() if e["event_type"] == etype]


def starts_of(p, tid):
    """Authoritative per-task execution count (task_started events)."""
    return [e for e in p.events()
            if e["event_type"] == "task_started" and e.get("task_id") == tid]


# ------------------------------------------------------------------------- #
# T1 — deterministic replan trigger
# ------------------------------------------------------------------------- #
@section
def test_t1_replan_trigger(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        trig = events_of(p, "replan_triggered")
        c.chk("T1: deterministic trigger fired", len(trig) == 1, len(trig))
        if trig:
            c.chk("T1: trigger category TASK_BLOCKED",
                  trig[0].get("trigger") == "TASK_BLOCKED", trig[0])
        c.chk("T1: failed task is NEEDS_REVIEW, downstream was BLOCKED",
              p.get_task("task_risk") is None  # removed by v2
              and p.replans and p.replans[0]["trigger"] == "TASK_BLOCKED")
        c.chk("T1: replan accepted (v2 active)",
              p.current_graph_revision == 2, p.current_graph_revision)
        c.chk("T1: project completed after replan",
              result["status"] == "completed", result["status"])
        c.chk("T1: replans summary reported",
              result.get("replans", {}).get("accepted") == 1, result.get("replans"))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T2 — ordinary eval FAIL follows Repair, never Replan
# ------------------------------------------------------------------------- #
@section
def test_t2_no_trigger_on_ordinary_eval_failure(c: Checks):
    d = fresh_dir()
    try:
        # script-executor mode: product candidates BAD first (eval FAIL),
        # GOOD on repair — the normal Repair path, no replan
        scripts = {"product_candidates": [
            copy.deepcopy(BAD_PRODUCT), copy.deepcopy(GOOD["product_candidates"])]}
        ex = ScriptAgentExecutor(scripts)
        h = LongRunningHarness(d, agent_executor=ex, max_concurrency=2,
                               planner_provider=FakePlannerProvider([]))
        p = h.create_project("repair", task_graph={"tasks": [
            {"task_id": "t_prod", "task_type": "product_candidates"}]})
        state = orch.seed_case(WF, p.case_id, {})
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))
        result = h.run(p)
        c.chk("T2: ordinary eval FAIL repaired to PASS",
              p.get_task("t_prod")["status"] == "PASSED",
              p.get_task("t_prod")["status"])
        c.chk("T2: no replan occurred",
              p.replans == [] and p.current_graph_revision == 1,
              (len(p.replans), p.current_graph_revision))
        c.chk("T2: no replan events", events_of(p, "replan_triggered") == [])
        c.chk("T2: exactly 2 executions (1 + 1 repair)",
              ex.calls.count("t_prod") == 2, ex.calls)
        c.chk("T2: project completed on v1",
              result["status"] == "completed", result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T3 — safe barrier: no replan while a worker is running
# ------------------------------------------------------------------------- #
@section
def test_t3_safe_barrier(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner = make_replan_project(d, [graph_json(V2)])
        p._set_task("task_rep", status="RUNNING")
        c.chk("T3: no trigger while a task is RUNNING",
              h._evaluate_replan_trigger(p, {}) is None)
        # and even a forced invocation refuses (R1 belt-and-braces)
        rec = h._run_replan(p, {}, WF, {"trigger": "TASK_BLOCKED",
                                        "reason": "forced", "task_ids": []}, [])
        c.chk("T3: _run_replan refuses at unsafe barrier",
              rec["status"] == "failed" and "UNSAFE_BARRIER" in rec["error"], rec)
        c.chk("T3: no graph revision created",
              p.current_graph_revision == 1, p.current_graph_revision)
    finally:
        cleanup(d)


class RecordingPlannerProvider(FakePlannerProvider):
    """Captures the prompt so tests can assert the ReplanContext contract."""
    def __init__(self, graphs):
        super().__init__(graphs)
        self.prompts = []

    def generate(self, messages, tools):
        self.prompts.append(messages[0]["content"])
        return super().generate(messages, tools)


# ------------------------------------------------------------------------- #
# T4 — the Harness invokes the Planner with a structured ReplanContext
# ------------------------------------------------------------------------- #
@section
def test_t4_replan_context(c: Checks):
    d = fresh_dir()
    try:
        provider = TaskScriptProvider(copy.deepcopy(SCRIPTS))
        planner = RecordingPlannerProvider([graph_json(V2)])
        h = LongRunningHarness(d, agent_executor=provider,
                               planner_provider=planner)
        p = h.create_project("ctx", task_graph=copy.deepcopy(V1))
        state = orch.seed_case(WF, p.case_id, {})
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))
        h.run(p)
        c.chk("T4: planner invoked exactly once for the replan",
              planner.calls == 1, planner.calls)
        c.chk("T4: prompt captured", len(planner.prompts) == 1)
        if planner.prompts:
            prompt = planner.prompts[0]
            for marker in ("REPLAN", "task_cli", "task_req", "TASK_BLOCKED",
                           "current_graph_revision", "completed_tasks",
                           "requirement_analysis", "risk_analysis",
                           "Preserve", "task_id"):
                c.chk("T4: ReplanContext carries %r" % marker, marker in prompt)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T5 — invalid replan graph is rejected; the active graph cannot mutate
# ------------------------------------------------------------------------- #
@section
def test_t5_invalid_graph_rejected(c: Checks):
    d = fresh_dir()
    try:
        bad = json.dumps({"tasks": [
            {"task_id": "x1", "task_type": "not_a_real_type"},
            {"task_id": "x2", "task_type": "risk_analysis",
             "dependencies": ["x1"]}]})
        h, p, provider, planner = make_replan_project(d, [bad] * 3)
        result = h.run(p)
        recs = p.replans
        c.chk("T5: replan failed on invalid graph",
              len(recs) == 1 and recs[0]["status"] == "failed", recs)
        c.chk("T5: graph validator rejected (3 attempts)",
              recs[0]["planner_attempts"] == 3, recs[0])
        c.chk("T5: active graph UNCHANGED (R12)",
              [t["task_id"] for t in p.tasks] == V1_IDS,
              [t["task_id"] for t in p.tasks])
        c.chk("T5: no new revision", p.current_graph_revision == 1)
        c.chk("T5: validator rejections observed",
              len(events_of(p, "graph_validation_failed")) == 3)
        c.chk("T5: project fails closed (needs_review)",
              result["status"] == "needs_review", result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T6 — bounded planner retry: invalid then valid
# ------------------------------------------------------------------------- #
@section
def test_t6_planner_bounded_retry(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner = make_replan_project(
            d, ["{not json", graph_json(V2)])
        result = h.run(p)
        c.chk("T6: invalid first attempt retried, then accepted",
              p.current_graph_revision == 2, p.current_graph_revision)
        c.chk("T6: bounded retry recorded (2 attempts)",
              p.replans[0]["planner_attempts"] == 2, p.replans[0])
        c.chk("T6: planner consumed exactly 2 script items",
              planner.calls == 2, planner.calls)
        c.chk("T6: project completed", result["status"] == "completed",
              result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T7/T8 — revision persistence + lineage immutability
# ------------------------------------------------------------------------- #
@section
def test_t7_t8_revision_persisted_and_immutable(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        c.chk("T7: graph lineage v1→v2 persisted",
              [r["revision"] for r in p.graph_revisions] == [1, 2],
              [r["revision"] for r in p.graph_revisions])
        c.chk("T7: v2 lineage fields",
              p.graph_revisions[1]["parent_revision"] == 1
              and p.graph_revisions[1]["trigger"] == "TASK_BLOCKED"
              and p.graph_revisions[1]["planner_run_id"],
              p.graph_revisions[1])
        v1_before = copy.deepcopy(p.graph_revisions[0])
        h.run(p)
        c.chk("T8: v1 snapshot unchanged after later runs",
              p.graph_revisions[0] == v1_before)
        p2 = load_project(d, p.project_id)
        c.chk("T7: revisions survive reload",
              [r["revision"] for r in p2.graph_revisions] == [1, 2])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T9/T10/T12 — preservation, new-task execution, deterministic diff
# ------------------------------------------------------------------------- #
@section
def test_t9_t10_t12_preserve_new_diff(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        # T9: completed v1 work never re-executed
        c.chk("T9: task_cli executed exactly once",
              len(starts_of(p, "task_cli")) == 1, starts_of(p, "task_cli"))
        c.chk("T9: task_req executed exactly once",
              len(starts_of(p, "task_req")) == 1, starts_of(p, "task_req"))
        c.chk("T9: preserved tasks stay PASSED",
              p.get_task("task_cli")["status"] == "PASSED"
              and p.get_task("task_req")["status"] == "PASSED")
        # T10: the v2-introduced retry task executed normally
        c.chk("T10: new task task_risk2 executed once",
              len(starts_of(p, "task_risk2")) == 1, starts_of(p, "task_risk2"))
        c.chk("T10: report executed after replan",
              len(starts_of(p, "task_rep")) == 1, starts_of(p, "task_rep"))
        c.chk("T10: all tasks PASSED",
              all(t["status"] == "PASSED" for t in p.tasks),
              {t["task_id"]: t["status"] for t in p.tasks})
        # T12: deterministic machine-computed diff
        diff = p.replans[0].get("diff") or {}
        c.chk("T12: diff.added", diff.get("added") == ["task_risk2"],
              diff.get("added"))
        c.chk("T12: diff.removed", diff.get("removed") == ["task_risk"],
              diff.get("removed"))
        c.chk("T12: diff.preserved",
              sorted(diff.get("preserved") or []) == ["task_cli", "task_req"],
              diff.get("preserved"))
        c.chk("T12: diff.rerun", diff.get("rerun") == ["task_rep"],
              diff.get("rerun"))
        dc = diff.get("dependency_changes") or []
        c.chk("T12: diff.dependency_changes (exactly task_rep)",
              len(dc) == 1 and dc[0]["task_id"] == "task_rep"
              and dc[0]["from"] == ["task_cli", "task_req", "task_risk"]
              and dc[0]["to"] == ["task_cli", "task_req", "task_risk2"], dc)
        c.chk("T12: diff computed deterministically (no LLM text)",
              isinstance(diff, dict) and set(diff) == {
                  "added", "removed", "preserved", "rerun",
                  "dependency_changes"}, sorted(diff))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T11 — v1 artifacts remain valid inputs for v2 (lineage-safe reuse)
# ------------------------------------------------------------------------- #
class ArtifactVisibilityProvider(TaskScriptProvider):
    """Records which CaseState artifacts were visible per executed task."""
    def __init__(self, scripts):
        super().__init__(scripts)
        self.seen = {}

    def generate(self, messages, tools):
        task_id = ""
        for m in reversed(messages):
            content = m.get("content") or ""
            if m.get("role") == "user" and "Execute task: " in content:
                task_id = content.split("Execute task: ")[1].split(" ")[0]
                break
        # the worker snapshot is what the executor sees — recover artifact
        # visibility from the context the tool layer reports back is not
        # directly available; instead assert via the durable state below.
        self.seen.setdefault(task_id, True)
        return super().generate(messages, tools)


@section
def test_t11_artifact_reuse(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        final = load_state(d, p) or {}
        reg_arts = final.get("artifact_registry") or {}
        # v1's client-profile + requirement-analysis (produced BEFORE the
        # replan) satisfy v2's report task — no regeneration happened:
        # each surviving artifact type is registered exactly once
        ids = [r["artifact_id"] for r in reg_arts.values()]
        c.chk("T11: no duplicate artifacts after replan",
              len(ids) == len(set(ids)), ids)
        c.chk("T11: v1 artifacts still registered (lineage intact, R7)",
              {"client-profile", "requirement-analysis"} <= set(reg_arts),
              sorted(reg_arts))
        # the report consumed them: its lineage reaches back to client facts
        from runtime import artifact_registry as reg
        lineage = reg.lineage_types(final, "insurance-report")
        c.chk("T11: v2 report lineage crosses v1-produced artifacts",
              "client-profile" in lineage and "requirement-analysis" in lineage,
              lineage)
        # and the report engine really ran on the v1 artifacts (single run)
        c.chk("T11: report executed once on inherited artifacts",
              len(starts_of(p, "task_rep")) == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T13 — replan budget is enforced
# ------------------------------------------------------------------------- #
@section
def test_t13_replan_budget(c: Checks):
    d = fresh_dir()
    try:
        # v2's retry task ALSO fails (plain text) → after the one allowed
        # replan, the second trigger must be suppressed by the budget
        scripts = copy.deepcopy(SCRIPTS)
        scripts["task_risk2"] = ["仍然无法完成风险分析。"]
        h, p, provider, planner = make_replan_project(
            d, [graph_json(V2)], scripts=scripts, max_replans=1)
        result = h.run(p)
        c.chk("T13: exactly one replan attempted (budget=1)",
              len(p.replans) == 1 and p.current_graph_revision == 2,
              (len(p.replans), p.current_graph_revision))
        c.chk("T13: second trigger suppressed by budget",
              len(events_of(p, "replan_triggered")) == 1,
              len(events_of(p, "replan_triggered")))
        c.chk("T13: project ends needs_review, not looping",
              result["status"] == "needs_review", result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T14 — identical graph cannot create a replan loop
# ------------------------------------------------------------------------- #
@section
def test_t14_no_change_loop_protection(c: Checks):
    d = fresh_dir()
    try:
        # planner returns the SAME (validator-valid) structure as v1
        # (source_request stripped: the graph schema forbids unknown keys)
        h, p, provider, planner = make_replan_project(
            d, [graph_json({"tasks": V1["tasks"]})])
        result = h.run(p)
        c.chk("T14: identical graph detected (no_change)",
              p.replans and p.replans[0]["status"] == "no_change", p.replans)
        c.chk("T14: no new revision created",
              p.current_graph_revision == 1, p.current_graph_revision)
        c.chk("T14: exactly one replan attempt (loop stopped)",
              len(p.replans) == 1, len(p.replans))
        c.chk("T14: active graph unchanged",
              [t["task_id"] for t in p.tasks] == V1_IDS,
              [t["task_id"] for t in p.tasks])
        c.chk("T14: no_change recorded with structural reason",
              "REPLAN_NO_CHANGE" in (p.replans[0].get("error") or ""),
              p.replans[0])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T15 — planner failure is fail-closed
# ------------------------------------------------------------------------- #
@section
def test_t15_planner_failure_fail_closed(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner = make_replan_project(d, ["{broken json"] * 3)
        result = h.run(p)
        recs = p.replans
        c.chk("T15: replan failed after bounded retries",
              len(recs) == 1 and recs[0]["status"] == "failed", recs)
        c.chk("T15: fail closed — no fallback graph, v1 intact",
              p.current_graph_revision == 1
              and [t["task_id"] for t in p.tasks] == V1_IDS,
              (p.current_graph_revision, [t["task_id"] for t in p.tasks]))
        c.chk("T15: replan_failed event emitted",
              len(events_of(p, "replan_failed")) == 1)
        c.chk("T15: project surfaces needs_review",
              result["status"] == "needs_review", result["status"])
        c.chk("T15: v1 successes preserved despite failed replan",
              p.get_task("task_cli")["status"] == "PASSED")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T16 — checkpoint integration
# ------------------------------------------------------------------------- #
@section
def test_t16_checkpoint(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        cps = p.checkpoints()
        c.chk("T16: checkpoint records carry graph_revision",
              bool(cps) and all("graph_revision" in cp for cp in cps),
              [list(cp) for cp in cps[:1]])
        post = [cp for cp in cps if cp.get("graph_revision") == 2]
        c.chk("T16: checkpoints written under revision 2", len(post) >= 1,
              len(post))
        p2 = load_project(d, p.project_id)
        c.chk("T16: replan state survives reload",
              p2.current_graph_revision == 2 and len(p2.replans) == 1,
              (p2.current_graph_revision, len(p2.replans)))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T17 — recovery after a replan-related interruption (R11)
# ------------------------------------------------------------------------- #
@section
def test_t17_recovery_after_replan_interruption(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner = make_replan_project(d, [graph_json(V2)])
        # forge a crash DURING replanning: an in_progress record on disk
        p.replans.append({
            "replan_id": "replan_crash", "revision_from": 1,
            "trigger": "TASK_BLOCKED", "reason": "forged interruption",
            "status": "in_progress", "planner_attempts": 1,
            "created_at": "2026-09-18T00:00:00Z", "completed_at": None,
            "error": ""})
        p._save()

        provider2 = TaskScriptProvider(copy.deepcopy(SCRIPTS))
        h2 = LongRunningHarness(d, agent_executor=provider2,
                                planner_provider=FakePlannerProvider(
                                    [graph_json(V2)]))
        p2 = load_project(d, p.project_id)
        result = h2.run(p2)
        rec = next(r for r in p2.replans if r["replan_id"] == "replan_crash")
        c.chk("T17: in_progress replan marked failed on resume (R11)",
              rec["status"] == "failed" and "INTERRUPTED" in rec["error"], rec)
        c.chk("T17: no false revision from the crashed replan at its point",
              rec.get("revision") is None)
        c.chk("T17: replan_failed event recorded",
              any(e.get("replan_id") == "replan_crash"
                  for e in events_of(p2, "replan_failed")))
        # the resumed run still replans legitimately (crashed one consumed
        # budget 1 of 2) and completes
        c.chk("T17: resumed run completes via a NEW clean replan",
              result["status"] == "completed"
              and p2.current_graph_revision == 2,
              (result["status"], p2.current_graph_revision))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T18 — parallel compatibility (replan only at the round/barrier edge)
# ------------------------------------------------------------------------- #
@section
def test_t18_parallel_compatibility(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d, max_concurrency=2)
        c.chk("T18: replan works under max_concurrency=2",
              p.current_graph_revision == 2, p.current_graph_revision)
        c.chk("T18: project completed", result["status"] == "completed",
              result["status"])
        evs = p.events()
        done = next((i for i, e in enumerate(evs)
                     if e["event_type"] == "replan_completed"), -1)
        # every v2 execution (task_risk2, task_rep retry) starts strictly
        # after the replan completed — proof the planner never ran mid-round
        first_v2_start = min(
            (i for i, e in enumerate(evs)
             if e["event_type"] == "task_started"
             and e.get("task_id") in ("task_risk2", "task_rep")), default=10**9)
        c.chk("T18: v2 executions start only after replan_completed",
              first_v2_start > done, (first_v2_start, done))
        # and the planner phase itself contains no execution events
        trig = next((i for i, e in enumerate(evs)
                     if e["event_type"] == "replan_triggered"), -1)
        between = [e for e in evs[trig:done + 1]
                   if e["event_type"] == "task_started"]
        c.chk("T18: no execution during the replan decision",
              between == [], between)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T19 — sequential compatibility (Phase 6 path + replan)
# ------------------------------------------------------------------------- #
@section
def test_t19_sequential_compatibility(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d, max_concurrency=1)
        evs = [e["event_type"] for e in p.events()]
        c.chk("T19: sequential path (no parallel scheduler events)",
              "task_scheduled" not in evs, evs[:8])
        c.chk("T19: replan + completion on the Phase 6 path",
              result["status"] == "completed"
              and p.current_graph_revision == 2)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T20 — MessageBus stays coordination-only
# ------------------------------------------------------------------------- #
@section
def test_t20_a2a_cannot_mutate_graph(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        from runtime.agents import MessageBus
        bus = MessageBus(p._dir)
        before_ids = [t["task_id"] for t in p.tasks]
        before_rev = p.current_graph_revision
        bus.send(from_agent="insurance_analyst",
                 to_agent="knowledge_specialist",
                 message_type="TASK_HANDOFF", task_id="task_cli")
        bus.send(from_agent="insurance_analyst",
                 to_agent="knowledge_specialist",
                 message_type="INFORMATION_REQUEST")
        c.chk("T20: messages did NOT change the active graph",
              [t["task_id"] for t in p.tasks] == before_ids)
        c.chk("T20: messages did NOT change graph revision",
              p.current_graph_revision == before_rev)
        import inspect
        from runtime.agents import message_bus as mb
        src = inspect.getsource(mb)
        for banned in ("create_task", "add_task", "project.tasks",
                       "remove_task", "graph_revision", "replan"):
            c.chk("T20: message_bus has no %r" % banned, banned not in src)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T21 — agents have no replan / graph-mutation capability
# ------------------------------------------------------------------------- #
@section
def test_t21_agent_cannotask_replan(c: Checks):
    d = fresh_dir()
    try:
        import inspect
        from runtime.agent import tools as agent_tools
        from runtime.agents import executor as agents_executor
        src = inspect.getsource(agent_tools) + inspect.getsource(agents_executor)
        for banned in ("from runtime.planner import planner",
                       "planner.replan", "planner.plan(", "graph_revision",
                       "max_replans", "current_graph_revision"):
            c.chk("T21: agent layer never references %r" % banned,
                  banned not in src)
        reg_tools = agent_tools.build_registry()
        c.chk("T21: no replan/planner tool exposed to agents",
              not any("plan" in name or "replan" in name
                      for name in reg_tools), sorted(reg_tools))
        h, p, provider, planner, result = run_master_flow(d)
        c.chk("T21: revisions only created by Harness replans",
              len(p.graph_revisions) == 2
              and all(r["planner_run_id"] for r in p.graph_revisions[1:]))
        c.chk("T21: agents executed only via task scheduling",
              set(provider.calls) <= {"task_cli", "task_req", "task_risk",
                                      "task_risk2", "task_rep"}, provider.calls)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T22 — replan lifecycle events: correct, ordered, non-duplicated
# ------------------------------------------------------------------------- #
@section
def test_t22_event_integrity(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider, planner, result = run_master_flow(d)
        for etype in ("replan_triggered", "replan_started",
                      "replan_completed"):
            evs = events_of(p, etype)
            c.chk("T22: exactly one %s" % etype, len(evs) == 1,
                  (etype, len(evs)))
        revisions = events_of(p, "graph_revision_created")
        c.chk("T22: exactly two revisions (INITIAL + replan)",
              len(revisions) == 2
              and revisions[0].get("trigger") == "INITIAL"
              and revisions[1].get("graph_revision") == 2, revisions)
        evs = p.events()
        order = {}
        for i, e in enumerate(evs):
            if e["event_type"] not in order:
                order[e["event_type"]] = i
        replan_rev = next(i for i, e in enumerate(evs)
                          if e["event_type"] == "graph_revision_created"
                          and e.get("trigger") != "INITIAL")
        c.chk("T22: order triggered < started < revision_created < completed",
              order["replan_triggered"] < order["replan_started"]
              < replan_rev < order["replan_completed"])
        trig = events_of(p, "replan_triggered")[0]
        done = events_of(p, "replan_completed")[0]
        c.chk("T22: events correlate on replan identifiers",
              trig.get("replan_id") == done.get("replan_id")
              and done.get("graph_revision") == 2
              and done.get("parent_revision") == 1, (trig, done))
        c.chk("T22: diff surfaced in replan_completed (structured, no CoT)",
              "added" in done and "preserved" in done, list(done))
        # graph validation events belong to the planner attempt lifecycle
        c.chk("T22: graph_validation_passed fired once for the replan",
              len(events_of(p, "graph_validation_passed")) == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T23 — determinism: same state + same planner output → same result
# ------------------------------------------------------------------------- #
@section
def test_t23_determinism(c: Checks):
    runs = []
    for i in range(3):
        d = fresh_dir()
        try:
            h, p, provider, planner, result = run_master_flow(d)
            runs.append({
                "status": result["status"],
                "revision": p.current_graph_revision,
                "tasks": {t["task_id"]: t["status"] for t in p.tasks},
                "diff": p.replans[0]["diff"],
                "fingerprint": h._graph_fingerprint(p.tasks),
            })
        finally:
            cleanup(d)
    first = runs[0]
    c.chk("T23: same final statuses across 3 runs",
          all(r["tasks"] == first["tasks"] for r in runs),
          [r["tasks"] for r in runs])
    c.chk("T23: same graph fingerprint",
          all(r["fingerprint"] == first["fingerprint"] for r in runs))
    c.chk("T23: same diff", all(r["diff"] == first["diff"] for r in runs))
    c.chk("T23: same revision + status",
          all(r["revision"] == first["revision"]
              and r["status"] == first["status"] for r in runs))


# ------------------------------------------------------------------------- #
# T24 — realistic FOUR-agent replan E2E through the real executor:
# v1 runs analyst + knowledge + product specialists; knowledge_search fails
# (no artifact); the report task is BLOCKED; the Harness replans; v2 drops
# the failed task and reroutes the report dependency; the REAL report
# engine then completes the project.
# ------------------------------------------------------------------------- #
T24_V1 = {"tasks": [
    {"task_id": "task_0", "task_type": "client_profile"},
    {"task_id": "task_1", "task_type": "requirement_analysis",
     "dependencies": ["task_0"]},
    {"task_id": "task_2", "task_type": "risk_analysis",
     "dependencies": ["task_0", "task_1"]},
    {"task_id": "task_3", "task_type": "coverage_gap",
     "dependencies": ["task_0", "task_1", "task_2"]},
    {"task_id": "task_4", "task_type": "solution",
     "dependencies": ["task_1", "task_2", "task_3"]},
    {"task_id": "task_5", "task_type": "knowledge_search",
     "dependencies": ["task_4"]},
    {"task_id": "task_6", "task_type": "product_candidates",
     "dependencies": ["task_0", "task_3", "task_4"]},
    {"task_id": "task_7", "task_type": "report_generation",
     "dependencies": ["task_0", "task_1", "task_2", "task_5", "task_6"]},
], "source_request": "完整分析并生成报告"}

T24_V2 = {"tasks": [
    {"task_id": "task_0", "task_type": "client_profile"},
    {"task_id": "task_1", "task_type": "requirement_analysis",
     "dependencies": ["task_0"]},
    {"task_id": "task_2", "task_type": "risk_analysis",
     "dependencies": ["task_0", "task_1"]},
    {"task_id": "task_3", "task_type": "coverage_gap",
     "dependencies": ["task_0", "task_1", "task_2"]},
    {"task_id": "task_4", "task_type": "solution",
     "dependencies": ["task_1", "task_2", "task_3"]},
    {"task_id": "task_6", "task_type": "product_candidates",
     "dependencies": ["task_0", "task_3", "task_4"]},
    {"task_id": "task_7", "task_type": "report_generation",
     "dependencies": ["task_0", "task_1", "task_2", "task_6"]},
]}

T24_SCRIPTS = {
    "task_0": [("record_client_profile", PROFILE_ARGS), "done"],
    "task_1": [("record_requirement_analysis", REQ_ARGS), "done"],
    "task_2": [("record_risk_assessment", RISK_ARGS), "done"],
    "task_3": [("coverage_gap_analysis", {}), "done"],
    "task_4": [("solution", {}), "done"],
    # plain-text reply → no knowledge-evidence artifact → AGENT_FAILED
    "task_5": ["知识检索没有找到可用证据。"],
    "task_6": [("product_candidate_provider", {}), "done"],
    "task_7": [("report_generation", {}), "done"],
}


@section
def test_t24_multi_agent_replan_e2e(c: Checks):
    d = fresh_dir()
    try:
        provider = TaskScriptProvider(copy.deepcopy(T24_SCRIPTS))
        planner = FakePlannerProvider([graph_json(T24_V2)])
        h = LongRunningHarness(d, agent_executor=provider,
                               planner_provider=planner)
        p = h.create_project("e2e-replan", task_graph=copy.deepcopy(T24_V1))
        state = orch.seed_case(WF, p.case_id, {})
        from runtime.state import store as ss
        ss.save(state, os.path.join(d, p.project_id, "case"))
        result = h.run(p)

        c.chk("T24: project COMPLETED after replan",
              result["status"] == "completed", result["status"])
        c.chk("T24: revision v1 → v2", p.current_graph_revision == 2,
              p.current_graph_revision)
        c.chk("T24: replanning changed the ACTUAL execution graph",
              p.get_task("task_5") is None
              and p.get_task("task_7")["dependencies"]
              == ["task_0", "task_1", "task_2", "task_6"],
              [t["task_id"] for t in p.tasks])
        c.chk("T24: report executed and PASSED after reroute",
              p.get_task("task_7")["status"] == "PASSED"
              and len(starts_of(p, "task_7")) == 1)
        # all four specialist agents really executed across v1+v2
        evs = p.events()
        started = {e.get("agent_id") for e in evs
                   if e["event_type"] == "agent_started"}
        c.chk("T24: 4 specialist agents executed",
              started == {"insurance_analyst", "knowledge_specialist",
                          "product_specialist", "report_specialist"}, started)
        # v1's completed work was preserved, not re-executed
        c.chk("T24: preserved tasks not re-executed",
              len(starts_of(p, "task_1")) == 1
              and len(starts_of(p, "task_4")) == 1)
        final = load_state(d, p) or {}
        c.chk("T24: final report artifact produced",
              "insurance-report" in (final.get("artifacts") or {}),
              sorted((final.get("artifacts") or {}).keys()))
        c.chk("T24: diff recorded for the realistic replan",
              p.replans[0]["diff"]["removed"] == ["task_5"], p.replans[0]["diff"])
    finally:
        cleanup(d)


def main():
    return run_sections(SECTIONS, "webui_testask_replan_log.txt",
                        "RUNTIME DYNAMIC REPLANNING")


if __name__ == "__main__":
    sys.exit(main())
