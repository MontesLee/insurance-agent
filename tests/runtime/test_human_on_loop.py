"""Phase 10 — Human-on-the-loop Control Plane tests (T1–T40).

Covers: the deterministic monitor (signals, dedup, risk), the intervention
policy (LOW→NONE … CRITICAL→PAUSE, WAIT_APPROVAL priority), permission
boundaries (agents/planner/monitor/bus cannot control the runtime),
audited idempotent control commands (pause/resume/retry/cancel/replan/
provide-information), safe-barrier pausing (sequential + parallel),
crash recovery for paused projects and mid-command crashes, human-input
artifacts with provenance and conflict detection, checkpoint integration,
Phase 7/8/9 compatibility and the four-agent HOTL E2E (autonomous NOTIFY
vs supervisor PAUSE vs approval WAITING).

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_human_on_loop.py`.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

import test_dynamic_replanning as PH8  # noqa: E402
from test_parallel_scheduler import (TaskScriptProvider, load_state,  # noqa: E402
                                     cleanup)
from runtime import orchestrator as orch
from runtime.approval import ApprovalPolicy  # noqa: E402
from runtime.control import (RuntimeMonitor, InterventionPolicy,  # noqa: E402
                             ControlPlane, ControlStore, RISK_LOW, RISK_MEDIUM,
                             RISK_HIGH, RISK_CRITICAL, INTERVENTION_NONE,
                             INTERVENTION_NOTIFY, INTERVENTION_PAUSE,
                             INTERVENTION_WAIT_APPROVAL, make_signal,
                             make_observation, make_supervisor_state)
from runtime.harness import LongRunningHarness, load_project
from runtime.planner.planner import FakePlannerProvider

SECTIONS = []
WF = orch.load_workflow()


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="hotl_", dir=os.path.join(REPO, "tmp"))


def make_project(root, planner_graphs=None, max_concurrency=1, max_replans=2,
                 policy=None, intervention_policy=None, graph=None,
                 scripts=None):
    provider = TaskScriptProvider(copy.deepcopy(scripts or PH8.SCRIPTS))
    planner = FakePlannerProvider(
        list(planner_graphs if planner_graphs is not None
             else [PH8.graph_json(PH8.V2)]))
    h = LongRunningHarness(root, agent_executor=provider,
                           max_concurrency=max_concurrency,
                           max_replans=max_replans,
                           planner_provider=planner,
                           approval_policy=policy,
                           intervention_policy=intervention_policy)
    p = h.create_project("hotl", task_graph=graph or copy.deepcopy(PH8.V1))
    state = orch.seed_case(WF, p.case_id, {})
    from runtime.state import store as ss
    ss.save(state, os.path.join(root, p.project_id, "case"))
    return h, p, provider


def events_of(p, etype):
    return [e for e in p.events() if e["event_type"] == etype]


def starts_of(p, tid):
    return [e for e in p.events()
            if e["event_type"] == "task_started" and e.get("task_id") == tid]


def a_failing_project(root, **kw):
    """The Phase 8 master scenario: task_risk fails (plain text), task_rep
    blocked, then a replan. Monitor is ON by default."""
    h, p, provider = make_project(root, **kw)
    return h, p, provider


# ------------------------------------------------------------------------- #
# T1/T2 — monitor consumes runtime events; deterministic signals
# ------------------------------------------------------------------------- #
@section
def test_t1_t2_monitor_signals(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = a_failing_project(d)
        result = h.run(p)
        evs = p.events()
        # T1: the monitor consumed the runtime event log
        c.chk("T1: run completed with monitor on", result["status"] == "completed",
              result["status"])
        c.chk("T1: monitor_started events present",
              len(events_of(p, "monitor_started")) >= 1)
        # T2: deterministic signal generation. The mid-run failure was
        # observed at the barriers (its alert is durable); the settled
        # final state shows the structural graph-change signal (the failed
        # task was removed by the accepted replan).
        monitor = RuntimeMonitor()
        obs = monitor.observe(p, events=evs, max_replans=2)
        types = {s["signal_type"] for s in obs["signals"]}
        c.chk("T2: high-impact graph change signal present",
              "SIGNAL_GRAPH_CHANGE_HIGH_IMPACT" in types, sorted(types))
        c.chk("T2: no integrity signal on a healthy project",
              "SIGNAL_INTEGRITY" not in types)
        # the durable alerts carry the deterministic signals seen mid-run
        alerts = ControlStore(p._dir).alerts()
        alert_types = {a["signal_type"] for a in alerts}
        c.chk("T2: alerts persisted from the barrier observations",
              len(alerts) >= 2 and all(a["fingerprint"] for a in alerts)
              and "SIGNAL_TASK_FAILURE" in alert_types,
              sorted(alert_types))
        # determinism: same state + events, same observation
        obs2 = monitor.observe(p, events=evs, max_replans=2)
        c.chk("T2: observation deterministic",
              [s["signal_type"] for s in obs["signals"]]
              == [s["signal_type"] for s in obs2["signals"]]
              and obs["risk_level"] == obs2["risk_level"])
    finally:
        cleanup(d)


@section
def test_t2b_deterministic_signal_rules(c: Checks):
    d = fresh_dir()
    try:
        h = LongRunningHarness(d)
        p = h.create_project("sig", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"},
            {"task_id": "task_b", "task_type": "risk_analysis",
             "dependencies": ["task_a"]}]})
        monitor = RuntimeMonitor()
        # healthy → no signals
        obs = monitor.observe(p, events=[], max_replans=2)
        c.chk("T2: healthy project → LOW, no signals",
              obs["risk_level"] == RISK_LOW and obs["signals"] == [])
        # failed task → TASK_FAILURE (MEDIUM); attempts>=3 → REPAIR_EXHAUSTED
        p._set_task("task_a", status="NEEDS_REVIEW", attempt=3)
        obs = monitor.observe(p, events=[], max_replans=2)
        types = {s["signal_type"] for s in obs["signals"]}
        c.chk("T2: NEEDS_REVIEW task → SIGNAL_TASK_FAILURE",
              "SIGNAL_TASK_FAILURE" in types)
        c.chk("T2: attempts>=3 → SIGNAL_REPAIR_EXHAUSTED",
              "SIGNAL_REPAIR_EXHAUSTED" in types)
        c.chk("T2: risk MEDIUM from medium signals",
              obs["risk_level"] == RISK_MEDIUM)
        # repeated failure from the EVENT LOG → HIGH
        for _ in range(3):
            p._event("task_failed", task_id="task_b", reason="x")
        obs = monitor.observe(p, events=p.events(), max_replans=2)
        types = {s["signal_type"] for s in obs["signals"]}
        c.chk("T2: 3 task_failed events → SIGNAL_REPEATED_FAILURE",
              "SIGNAL_REPEATED_FAILURE" in types)
        c.chk("T2: risk HIGH", obs["risk_level"] == RISK_HIGH)
        # integrity → CRITICAL (dangling dependency)
        p2 = h.create_project("sig2", task_graph={"tasks": [
            {"task_id": "task_x", "task_type": "client_profile",
             "dependencies": ["task_missing"]}]})
        obs = monitor.observe(p2, events=[], max_replans=2)
        c.chk("T2: dangling dependency → SIGNAL_INTEGRITY (CRITICAL)",
              obs["signals"] and obs["signals"][0]["signal_type"] == "SIGNAL_INTEGRITY"
              and obs["risk_level"] == RISK_CRITICAL, obs["signals"][:1])
        # budget signals
        p._set_task("task_a", status="NEEDS_REVIEW", attempt=9)
        obs = monitor.observe(p, events=[], max_replans=2)
        types = {s["signal_type"] for s in obs["signals"]}
        c.chk("T2: repair budget exceeded → SIGNAL_BUDGET_EXCEEDED",
              "SIGNAL_BUDGET_EXCEEDED" in types)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T3/T34 — signal + notification deduplication (no event storm)
# ------------------------------------------------------------------------- #
@section
def test_t3_t34_deduplication(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = a_failing_project(d)
        h.run(p)
        store = ControlStore(p._dir)
        alerts_after_run = len(store.alerts())
        notifs_after_run = len(store.notifications())
        # re-observing the SAME state must not duplicate alerts/notifications
        plane = h._control_plane(p)
        plane.observe([])
        plane.observe([])
        c.chk("T3: re-observation adds no duplicate alerts",
              len(store.alerts()) == alerts_after_run,
              (alerts_after_run, len(store.alerts())))
        c.chk("T34: notifications deduplicated",
              len(store.notifications()) == notifs_after_run,
              (notifs_after_run, len(store.notifications())))
        sig_events = len(events_of(p, "monitor_signal_detected"))
        plane.observe([])
        c.chk("T3: signal events not re-emitted for unchanged state",
              len(events_of(p, "monitor_signal_detected")) == sig_events)
        # resolved alerts: conditions that clear resolve their alerts; a
        # historically-true signal (the applied graph change remains a fact)
        # stays OPEN until a human acknowledges it via RESUME
        for t in p.tasks:
            if t["status"] == "NEEDS_REVIEW":
                t["status"] = "PASSED"
        p._save()
        plane.observe([])
        by_type = {a["signal_type"]: a["status"] for a in store.alerts()}
        c.chk("T3: cleared conditions resolve their alerts",
              by_type.get("SIGNAL_TASK_FAILURE") == "RESOLVED"
              and by_type.get("SIGNAL_REPLAN_NO_CHANGE", "RESOLVED")
              == "RESOLVED", by_type)
        c.chk("T3: historically-true signals stay OPEN until acknowledged",
              by_type.get("SIGNAL_GRAPH_CHANGE_HIGH_IMPACT") == "OPEN",
              by_type)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T4–T9 — risk levels + deterministic intervention policy
# ------------------------------------------------------------------------- #
@section
def test_t4_t5_risk_and_policy(c: Checks):
    mon = RuntimeMonitor()
    c.chk("T4: no signals → LOW", mon.risk_level([]) == RISK_LOW)
    c.chk("T4: medium → MEDIUM",
          mon.risk_level([make_signal("SIGNAL_TASK_FAILURE", "MEDIUM")])
          == RISK_MEDIUM)
    c.chk("T4: high wins over medium",
          mon.risk_level([make_signal("SIGNAL_TASK_FAILURE", "MEDIUM"),
                          make_signal("SIGNAL_REPEATED_FAILURE", "HIGH")])
          == RISK_HIGH)
    c.chk("T4: critical wins over all",
          mon.risk_level([make_signal("SIGNAL_INTEGRITY", "CRITICAL"),
                          make_signal("SIGNAL_REPEATED_FAILURE", "HIGH")])
          == RISK_CRITICAL)
    pol = InterventionPolicy()
    obs = make_observation("p", RISK_MEDIUM, [], INTERVENTION_NONE)
    sup = make_supervisor_state("p")
    d1 = pol.decide(obs, sup, None)
    d2 = pol.decide(obs, sup, None)
    c.chk("T5: policy deterministic (same in, same out)", d1 == d2)
    c.chk("T5: decision carries a reason", bool(d1["reason"]))


@section
def test_t6_t7_t8_t9_policy_mapping(c: Checks):
    pol = InterventionPolicy()
    sup = make_supervisor_state("p")
    c.chk("T6: LOW → NONE",
          pol.decide(make_observation("p", RISK_LOW, [], ""), sup)["action"]
          == INTERVENTION_NONE)
    c.chk("T7: MEDIUM → NOTIFY",
          pol.decide(make_observation("p", RISK_MEDIUM, [], ""), sup)["action"]
          == INTERVENTION_NOTIFY)
    c.chk("T8: HIGH → NOTIFY by default",
          pol.decide(make_observation("p", RISK_HIGH, [], ""), sup)["action"]
          == INTERVENTION_NOTIFY)
    c.chk("T8: HIGH → configurable PAUSE",
          InterventionPolicy(high=INTERVENTION_PAUSE).decide(
              make_observation("p", RISK_HIGH, [], ""), sup)["action"]
          == INTERVENTION_PAUSE)
    c.chk("T9: CRITICAL → PAUSE",
          pol.decide(make_observation("p", RISK_CRITICAL, [], ""), sup)["action"]
          == INTERVENTION_PAUSE)
    # a waiting Phase 9 approval keeps priority (WAIT_APPROVAL)
    c.chk("T9: waiting approval outranks supervisor notification",
          pol.decide(make_observation("p", RISK_CRITICAL, [], ""), sup,
                     None, waiting_approval=True)["action"]
          == INTERVENTION_WAIT_APPROVAL)


# ------------------------------------------------------------------------- #
# T10/T11/T12/T13 — permission boundaries
# ------------------------------------------------------------------------- #
@section
def test_t10_t12_permissions(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        plane = h._control_plane(p)
        # T10: an agent actor cannot issue control commands
        out = plane.command("PAUSE", actor="agent:insurance_analyst")
        c.chk("T10: agent actor refused",
              not out["ok"] and "ACTOR_NOT_AUTHORIZED" in out["error"], out)
        out = plane.command("RESUME", actor="planner:glm")
        c.chk("T12: planner actor refused",
              not out["ok"] and "ACTOR_NOT_AUTHORIZED" in out["error"])
        out = plane.command("CANCEL", actor="tool:send_email")
        c.chk("T10: tool actor refused", not out["ok"])
        out = plane.command("PAUSE", actor="message_bus")
        c.chk("T10: message-bus actor refused", not out["ok"])
        c.chk("T10: nothing paused from refused commands",
              plane.supervisor()["status"] == "RUNNING")
        # structural: agent/planner/bus layers have no control-plane path
        import inspect
        from runtime.agents import executor as agents_executor, message_bus as mb
        from runtime.planner import planner as planner_mod
        src = (inspect.getsource(agents_executor) + inspect.getsource(mb)
               + inspect.getsource(planner_mod))
        for banned in ("ControlPlane", "control_command", "_apply_control_command",
                       "runtime_paused", "monitor_enabled"):
            c.chk("T10/T12: agent/planner/bus never reference %r" % banned,
                  banned not in src)
    finally:
        cleanup(d)


@section
def test_t11_t13_request_and_monitor_limits(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        plane = h._control_plane(p)
        # T11: an agent REQUESTS intervention — a signal, never a command
        out = plane.request_intervention(
            "客户信息疑似冲突，需要人工确认", requested_by="agent:insurance_analyst",
            requested_action="NOTIFY")
        c.chk("T11: agent request recorded", out["ok"])
        c.chk("T11: request produced a notification",
              len(ControlStore(p._dir).notifications()) == 1)
        c.chk("T11: request did NOT pause or mutate the runtime",
              plane.supervisor()["status"] == "RUNNING"
              and all(t["status"] == "PENDING" for t in p.tasks))
        out2 = plane.request_intervention(
            "客户信息疑似冲突，需要人工确认", requested_by="agent:insurance_analyst")
        c.chk("T11: identical request deduplicated", out2.get("already") is True)
        # even a PAUSE-requesting agent cannot pause
        out3 = plane.request_intervention(
            "请求暂停", requested_by="agent:insurance_analyst",
            requested_action="PAUSE")
        c.chk("T11: requested PAUSE honoured only as notification",
              out3["ok"] and plane.supervisor()["status"] == "RUNNING")
        # T13: the monitor has NO command/mutation surface (structural)
        import inspect
        from runtime.control import monitor as monitor_mod
        msrc = inspect.getsource(monitor_mod)
        for banned in ("def command", "def pause", "def resume",
                       "_apply_control_command", "plane.command",
                       "set_status", "task[", "project.tasks ="):
            c.chk("T13: monitor never %r" % banned, banned not in msrc)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T14/T15/T16/T32 — command persistence, PAUSE, idempotency, audit
# ------------------------------------------------------------------------- #
@section
def test_t14_t15_t16_t32_pause_audit(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        plane = h._control_plane(p)
        out = plane.command("PAUSE", actor="human")
        c.chk("T15: PAUSE applied → PAUSED",
              out["ok"] and out["result"]["status"] == "PAUSED", out)
        c.chk("T15: supervisor state persisted",
              ControlStore(p._dir).load_supervisor(p.project_id)["status"]
              == "PAUSED")
        c.chk("T15: project status paused", p.status == "paused")
        c.chk("T15: runtime_paused event emitted",
              len(events_of(p, "runtime_paused")) == 1)
        c.chk("T15: a paused checkpoint was written",
              any(cp.get("supervisor_status") == "PAUSED"
                  for cp in p.checkpoints()))
        # T16: identical PAUSE is idempotent
        out2 = plane.command("PAUSE", actor="human")
        c.chk("T16: double PAUSE idempotent (already)",
              out2["ok"] and out2["already"] is True, out2.get("already"))
        applied = [c2 for c2 in ControlStore(p._dir).commands()
                   if c2["status"] == "APPLIED"]
        c.chk("T16: exactly one APPLIED pause command",
              len(applied) == 1, len(applied))
        # T14/T32: full audit trail persisted (the idempotent duplicate is
        # answered from the original record — one audited row)
        cmds = ControlStore(p._dir).commands()
        c.chk("T14: commands persisted in control_commands.jsonl",
              os.path.exists(os.path.join(p._dir, "control_commands.jsonl"))
              and len(cmds) == 1
              and out2["command"]["command_id"] == cmds[0]["command_id"])
        c.chk("T32: audit fields present",
              all(k in cmds[0] for k in ("command_id", "command", "actor",
                                         "status", "created_at", "applied_at")))
        c.chk("T32: command lifecycle events ordered",
              events_of(p, "control_command_received")
              and events_of(p, "control_command_applied"))
        # run() refuses to execute a paused project
        r = h.run(p)
        c.chk("T15: run() refuses while PAUSED",
              r["status"] == "paused" and starts_of(p, "task_cli") == [])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T17 — safe-barrier pause (sequential: no worker killed mid-commit)
# ------------------------------------------------------------------------- #
@section
def test_t17_safe_barrier_pause(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        # a RUNNING task exists → PAUSE defers to the safe barrier
        p._set_task("task_cli", status="RUNNING")
        plane = h._control_plane(p)
        out = plane.command("PAUSE", actor="human")
        c.chk("T17: pause with RUNNING task defers (PAUSING)",
              out["ok"] and out["result"]["status"] == "PAUSING", out)
        c.chk("T17: task not killed mid-flight",
              p.get_task("task_cli")["status"] == "RUNNING")
        c.chk("T17: no half-committed PAUSED state yet",
              plane.supervisor()["status"] == "PAUSING")
        # the barrier completes the pause: crash-style recovery clears the
        # RUNNING task first (Phase 9 semantics), then the pause completes
        p._set_task("task_cli", status="PENDING")
        p._save()
        r = h.run(p)
        c.chk("T17: pending pause completes at the safe barrier",
              r["status"] == "paused"
              and plane.supervisor()["status"] == "PAUSED")
        c.chk("T17: nothing executed while pausing",
              starts_of(p, "task_cli") == [])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T18 — parallel safe-barrier pause (round boundary, workers committed)
# ------------------------------------------------------------------------- #
@section
def test_t18_parallel_safe_barrier_pause(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d, max_concurrency=2)
        plane = h._control_plane(p)
        result_box = {}

        def _runner():
            result_box["r"] = h.run(p)

        t = threading.Thread(target=_runner)
        t.start()
        # pause as soon as the first round is executing (workers in flight)
        deadline = time.time() + 15
        while time.time() < deadline:
            if starts_of(p, "task_cli"):
                break
            time.sleep(0.01)
        plane.command("PAUSE", actor="human")
        t.join(timeout=30)
        c.chk("T18: parallel run paused (not completed past the barrier)",
              result_box.get("r", {}).get("status") == "paused",
              result_box.get("r", {}).get("status"))
        started = [tid for tid in ("task_cli", "task_req", "task_risk",
                                   "task_rep")
                   if starts_of(p, tid)]
        c.chk("T18: pause honored at a round boundary (round 1 committed)",
              "task_cli" in started, started)
        c.chk("T18: later-round tasks never started against the pause",
              "task_rep" not in started, started)
        # every started task reached a terminal state — no half-commits
        for tid in started:
            st = p.get_task(tid)["status"]
            c.chk("T18: %s committed cleanly (%s)" % (tid, st),
                  st in ("PASSED", "NEEDS_REVIEW"), st)
        c.chk("T18: supervisor PAUSED",
              plane.supervisor()["status"] == "PAUSED")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T19/T20 — RESUME + idempotency
# ------------------------------------------------------------------------- #
@section
def test_t19_t20_resume(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d, planner_graphs=[PH8.graph_json(PH8.V2)])
        plane = h._control_plane(p)
        plane.command("PAUSE", actor="human")
        r1 = h.run(p)
        c.chk("T19: paused run executes nothing",
              r1["status"] == "paused" and provider.calls == [])
        out = plane.command("RESUME", actor="human")
        c.chk("T19: RESUME applied → RUNNING",
              out["ok"] and out["result"]["status"] == "RUNNING")
        c.chk("T19: runtime_resumed event",
              len(events_of(p, "runtime_resumed")) == 1)
        r2 = h.run(p)
        c.chk("T19: resumed run completes the project",
              r2["status"] == "completed", r2["status"])
        # T20: repeated resume is a harmless no-op (idempotent)
        out2 = plane.command("RESUME", actor="human")
        c.chk("T20: second RESUME idempotent (already applied)",
              out2["ok"] and out2["already"] is True, out2.get("already"))
        starts = {tid: len(starts_of(p, tid)) for tid in
                  ("task_cli", "task_req", "task_risk2", "task_rep")}
        r3 = h.run(p)
        c.chk("T20: third run() executes nothing new",
              all(v == 1 for v in starts.values())
              and {tid: len(starts_of(p, tid)) for tid in starts} == starts,
              starts)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T21/T22 — RETRY_TASK validation + no duplicate execution
# ------------------------------------------------------------------------- #
@section
def test_t21_t22_retry(c: Checks):
    d = fresh_dir()
    try:
        # a flow that fails: task_risk plain-text failure
        h, p, provider = make_project(d, planner_graphs=[])
        h.run(p)
        plane = h._control_plane(p)
        c.chk("T21 setup: task_risk NEEDS_REVIEW",
              p.get_task("task_risk")["status"] == "NEEDS_REVIEW")
        # validation failures
        out = plane.command("RETRY_TASK", actor="human",
                            payload={"task_id": "task_nope"})
        c.chk("T21: unknown task refused",
              not out["ok"] and "unknown task" in out["error"])
        out = plane.command("RETRY_TASK", actor="human",
                            payload={"task_id": "task_cli"})
        c.chk("T21: terminal-ok task refused",
              not out["ok"] and "terminal-ok" in out["error"])
        out = plane.command("RETRY_TASK", actor="human", payload={})
        c.chk("T21: missing task_id refused", not out["ok"])
        out = plane.command("RETRY_TASK", actor="human",
                            payload={"task_id": "task_rep"})
        c.chk("T21: BLOCKED downstream retry refused (dependency not met)",
              not out["ok"] and "not met" in out["error"], out.get("error"))
        # T22: retry the FAILED task with a working script → executes once more
        provider._scripts["task_risk"] = [("record_risk_assessment",
                                           PH8.RISK_ARGS), "done"]
        before = len(starts_of(p, "task_risk"))
        out = plane.command("RETRY_TASK", actor="human",
                            payload={"task_id": "task_risk"})
        c.chk("T22: retry applied → PENDING",
              out["ok"] and p.get_task("task_risk")["status"] == "PENDING")
        r = h.run(p)
        c.chk("T22: retried task passed on the re-run",
              p.get_task("task_risk")["status"] == "PASSED", r["status"])
        c.chk("T22: exactly one additional execution",
              len(starts_of(p, "task_risk")) == before + 1,
              (before, len(starts_of(p, "task_risk"))))
        final = load_state(d, p) or {}
        ids = [r2["artifact_id"] for r2 in
               (final.get("artifact_registry") or {}).values()]
        c.chk("T22: no duplicate artifacts after retry",
              len(ids) == len(set(ids)), ids)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T23 — CANCEL is fail-closed and preserves history
# ------------------------------------------------------------------------- #
@section
def test_t23_cancel(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d, planner_graphs=[])
        h.run(p)
        revs_before = copy.deepcopy(p.graph_revisions)
        tasks_before = copy.deepcopy(p.tasks)
        plane = h._control_plane(p)
        out = plane.command("CANCEL", actor="human",
                            payload={"reason": "wrong client"})
        c.chk("T23: CANCEL applied", out["ok"])
        c.chk("T23: supervisor + project cancelled",
              plane.supervisor()["status"] == "CANCELLED"
              and p.status == "cancelled")
        r = h.run(p)
        c.chk("T23: cancelled runtime refuses to execute",
              r["status"] == "cancelled" and provider.calls.count("task_risk") <= 1)
        c.chk("T23: history preserved (tasks, revisions, events)",
              p.tasks == tasks_before and p.graph_revisions == revs_before
              and p.events())
        out2 = plane.command("PAUSE", actor="human")
        c.chk("T23: cannot pause a cancelled project", not out2["ok"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T24 — REPLAN command routes through the Phase 8 path
# ------------------------------------------------------------------------- #
@section
def test_t24_replan_command(c: Checks):
    d = fresh_dir()
    try:
        # no failure → no automatic trigger; the human REQUESTS the replan
        scripts = copy.deepcopy(PH8.SCRIPTS)
        scripts["task_risk"] = [("record_risk_assessment", PH8.RISK_ARGS), "done"]
        h, p, provider = make_project(d, planner_graphs=[PH8.graph_json(PH8.V2)],
                                      scripts=scripts)
        r1 = h.run(p)
        c.chk("T24 setup: v1 completes without replanning",
              r1["status"] == "completed" and p.replans == [])
        plane = h._control_plane(p)
        out = plane.command("REPLAN", actor="human",
                            payload={"reason": "supervisor wants v2"})
        c.chk("T24: human REPLAN applied via the Phase 8 path",
              out["ok"] and out["result"]["replan"]["status"] == "accepted",
              out.get("result"))
        c.chk("T24: same revision/diff machinery",
              p.current_graph_revision == 2
              and p.replans[0]["trigger"] == "HUMAN_REQUEST"
              and p.replans[0]["diff"]["removed"] == ["task_risk"])
        # budget guard still applies (§21). Identical commands deduplicate
        # (idempotency), so distinct payloads drive the budget: 1/2 done →
        # a second distinct replan is attempted → 2/2 → the third is refused.
        out2 = plane.command("REPLAN", actor="human",
                             payload={"reason": "second attempt"})
        c.chk("T24: second distinct replan within budget",
              out2["ok"], out2.get("error"))
        out3 = plane.command("REPLAN", actor="human",
                             payload={"reason": "third attempt"})
        c.chk("T24: replan budget enforced for human commands",
              not out3["ok"] and "budget" in out3["error"], out3.get("error"))
        out_same = plane.command("REPLAN", actor="human",
                                 payload={"reason": "second attempt"})
        c.chk("T24: identical retry of an applied command is idempotent",
              out_same["ok"] and out_same.get("already") is True)
        # approval gateway still gates high-impact human replans (§39)
        h2, p2, pr2 = make_project(
            os.path.join(d, "b"), planner_graphs=[PH8.graph_json(PH8.V2)],
            scripts=scripts, policy=ApprovalPolicy())
        h2.run(p2)
        out3 = h2._control_plane(p2).command(
            "REPLAN", actor="human", payload={"reason": "again"})
        c.chk("T24: Phase 9 approval still gates human replans",
              out3["ok"]
              and out3["result"]["replan"]["status"] == "waiting_approval",
              out3.get("result"))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T25/T26/T27 — PROVIDE_INFORMATION: artifact, provenance, conflicts
# ------------------------------------------------------------------------- #
@section
def test_t25_t26_t27_human_information(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        plane = h._control_plane(p)
        out = plane.command("PROVIDE_INFORMATION", actor="human",
                            payload={"key": "client_age", "value": "40"})
        c.chk("T25: information applied", out["ok"])
        final = load_state(d, p) or {}
        arts = final.get("artifacts") or {}
        c.chk("T25: human-input ARTIFACT created",
              "human-input" in arts, sorted(arts))
        entry = ((arts.get("human-input") or {}).get("payload")
                 or {}).get("entries", [{}])[-1]
        c.chk("T26: provenance on the entry",
              entry.get("source_type") == "human"
              and entry.get("actor") == "human" and entry.get("at"),
              entry)
        prov = (arts.get("human-input") or {}).get("provenance") or []
        c.chk("T26: artifact-level provenance registered",
              prov and prov[0].get("source_type") == "human")
        from runtime import artifact_registry as reg
        c.chk("T26: human-input registered in the artifact registry",
              reg.by_type(final, "human-input") is not None)
        # T27: conflicting update is recorded, never silently overwritten
        out2 = plane.command("PROVIDE_INFORMATION", actor="human",
                             payload={"key": "client_age", "value": "41"})
        final = load_state(d, p) or {}
        entries = (((final.get("artifacts") or {}).get("human-input") or {})
                   .get("payload") or {}).get("entries", [])
        c.chk("T27: conflict detected and recorded",
              out2["result"]["entry"]["conflict"] is True
              and entries[-1]["previous_value"] == "40"
              and entries[-1]["value"] == "41", entries[-1])
        c.chk("T27: both values preserved (append, not overwrite)",
              len([e for e in entries if e["key"] == "client_age"]) == 2)
        state_events = [e.get("type") for e in final.get("events") or []]
        c.chk("T27: FACT_CONFLICT recorded in CaseState events",
              "FACT_CONFLICT" in state_events)
        # same value again → no conflict (unit-level: an identical command
        # would be deduplicated by command idempotency, which is correct —
        # so exercise the conflict logic directly)
        state = load_state(d, p)
        e3 = h._apply_human_information(p, state, "client_age", "41", "human")
        c.chk("T27: same value again → no conflict",
              e3["conflict"] is False, e3)
        # invalid input refused
        out4 = plane.command("PROVIDE_INFORMATION", actor="human",
                             payload={"value": "x"})
        c.chk("T27: empty key refused", not out4["ok"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T28/T29/T30/T31 — crash recovery across supervisor states and commands
# ------------------------------------------------------------------------- #
@section
def test_t28_crash_while_paused(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        h._control_plane(p).command("PAUSE", actor="human")
        # new process
        provider2 = TaskScriptProvider(copy.deepcopy(PH8.SCRIPTS))
        h2 = LongRunningHarness(d, agent_executor=provider2)
        p2 = load_project(d, p.project_id)
        r = h2.run(p2)
        c.chk("T28: restart does NOT continue a paused project",
              r["status"] == "paused" and provider2.calls == [],
              (r["status"], provider2.calls))
        c.chk("T28: supervisor still PAUSED after restart",
              h2._control_plane(p2).supervisor()["status"] == "PAUSED")
    finally:
        cleanup(d)


@section
def test_t29_crash_during_pause_command(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        # forge a crash AFTER the command was persisted, BEFORE it applied
        from runtime.control import make_command
        cmd = make_command(p.project_id, "PAUSE", actor="human")
        ControlStore(p._dir).append_command(cmd)
        provider2 = TaskScriptProvider(copy.deepcopy(PH8.SCRIPTS))
        h2 = LongRunningHarness(d, agent_executor=provider2)
        p2 = load_project(d, p.project_id)
        r = h2.run(p2)
        c.chk("T29: pending command recovered idempotently → PAUSED",
              r["status"] == "paused"
              and h2._control_plane(p2).supervisor()["status"] == "PAUSED")
        applied = [x for x in ControlStore(p._dir).commands()
                   if x["status"] == "APPLIED"]
        c.chk("T29: exactly one applied PAUSE (no double-apply)",
              len(applied) == 1, len(applied))
        c.chk("T29: nothing executed during recovery",
              provider2.calls == [])
    finally:
        cleanup(d)


@section
def test_t30_crash_during_resume(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d, planner_graphs=[PH8.graph_json(PH8.V2)])
        plane = h._control_plane(p)
        plane.command("PAUSE", actor="human")
        # crash between human RESUME and execution
        from runtime.control import make_command
        cmd = make_command(p.project_id, "RESUME", actor="human")
        ControlStore(p._dir).append_command(cmd)
        provider2 = TaskScriptProvider(copy.deepcopy(PH8.SCRIPTS))
        h2 = LongRunningHarness(d, agent_executor=provider2,
                                planner_provider=FakePlannerProvider(
                                    [PH8.graph_json(PH8.V2)]))
        p2 = load_project(d, p.project_id)
        r = h2.run(p2)
        c.chk("T30: pending RESUME recovered → execution continued",
              r["status"] == "completed", r["status"])
        c.chk("T30: supervisor RUNNING again",
              h2._control_plane(p2).supervisor()["status"] == "RUNNING")
    finally:
        cleanup(d)


@section
def test_t31_crash_during_replan_command(c: Checks):
    d = fresh_dir()
    try:
        scripts = copy.deepcopy(PH8.SCRIPTS)
        scripts["task_risk"] = [("record_risk_assessment", PH8.RISK_ARGS), "done"]
        h, p, provider = make_project(d, planner_graphs=[], scripts=scripts)
        h.run(p)   # completes on v1, no replans
        from runtime.control import make_command
        cmd = make_command(p.project_id, "REPLAN", actor="human",
                           payload={"reason": "upgrade"})
        ControlStore(p._dir).append_command(cmd)
        provider2 = TaskScriptProvider(copy.deepcopy(scripts))
        h2 = LongRunningHarness(
            d, agent_executor=provider2,
            planner_provider=FakePlannerProvider([PH8.graph_json(PH8.V2)]))
        p2 = load_project(d, p.project_id)
        r = h2.run(p2)
        c.chk("T31: pending REPLAN recovered → v2 applied",
              p2.current_graph_revision == 2
              and p2.replans[0]["trigger"] == "HUMAN_REQUEST",
              (p2.current_graph_revision, r["status"]))
        applied = [x for x in ControlStore(p._dir).commands()
                   if x["status"] == "APPLIED"]
        c.chk("T31: replan command applied exactly once", len(applied) == 1)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T33 — notification persistence
# ------------------------------------------------------------------------- #
@section
def test_t33_notification_persistence(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = a_failing_project(d, planner_graphs=[])
        h.run(p)   # task_risk fails → MEDIUM → NOTIFY
        path = os.path.join(p._dir, "notifications.jsonl")
        c.chk("T33: notifications.jsonl persisted", os.path.exists(path))
        notifs = ControlStore(p._dir).notifications()
        c.chk("T33: notifications carry severity + signal",
              notifs and all(n.get("severity") and n.get("signal_type")
                             and n.get("status") == "PENDING" for n in notifs))
        c.chk("T33: intervention_notified event emitted",
              len(events_of(p, "intervention_notified")) >= 1)
        # a new process reads the same notifications
        p2 = load_project(d, p.project_id)
        c.chk("T33: notifications survive reload",
              ControlStore(p2._dir).notifications() == notifs)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T35 — event integrity for monitor + command lifecycles
# ------------------------------------------------------------------------- #
@section
def test_t35_event_integrity(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = make_project(d)
        plane = h._control_plane(p)
        plane.command("PAUSE", actor="human")
        evs = p.events()
        types = [e["event_type"] for e in evs]
        for needed in ("control_command_received", "control_command_applied",
                       "runtime_pausing", "runtime_paused"):
            c.chk("T35: %s present exactly once" % needed,
                  types.count(needed) == 1, types.count(needed))
        order = {t: i for i, t in enumerate(types)}
        c.chk("T35: command order received < applied",
              order["control_command_received"]
              < order["control_command_applied"])
        c.chk("T35: runtime order pausing < paused",
              order["runtime_pausing"] < order["runtime_paused"])
        refused = plane.command("PAUSE", actor="agent:x")
        c.chk("T35: refused command emits control_command_rejected",
              not refused["ok"]
              and len(events_of(p, "control_command_rejected")) == 1)
        # monitor events carry the required identifiers
        h, p2, pr2 = a_failing_project(os.path.join(d, "b"), planner_graphs=[])
        h.run(p2)
        sig = events_of(p2, "monitor_signal_detected")
        c.chk("T35: monitor_signal_detected carries signal fields",
              sig and all("signal_type" in e and "severity" in e for e in sig))
        c.chk("T35: events carry project_id",
              all(e.get("project_id") == p2.project_id
                  for e in events_of(p2, "monitor_signal_detected")))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T36 — checkpoint integrity with supervisor fields
# ------------------------------------------------------------------------- #
@section
def test_t36_checkpoint_integrity(c: Checks):
    d = fresh_dir()
    try:
        h, p, provider = a_failing_project(d, planner_graphs=[])
        h.run(p)
        h._control_plane(p).command("PAUSE", actor="human")
        cps = p.checkpoints()
        c.chk("T36: checkpoints carry supervisor fields",
              all("supervisor_status" in cp and "risk_level" in cp
                  for cp in cps), [list(cps[0])][:1])
        last = cps[-1]
        c.chk("T36: paused checkpoint reflects supervisor state",
              last.get("supervisor_status") == "PAUSED"
              and last.get("risk_level") in ("LOW", "MEDIUM", "HIGH", "CRITICAL"),
              last)
        c.chk("T36: last_control_command_id recorded",
              last.get("last_control_command_id"), last)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T37/T38/T39 — Phase 9 / Phase 8 / Phase 7 compatibility with monitor on
# ------------------------------------------------------------------------- #
@section
def test_t37_phase9_compatibility(c: Checks):
    d = fresh_dir()
    try:
        # the Phase 9 waiting flow with the monitor observing
        h, p, provider = make_project(d, policy=ApprovalPolicy())
        r = h.run(p)
        c.chk("T37: approval waiting still primary (WAITING over PAUSED)",
              r["status"] == "waiting_approval", r["status"])
        from runtime.approval import ApprovalStore
        appr = ApprovalStore(p._dir).pending()[0]
        h._control_plane(p).command(
            "APPROVE", actor="human", payload={"approval_id": appr["approval_id"]})
        res = h.resume_approval(p, appr["approval_id"])
        c.chk("T37: approve + Harness resume completes",
              res["status"] == "completed", res["status"])
        c.chk("T37: monitor did not pause the approval flow",
              h._control_plane(p).supervisor()["status"]
              in ("RUNNING", "WAITING_HUMAN"))
    finally:
        cleanup(d)


@section
def test_t38_t39_phase8_phase7_compatibility(c: Checks):
    for tag, mc in (("T38 sequential", 1), ("T39 parallel", 2)):
        d = fresh_dir()
        try:
            h, p, provider = make_project(d, max_concurrency=mc)
            r = h.run(p)
            c.chk("%s: Phase 8 replan completes with monitor on" % tag,
                  r["status"] == "completed"
                  and p.current_graph_revision == 2, r["status"])
            c.chk("%s: autonomous — no supervisor pause" % tag,
                  h._control_plane(p).supervisor()["status"] == "RUNNING")
            # worker isolation markers intact (Phase 7)
            evs = [e["event_type"] for e in p.events()]
            if mc == 1:
                c.chk("T38: sequential path unchanged (no task_scheduled)",
                      "task_scheduled" not in evs)
            else:
                c.chk("T39: parallel path intact (task_scheduled present)",
                      "task_scheduled" in evs)
        finally:
            cleanup(d)


# ------------------------------------------------------------------------- #
# T40 — four-agent HOTL E2E: Case A autonomous NOTIFY, Case B PAUSE+RESUME
# ------------------------------------------------------------------------- #
@section
def test_t40_four_agent_hotl_e2e(c: Checks):
    # ---- Case A: repeated runtime trouble → HIGH → NOTIFY, run continues --
    d = fresh_dir()
    try:
        h, p, provider = make_project(
            d, planner_graphs=[PH8.graph_json(PH8.T24_V2)],
            graph=copy.deepcopy(PH8.T24_V1), scripts=copy.deepcopy(PH8.T24_SCRIPTS))
        r = h.run(p)
        started = {e.get("agent_id") for e in p.events()
                   if e["event_type"] == "agent_started"}
        c.chk("T40A: four specialists executed autonomously",
              started == {"insurance_analyst", "knowledge_specialist",
                          "product_specialist", "report_specialist"}, started)
        c.chk("T40A: project COMPLETED — HOTL did not block execution",
              r["status"] == "completed", r["status"])
        notifs = ControlStore(p._dir).notifications()
        c.chk("T40A: human was NOTIFIED of the runtime signals",
              len(notifs) >= 1
              and any(n["signal_type"] == "SIGNAL_TASK_FAILURE"
                      for n in notifs),
              [(n["signal_type"], n["severity"]) for n in notifs])
        c.chk("T40A: supervisor stayed RUNNING (no pause, no waiting)",
              h._control_plane(p).supervisor()["status"] == "RUNNING")
    finally:
        cleanup(d)

    # ---- Case B: HIGH → configured PAUSE at the safe barrier → RESUME -----
    d = fresh_dir()
    try:
        h, p, provider = make_project(
            d, planner_graphs=["{broken"] * 3, max_replans=1,
            graph=copy.deepcopy(PH8.T24_V1), scripts=copy.deepcopy(PH8.T24_SCRIPTS),
            intervention_policy=InterventionPolicy(high=INTERVENTION_PAUSE))
        r = h.run(p)
        c.chk("T40B: supervisor PAUSED at the safe barrier",
              r["status"] == "paused"
              and h._control_plane(p).supervisor()["status"] == "PAUSED",
              r["status"])
        c.chk("T40B: pause reason was the replan-budget exhaustion",
              any(n["signal_type"] == "SIGNAL_REPLAN_EXHAUSTED"
                  for n in ControlStore(p._dir).notifications()))
        plane = h._control_plane(p)
        c.chk("T40B: paused mid-graph (unfinished work remains)",
              any(t["status"] not in ("PASSED", "COMPLETED")
                  for t in p.tasks),
              {t["task_id"]: t["status"] for t in p.tasks})
        plane.command("RESUME", actor="human")
        r2 = h.run(p)
        c.chk("T40B: human RESUME continues to a terminal state",
              r2["status"] in ("needs_review", "completed"), r2["status"])
        c.chk("T40B: supervisor RUNNING after resume",
              plane.supervisor()["status"] == "RUNNING")
    finally:
        cleanup(d)


def main():
    return run_sections(SECTIONS, "webui_test_hotl_log.txt",
                        "RUNTIME HUMAN-ON-THE-LOOP")


if __name__ == "__main__":
    sys.exit(main())
