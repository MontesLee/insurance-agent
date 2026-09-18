"""Phase 7 — DAG-aware Bounded Parallel Scheduler tests (T1–T21).

Covers: runnable DAG calculation, dependency barrier, TRUE parallel overlap
(proved with a blocking probe, not event order), max_concurrency bound, no
duplicate execution, independent branches, downstream barrier, branch failure
isolation, failure blocking downstream, repair + repair exhaustion under
parallelism, artifact uniqueness, CaseState safety, checkpoints, crash
recovery (PENDING and RUNNING variants), MessageBus compatibility, handoff
-driven parallel activation, event integrity, deterministic final state and
Phase 6 sequential compatibility.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_parallel_scheduler.py`.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch
from runtime import artifact_registry as reg
from runtime import tasks as tk
from runtime import checkpoint as cp
from runtime.agent.model import FakeLLMProvider
from runtime.harness import LongRunningHarness, load_project
from runtime.state import case_state as cs
from runtime.state import store as ss

SECTIONS = []
WF = orch.load_workflow()

with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                       "case-full-chain.json"), encoding="utf-8") as f:
    FIX = json.load(f)


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="par_", dir=os.path.join(REPO, "tmp"))


def cleanup(d: str) -> None:
    """Delete a test's harness root (same semantics as the sibling suites'
    `shutil.rmtree(d, ignore_errors=True)`, centralized so every section in
    this file and the E2E file cleans up through one path)."""
    shutil.rmtree(d, ignore_errors=True)


def diamond_graph():
    """A → (B ∥ C) → D — the canonical Phase 7 DAG."""
    return {"tasks": [
        {"task_id": "task_A", "task_type": "client_profile"},
        {"task_id": "task_B", "task_type": "risk_analysis",
         "dependencies": ["task_A"]},
        {"task_id": "task_C", "task_type": "requirement_analysis",
         "dependencies": ["task_A"]},
        {"task_id": "task_D", "task_type": "product_candidates",
         "dependencies": ["task_B", "task_C"]},
    ]}


# valid artifacts per task_type — the dialogue fixtures in their CANONICAL
# form (the same adapters seed_case uses), so the Harness eval passes them
import adapters.client_intake_adapter as _cia
import adapters.requirement_analysis_adapter as _raa
import adapters.risk_analysis_adapter as _rka

GOOD = {
    "client_profile": _cia.to_canonical(copy.deepcopy(FIX["artifacts"]["client-profile"])),
    "requirement_analysis": _raa.to_canonical(copy.deepcopy(FIX["artifacts"]["requirement-analysis"])),
    "risk_analysis": _rka.to_canonical(copy.deepcopy(FIX["artifacts"]["risk-assessment"])),
    "product_candidates": {"candidates": [{
        "candidate_id": "C001", "product_id": "P001",
        "product_name": "demo-product", "company": "demo-company",
        "admissible": True}]},
}
# catalog-invariant violation — repairable (catalog_exists → DROP_INVALID_PRODUCTS)
BAD_PRODUCT = {"candidates": [{
    "candidate_id": "C001", "product_id": "BAD_X",
    "product_name": "no-such-product", "company": "demo-company",
    "admissible": True}]}
# contract violation — NOT repairable (immediate NEEDS_REVIEW after 1 eval)
BAD_RISK = {}


def make_project(root, graph, seeds=None, max_concurrency=2, agent_executor=None):
    h = LongRunningHarness(root, agent_executor=agent_executor,
                           max_concurrency=max_concurrency)
    p = h.create_project("par", task_graph=graph)
    state = orch.seed_case(WF, p.case_id, copy.deepcopy(seeds or {}))
    ss.save(state, os.path.join(root, p.project_id, "case"))
    return h, p


def load_state(root, project):
    return ss.load(os.path.join(root, project.project_id, "case"), project.case_id)


# ------------------------------------------------------------------------- #
# deterministic test instrumentation (§6: prove overlap, don't infer it)
# ------------------------------------------------------------------------- #
class OverlapProbe:
    """Concurrency probe: an ORDERED enter/exit log, live-concurrency
    tracking, and a release that fires only when `need` watched tasks are
    inside simultaneously — the true-overlap proof for T3/T4/T18.

    `watch`: None (every key watched) or a set of keys; unwatched keys are
    still counted/logged but never block — so solo tasks don't pay timeouts.
    """

    def __init__(self, need=2, timeout=5.0, watch=None):
        self.need, self.timeout = need, timeout
        self.watch = watch
        self._lock = threading.Lock()
        self._release = threading.Event()
        self._watched_inside = 0
        self.active = 0
        self.max_active = 0
        self.log = []          # ordered [(action, key), ...]

    def _watched(self, key):
        return self.watch is None or key in self.watch

    def enter(self, key):
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.log.append(("enter", key))
            if self._watched(key):
                self._watched_inside += 1
                if self._watched_inside >= self.need:
                    self._release.set()

    def wait(self, key):
        if self._watched(key):
            self._release.wait(self.timeout)

    def exit(self, key):
        with self._lock:
            self.active -= 1
            if self._watched(key):
                self._watched_inside = max(0, self._watched_inside - 1)
            self.log.append(("exit", key))

    @property
    def overlapped(self):
        return self._release.is_set()

    def enters(self):
        return [k for a, k in self.log if a == "enter"]

    def index_of(self, action, key):
        for i, (a, k) in enumerate(self.log):
            if (a, k) == (action, key):
                return i
        return -1


class ScriptAgentExecutor:
    """Deterministic fake agent executor for the parallel scheduler.

    scripts: task_type -> list of artifacts returned per successive call
    (worker call first, repair calls after); when a queue empties, the last
    consumed artifact repeats. The artifact is stored through the CANONICAL
    put_artifact + artifact_registry path on whatever CaseState it is given
    (worker copy during execution, main state during Harness repair).
    """

    def __init__(self, scripts=None, probe=None):
        self.name = "script-agent"
        self.model = "script"
        self.scripts = {k: list(v) for k, v in (scripts or {}).items()}
        self.probe = probe
        self.calls = []        # task_id per execute() invocation
        self._last = {}

    def execute(self, *, agent_id, task, project, case_state, emit=None):
        from runtime.agents.executor import AgentExecutionResult
        from runtime.planner import registry as pr
        tid, tt = task["task_id"], task["task_type"]
        self.calls.append(tid)
        if self.probe:
            self.probe.enter(tid)
            self.probe.wait(tid)
        try:
            queue = self.scripts.get(tt) or []
            if queue:
                art = queue.pop(0)
                self._last[tt] = art
            elif tt in self._last:
                art = self._last[tt]
            else:
                return AgentExecutionResult("AGENT_FAILED",
                                            error_code="NO_SCRIPT_FOR_%s" % tt)
            pdef = pr.get(tt)
            art_type, stage_id = pdef["produced_artifacts"][0], pdef["stage_id"]
            if art_type not in (case_state.get("artifacts") or {}):
                cs.put_artifact(case_state, art_type, art, stage_id)
            else:
                # repair replacement — mirrors the tool layer's documented
                # dialogue-refinement path (put_artifact refuses overwrites)
                case_state["artifacts"][art_type] = copy.deepcopy(art)
                case_state["stages"][stage_id]["artifact_fingerprint"] = None
            reg.register(case_state, art_type, case_state["artifacts"][art_type],
                         {"id": stage_id, "skill": stage_id, "consumes": []})
            return AgentExecutionResult("ARTIFACT_READY")
        finally:
            if self.probe:
                self.probe.exit(tid)


def all_good_scripts():
    return {tt: [copy.deepcopy(a)] for tt, a in GOOD.items()}


# ------------------------------------------------------------------------- #
# T1: DAG runnable calculation
# ------------------------------------------------------------------------- #
@section
def test_t1_runnable(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_project(d, diamond_graph())
        c.chk("T1: only A runnable initially", h._compute_runnable(p) == ["task_A"],
              h._compute_runnable(p))
        p._set_task("task_A", status="PASSED")
        r = h._compute_runnable(p)
        c.chk("T1: B,C runnable after A PASS", r == ["task_B", "task_C"], r)
        p._set_task("task_B", status="PASSED")
        c.chk("T1: only C runnable (D waits for C)",
              h._compute_runnable(p) == ["task_C"], h._compute_runnable(p))
        p._set_task("task_C", status="PASSED")
        c.chk("T1: D runnable after B,C", h._compute_runnable(p) == ["task_D"],
              h._compute_runnable(p))
        p._set_task("task_D", status="PASSED")
        c.chk("T1: nothing runnable when all terminal",
              h._compute_runnable(p) == [], h._compute_runnable(p))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T2: Dependency barrier
# ------------------------------------------------------------------------- #
@section
def test_t2_dependency_barrier(c: Checks):
    d = fresh_dir()
    try:
        h, p = make_project(d, diamond_graph())
        p._set_task("task_A", status="PASSED")
        p._set_task("task_B", status="RUNNING")
        r = h._compute_runnable(p)
        c.chk("T2: D NOT runnable while B RUNNING (P0 barrier)",
              "task_D" not in r, r)
        c.chk("T2: C still runnable", "task_C" in r, r)
        # B terminal-failed → D becomes BLOCKED territory, never runnable
        p._set_task("task_B", status="NEEDS_REVIEW")
        r = h._compute_runnable(p)
        c.chk("T2: D not runnable after B NEEDS_REVIEW", "task_D" not in r, r)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T3: True parallel overlap (blocking probe proof, §6)
# ------------------------------------------------------------------------- #
@section
def test_t3_true_parallel(c: Checks):
    d = fresh_dir()
    try:
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        ex = ScriptAgentExecutor(all_good_scripts(), probe=probe)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        result = h.run(p)
        # the release only fires while BOTH B and C are inside execute()
        # simultaneously — B was blocked in wait() when C entered
        c.chk("T3: true overlap proven (B and C inside execute() together)",
              probe.overlapped, probe.log)
        c.chk("T3: both branch tasks PASSED",
              p.get_task("task_B")["status"] == "PASSED"
              and p.get_task("task_C")["status"] == "PASSED")
        c.chk("T3: project completed", result["status"] == "completed",
              result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T4: max_concurrency bound
# ------------------------------------------------------------------------- #
@section
def test_t4_max_concurrency(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_%d" % i, "task_type": tt}
            for i, tt in enumerate(["client_profile", "requirement_analysis",
                                    "risk_analysis", "product_candidates"])]}
        probe = OverlapProbe(need=2)  # all watched: every batch must pair up
        ex = ScriptAgentExecutor(all_good_scripts(), probe=probe)
        h, p = make_project(d, graph, agent_executor=ex, max_concurrency=2)
        result = h.run(p)
        c.chk("T4: run completed", result["status"] == "completed",
              result["status"])
        c.chk("T4: max observed running == 2 (bound fully used)",
              probe.max_active == 2, probe.max_active)
        c.chk("T4: max observed running <= max_concurrency",
              probe.max_active <= 2, probe.max_active)
        c.chk("T4: all 4 tasks executed", len(ex.calls) == 4, ex.calls)
        # cross-check from the durable event log (scheduler-authoritative)
        running, max_ev = 0, 0
        for e in p.events():
            if e["event_type"] == "task_started":
                running += 1
                max_ev = max(max_ev, running)
            elif e["event_type"] in ("task_completed", "task_failed"):
                running -= 1
        c.chk("T4: event log confirms bound (max running <= 2)", max_ev <= 2, max_ev)
        c.chk("T4: event log shows parallel batches (max running == 2)",
              max_ev == 2, max_ev)
    finally:
        cleanup(d)


@section
def test_t4_invalid_concurrency(c: Checks):
    d = fresh_dir()
    try:
        for bad in (0, -1, 1.5, "2", None):
            try:
                LongRunningHarness(d, max_concurrency=bad)
                c.chk("T4: max_concurrency=%r rejected" % (bad,), False)
            except (ValueError, TypeError):
                c.chk("T4: max_concurrency=%r rejected" % (bad,), True)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T5: No duplicate execution
# ------------------------------------------------------------------------- #
@section
def test_t5_no_duplicate(c: Checks):
    d = fresh_dir()
    try:
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        ex = ScriptAgentExecutor(all_good_scripts(), probe=probe)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        h.run(p)
        enters = probe.enters()
        c.chk("T5: each task entered exactly once",
              all(enters.count(t) == 1 for t in enters), enters)
        c.chk("T5: 4 tasks, 4 entries", len(enters) == 4, enters)
        c.chk("T5: no task_id executed twice", len(ex.calls) == len(set(ex.calls)),
              ex.calls)
        c.chk("T5: scheduler running-ledger empty after run",
              h._running_task_ids == set(), h._running_task_ids)
        # a second run() must not re-execute terminal tasks (§14)
        before = list(ex.calls)
        h.run(p)
        c.chk("T5: second run() executes nothing", ex.calls == before,
              ex.calls[len(before):])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T6/T7: Independent branches + downstream barrier
# ------------------------------------------------------------------------- #
@section
def test_t6_t7_branches_and_barrier(c: Checks):
    d = fresh_dir()
    try:
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        ex = ScriptAgentExecutor(all_good_scripts(), probe=probe)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        h.run(p)
        log = probe.log
        # T6: B and C overlapped (B entered before C exited)
        c.chk("T6: B entered before C exited (branches independent)",
              probe.index_of("enter", "task_B") < probe.index_of("exit", "task_C"),
              log)
        c.chk("T6: C entered before B exited",
              probe.index_of("enter", "task_C") < probe.index_of("exit", "task_B"),
              log)
        # T7: D started only after BOTH branches finished
        c.chk("T7: D entered after B exited",
              probe.index_of("enter", "task_D") > probe.index_of("exit", "task_B"),
              log)
        c.chk("T7: D entered after C exited",
              probe.index_of("enter", "task_D") > probe.index_of("exit", "task_C"),
              log)
        # ...and from the durable events (§T7: deterministic ordering)
        evs = p.events()

        def ev_index(evt, tid):
            return next((i for i, e in enumerate(evs)
                         if e["event_type"] == evt and e.get("task_id") == tid), -1)

        d_start = ev_index("task_started", "task_D")
        c.chk("T7: event task_started(D) after task_completed(B)",
              d_start > ev_index("task_completed", "task_B"), d_start)
        c.chk("T7: event task_started(D) after task_completed(C)",
              d_start > ev_index("task_completed", "task_C"), d_start)
        c.chk("T7: D PASSED", p.get_task("task_D")["status"] == "PASSED")
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T8/T9: Branch failure isolation + downstream BLOCKED
# ------------------------------------------------------------------------- #
@section
def test_t8_t9_failure(c: Checks):
    d = fresh_dir()
    try:
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        scripts = all_good_scripts()
        scripts["risk_analysis"] = [BAD_RISK]   # B fails eval (not repairable)
        ex = ScriptAgentExecutor(scripts, probe=probe)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        result = h.run(p)
        # T8: B and C ran together; C passed DESPITE B failing
        c.chk("T8: B and C overlapped in the same batch", probe.overlapped,
              probe.log)
        c.chk("T8: B → NEEDS_REVIEW",
              p.get_task("task_B")["status"] == "NEEDS_REVIEW",
              p.get_task("task_B")["status"])
        c.chk("T8: C → PASSED (isolated from B's failure)",
              p.get_task("task_C")["status"] == "PASSED",
              p.get_task("task_C")["status"])
        c.chk("T8: C not cancelled by B failure",
              "task_C" in probe.enters(), probe.enters())
        # T9: D blocked by B's NEEDS_REVIEW
        c.chk("T9: D → BLOCKED",
              p.get_task("task_D")["status"] == "BLOCKED",
              p.get_task("task_D")["status"])
        c.chk("T9: D never executed", "task_D" not in probe.enters(),
              probe.enters())
        blocked_ev = [e for e in p.events()
                      if e["event_type"] == "task_failed"
                      and e.get("task_id") == "task_D"]
        c.chk("T9: BLOCKED task_failed event recorded", len(blocked_ev) == 1,
              blocked_ev)
        c.chk("T8/T9: project needs_review", result["status"] == "needs_review",
              result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T10/T11: Repair + repair exhaustion under parallelism
# ------------------------------------------------------------------------- #
@section
def test_t10_repair(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_P", "task_type": "product_candidates"}]}
        scripts = {"product_candidates": [copy.deepcopy(BAD_PRODUCT),
                                          copy.deepcopy(GOOD["product_candidates"])]}
        ex = ScriptAgentExecutor(scripts)
        h, p = make_project(d, graph, agent_executor=ex, max_concurrency=2)
        result = h.run(p)
        final = load_state(d, p) or {}
        evals = [e for e in final.get("evaluations", [])
                 if e.get("artifact_type") == "product-candidates"]
        c.chk("T10: first eval FAIL then repair PASS → task PASSED",
              p.get_task("task_P")["status"] == "PASSED",
              p.get_task("task_P")["status"])
        c.chk("T10: exactly 2 evals (FAIL → PASS)", len(evals) == 2,
              [(e["eval_id"], e["status"]) for e in evals])
        c.chk("T10: eval sequence FAIL, PASS",
              [e["status"] for e in evals] == ["FAIL", "PASS"],
              [e["status"] for e in evals])
        c.chk("T10: agent executed exactly twice (1 worker + 1 repair)",
              ex.calls.count("task_P") == 2, ex.calls)
        c.chk("T10: no concurrent duplicate execution",
              ex.calls.count("task_P") == len(ex.calls), ex.calls)
    finally:
        cleanup(d)


@section
def test_t11_repair_exhaustion(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_P", "task_type": "product_candidates"}]}
        scripts = {"product_candidates": [copy.deepcopy(BAD_PRODUCT)] * 5}
        ex = ScriptAgentExecutor(scripts)
        h, p = make_project(d, graph, agent_executor=ex, max_concurrency=2)
        result = h.run(p)
        final = load_state(d, p) or {}
        evals = [e for e in final.get("evaluations", [])
                 if e.get("artifact_type") == "product-candidates"]
        c.chk("T11: task NEEDS_REVIEW after exhaustion",
              p.get_task("task_P")["status"] == "NEEDS_REVIEW",
              p.get_task("task_P")["status"])
        c.chk("T11: exactly 3 evals (1 initial + 2 repairs)",
              len(evals) == 3, [(e["eval_id"], e["status"]) for e in evals])
        c.chk("T11: agent executed 3 times total (repairs ≤ 2)",
              ex.calls.count("task_P") == 3, ex.calls)
        c.chk("T11: never more than 2 repairs",
              ex.calls.count("task_P") - 1 <= 2, ex.calls)
        evs = [e["event_type"] for e in p.events()]
        c.chk("T11: repair_exhausted lifecycle observed",
              "task_failed" in evs, evs[:10])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# §9: a worker result alone can never PASS (no self-pass under parallelism)
# ------------------------------------------------------------------------- #
@section
def test_t9b_no_worker_self_pass(c: Checks):
    from runtime.agents.executor import AgentExecutionResult

    class SelfPassExecutor:
        """A misbehaving executor that claims OK without producing anything."""
        name, model = "self-pass", "self-pass"
        calls = []

        def execute(self, *, agent_id, task, project, case_state, emit=None):
            self.calls.append(task["task_id"])
            return AgentExecutionResult("OK")   # attempted self-PASS

    d = fresh_dir()
    try:
        graph = {"tasks": [{"task_id": "task_S", "task_type": "risk_analysis"}]}
        h, p = make_project(d, graph, agent_executor=SelfPassExecutor(),
                            max_concurrency=2)
        h.run(p)
        c.chk("NO-SELF-PASS: worker 'OK' does not become task PASS",
              p.get_task("task_S")["status"] == "NEEDS_REVIEW",
              p.get_task("task_S")["status"])
        final = load_state(d, p) or {}
        passed = [e for e in final.get("evaluations", []) if e["status"] == "PASS"]
        c.chk("NO-SELF-PASS: nothing eval-PASSed without an artifact",
              passed == [], [(e["eval_id"], e["artifact_type"]) for e in passed])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T12/T13: Artifact uniqueness + CaseState safety
# ------------------------------------------------------------------------- #
@section
def test_t12_t13_artifact_safety(c: Checks):
    d = fresh_dir()
    try:
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        ex = ScriptAgentExecutor(all_good_scripts(), probe=probe)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        h.run(p)
        final = load_state(d, p) or {}
        reg_arts = final.get("artifact_registry") or {}
        ids = [rec["artifact_id"] for rec in reg_arts.values()]
        c.chk("T12: artifact_ids unique after parallel merge",
              len(ids) == len(set(ids)), ids)
        types = sorted((final.get("artifacts") or {}).keys())
        c.chk("T12: all four branch artifacts produced",
              types == ["client-profile", "product-candidates",
                        "requirement-analysis", "risk-assessment"], types)
        # T13: no lost update — BOTH parallel branch artifacts exist & valid
        ok, problems = reg.verify(final)
        c.chk("T13: artifact registry verify (fingerprints intact)", ok, problems)
        ok, errs = cs.validate(final)
        c.chk("T13: CaseState schema valid", ok, errs[:3])
        ok, problems = tk.check_mirror(final)
        c.chk("T13: stage/task ledger mirror consistent", ok, problems[:3])
        ok, reasons = cp.validate(final, p.case_id)
        c.chk("T13: checkpoint-validate final state", ok, reasons[:3])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T14: Checkpoint per terminal task
# ------------------------------------------------------------------------- #
@section
def test_t14_checkpoint(c: Checks):
    d = fresh_dir()
    try:
        scripts = all_good_scripts()
        scripts["risk_analysis"] = [BAD_RISK]   # one failure, three passes
        ex = ScriptAgentExecutor(scripts)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        h.run(p)
        evs = p.events()
        terminal_started = [e for e in evs if e["event_type"] == "task_started"]
        ck_after = [e for e in evs if e["event_type"] == "checkpoint_created"]
        cps = p.checkpoints()
        c.chk("T14: checkpoint log non-empty", len(cps) >= 1, len(cps))
        c.chk("T14: a checkpoint for EVERY terminal task",
              len(ck_after) >= len(terminal_started),
              (len(ck_after), len(terminal_started)))
        # every task that reached a terminal state has a checkpoint entry
        ck_tids = {e.get("task_id") for e in ck_after}
        started_tids = {e.get("task_id") for e in terminal_started}
        c.chk("T14: per-task checkpoint ids cover all started tasks",
              started_tids <= ck_tids, sorted(started_tids - ck_tids))
        last = cps[-1]
        c.chk("T14: checkpoint records task states",
              {"completed_task_ids", "pending_task_ids"} <= set(last), list(last))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T15: Recovery — completed tasks skipped, no duplicate artifact/eval
# ------------------------------------------------------------------------- #
@section
def test_t15_recovery(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_A", "task_type": "client_profile"},
            {"task_id": "task_B", "task_type": "risk_analysis",
             "dependencies": ["task_A"]},
            {"task_id": "task_C", "task_type": "product_candidates",
             "dependencies": ["task_B"]},
        ]}
        # simulate an interruption AFTER A and B passed (artifacts on disk)
        seeds = {"client-profile": FIX["artifacts"]["client-profile"],
                 "risk-assessment": FIX["artifacts"]["risk-assessment"]}
        ex = ScriptAgentExecutor(all_good_scripts())
        h, p = make_project(d, graph, seeds=seeds, agent_executor=ex,
                            max_concurrency=2)
        p._set_task("task_A", status="PASSED")
        p._set_task("task_B", status="PASSED")
        p._save()

        # a NEW process picks the project up from disk
        h2 = LongRunningHarness(d, agent_executor=ex, max_concurrency=2)
        p2 = load_project(d, p.project_id)
        result = h2.run(p2)

        outcomes = {e["task"]: e["outcome"] for e in result["executed"]}
        c.chk("T15: A/B skipped, not re-executed",
              outcomes.get("client_profile") == "SKIPPED"
              and outcomes.get("risk_analysis") == "SKIPPED", outcomes)
        c.chk("T15: C executed and passed",
              p2.get_task("task_C")["status"] == "PASSED",
              p2.get_task("task_C")["status"])
        c.chk("T15: A/B agents never invoked",
              set(ex.calls) == {"task_C"}, ex.calls)
        final = load_state(d, p2) or {}
        eval_counts = {}
        for e in final.get("evaluations", []):
            eval_counts[e["artifact_type"]] = eval_counts.get(e["artifact_type"], 0) + 1
        c.chk("T15: no duplicate evals after recovery",
              all(v == 1 for v in eval_counts.values()), eval_counts)
        ids = [r["artifact_id"] for r in
               (final.get("artifact_registry") or {}).values()]
        c.chk("T15: no duplicate artifacts", len(ids) == len(set(ids)), ids)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T16: Running-task recovery (RUNNING → recovery-safe PENDING)
# ------------------------------------------------------------------------- #
@section
def test_t16_running_task_recovery(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_A", "task_type": "risk_analysis"},
            {"task_id": "task_B", "task_type": "requirement_analysis"},
            {"task_id": "task_C", "task_type": "product_candidates",
             "dependencies": ["task_A", "task_B"]},
        ]}
        seeds = {"requirement-analysis": FIX["artifacts"]["requirement-analysis"]}
        ex = ScriptAgentExecutor(all_good_scripts())
        h, p = make_project(d, graph, seeds=seeds, agent_executor=ex,
                            max_concurrency=2)
        # forge the crash state: A RUNNING, B PASSED, C PENDING
        p._set_task("task_A", status="RUNNING")
        p._set_task("task_B", status="PASSED")
        p._save()

        result = h.run(p)
        evs = p.events()
        rec = [e for e in evs if e["event_type"] == "task_recovered"
               and e.get("task_id") == "task_A"]
        c.chk("T16: RUNNING → PENDING recovery recorded", len(rec) == 1, rec)
        # A was NOT assumed PASS: it really executed (exactly once)
        c.chk("T16: A re-executed exactly once",
              ex.calls.count("task_A") == 1, ex.calls)
        c.chk("T16: A passed via real execution",
              p.get_task("task_A")["status"] == "PASSED",
              p.get_task("task_A")["status"])
        # B skipped (never re-executed)
        c.chk("T16: B skipped, never executed", "task_B" not in ex.calls, ex.calls)
        # C respected the dependency: ran only after A passed
        c.chk("T16: C executed after barrier", ex.calls.count("task_C") == 1,
              ex.calls)
        c.chk("T16: C PASSED", p.get_task("task_C")["status"] == "PASSED",
              p.get_task("task_C")["status"])
        c.chk("T16: project completed", result["status"] == "completed",
              result["status"])
        c.chk("T16: A executes before C (dependency order)",
              ex.calls.index("task_A") < ex.calls.index("task_C"), ex.calls)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T17: MessageBus compatibility (real executor + real MessageBus)
# ------------------------------------------------------------------------- #
RISK_ARGS = {"risks": [
    {"risk_id": "R1-001", "risk_category": "R1_medical",
     "risk_name": "住院费用风险", "priority": "P1_HIGH"}]}


class TaskScriptProvider:
    """Per-task scripted LLM for the REAL SpecialistAgentExecutor.

    Responses are keyed by the task_id parsed from the executor's user
    message, so a SHARED provider stays deterministic regardless of thread
    interleaving (§19). Probe support gives the true-overlap proof.
    """

    def __init__(self, scripts, probe=None):
        self.name = "task-script"
        self.model = "task-script"
        self._scripts = {k: list(v) for k, v in scripts.items()}
        self.probe = probe
        self.calls = []

    def generate(self, messages, tools):
        task_id = ""
        for m in reversed(messages):
            content = m.get("content") or ""
            if m.get("role") == "user" and "Execute task: " in content:
                task_id = content.split("Execute task: ")[1].split(" ")[0]
                break
        if self.probe and task_id:
            self.probe.enter(task_id)
            self.probe.wait(task_id)
            try:
                return self._respond(task_id, messages, tools)
            finally:
                self.probe.exit(task_id)
        return self._respond(task_id, messages, tools)

    def _respond(self, task_id, messages, tools):
        self.calls.append(task_id)
        queue = self._scripts.get(task_id) or []
        item = queue.pop(0) if queue else "done"
        return FakeLLMProvider([item]).generate(messages, tools)


@section
def test_t17_messagebus_compat(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_A", "task_type": "risk_analysis"},
            {"task_id": "task_B", "task_type": "knowledge_search",
             "dependencies": ["task_A"]},
        ]}
        scripts = {
            "task_A": [
                ("record_risk_assessment", RISK_ARGS),
                ("send_agent_message", {
                    "to_agent": "knowledge_specialist",
                    "message_type": "TASK_HANDOFF",
                    "task_id": "task_B",
                    "content": {"request": "请检索医疗相关证据"}}),
                "Risk recorded and handoff sent.",
            ],
            "task_B": [
                ("knowledge_search", {"query": "百万医疗险 重疾险 区别"}),
                "Evidence retrieved.",
            ],
        }
        provider = TaskScriptProvider(scripts)
        h, p = make_project(d, graph, agent_executor=provider,
                            max_concurrency=2)
        result = h.run(p)

        c.chk("T17: parallel run completed", result["status"] == "completed",
              result["status"])
        # message persisted by the WORKER through the real MessageBus
        msg_path = os.path.join(d, p.project_id, "messages.jsonl")
        c.chk("T17: messages.jsonl persisted", os.path.exists(msg_path))
        msgs = []
        if os.path.exists(msg_path):
            with open(msg_path, encoding="utf-8") as f:
                msgs = [json.loads(l) for l in f if l.strip()]
        handoffs = [m for m in msgs if m["message_type"] == "TASK_HANDOFF"]
        c.chk("T17: TASK_HANDOFF persisted", len(handoffs) == 1, msgs)
        if handoffs:
            c.chk("T17: handoff ACKED after target task PASSED",
                  handoffs[0]["status"] == "ACKED", handoffs[0]["status"])
        # the worker's agent_message_sent event was captured + replayed
        evs = p.events()
        c.chk("T17: agent_message_sent replayed into project events",
              any(e["event_type"] == "agent_message_sent" for e in evs),
              [e["event_type"] for e in evs][:12])
        c.chk("T17: target task executed and PASSED",
              p.get_task("task_B")["status"] == "PASSED",
              p.get_task("task_B")["status"])
        stats = result.get("handoffs", {})
        c.chk("T17: handoff consumed by harness", stats.get("acked", 0) >= 1,
              stats)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T18: Handoff-activated independent tasks run in parallel
# ------------------------------------------------------------------------- #
@section
def test_t18_message_parallel(c: Checks):
    d = fresh_dir()
    try:
        graph = {"tasks": [
            {"task_id": "task_A", "task_type": "knowledge_search"},
            {"task_id": "task_B", "task_type": "requirement_analysis",
             "dependencies": ["task_A"]},
            {"task_id": "task_C", "task_type": "risk_analysis",
             "dependencies": ["task_A"]},
        ]}
        scripts = {
            "task_A": [
                ("knowledge_search", {"query": "百万医疗险 重疾险 区别"}),
                ("send_agent_message", {
                    "to_agent": "insurance_analyst",
                    "message_type": "TASK_HANDOFF",
                    "task_id": "task_B",
                    "content": {"request": "请分析需求"}}),
                ("send_agent_message", {
                    "to_agent": "insurance_analyst",
                    "message_type": "TASK_HANDOFF",
                    "task_id": "task_C",
                    "content": {"request": "请分析风险"}}),
                "Handoffs sent.",
            ],
            "task_B": [
                ("record_requirement_analysis", {"requirements": [
                    {"requirement_id": "R1", "requirement_type": "medical",
                     "summary": "医疗费用保障", "priority": "P1_HIGH"}]}),
                "Requirements recorded.",
            ],
            "task_C": [
                ("record_risk_assessment", RISK_ARGS),
                "Risks recorded.",
            ],
        }
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        provider = TaskScriptProvider(scripts, probe=probe)
        h, p = make_project(d, graph, agent_executor=provider,
                            max_concurrency=2)
        result = h.run(p)
        c.chk("T18: both handoff-activated tasks ran in parallel",
              probe.overlapped, probe.log)
        c.chk("T18: B PASSED", p.get_task("task_B")["status"] == "PASSED",
              p.get_task("task_B")["status"])
        c.chk("T18: C PASSED", p.get_task("task_C")["status"] == "PASSED",
              p.get_task("task_C")["status"])
        msg_path = os.path.join(d, p.project_id, "messages.jsonl")
        msgs = []
        if os.path.exists(msg_path):
            with open(msg_path, encoding="utf-8") as f:
                msgs = [json.loads(l) for l in f if l.strip()]
        acked = [m for m in msgs if m["status"] == "ACKED"]
        c.chk("T18: both handoffs ACKED", len(acked) == 2,
              [(m["task_id"], m["status"]) for m in msgs])
        c.chk("T18: project completed", result["status"] == "completed",
              result["status"])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T19: Event integrity
# ------------------------------------------------------------------------- #
@section
def test_t19_event_integrity(c: Checks):
    d = fresh_dir()
    try:
        probe = OverlapProbe(need=2, watch={"task_B", "task_C"})
        ex = ScriptAgentExecutor(all_good_scripts(), probe=probe)
        h, p = make_project(d, diamond_graph(), agent_executor=ex,
                            max_concurrency=2)
        h.run(p)
        evs = p.events()
        for tid in ("task_A", "task_B", "task_C", "task_D"):
            sched = [i for i, e in enumerate(evs)
                     if e["event_type"] == "task_scheduled" and e.get("task_id") == tid]
            start = [i for i, e in enumerate(evs)
                     if e["event_type"] == "task_started" and e.get("task_id") == tid]
            done = [i for i, e in enumerate(evs)
                    if e["event_type"] == "task_completed" and e.get("task_id") == tid]
            fail = [i for i, e in enumerate(evs)
                    if e["event_type"] == "task_failed" and e.get("task_id") == tid]
            c.chk("T19: %s exactly one task_scheduled" % tid, len(sched) == 1, sched)
            c.chk("T19: %s exactly one task_started" % tid, len(start) == 1, start)
            c.chk("T19: %s exactly one terminal event" % tid,
                  len(done) + len(fail) == 1, (done, fail))
            c.chk("T19: %s order scheduled<started<terminal" % tid,
                  sched and start and (done or fail)
                  and sched[0] < start[0] < (done + fail)[0],
                  (sched, start, done, fail))
            # required fields (§18)
            if start:
                e = evs[start[0]]
                c.chk("T19: %s event carries ids+timestamp" % tid,
                      {"project_id", "task_id", "timestamp"} <= set(e)
                      and ("agent_id" in e or "worker_id" in e), list(e))
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T20: Deterministic final state across repeated runs
# ------------------------------------------------------------------------- #
@section
def test_t20_deterministic(c: Checks):
    d = fresh_dir()
    try:
        runs = []
        for i in range(3):
            sub = os.path.join(d, "run_%d" % i)
            os.makedirs(sub, exist_ok=True)
            ex = ScriptAgentExecutor(all_good_scripts())
            h, p = make_project(sub, diamond_graph(), agent_executor=ex,
                                max_concurrency=2)
            r = h.run(p)
            final = load_state(sub, p) or {}
            runs.append({
                "status": r["status"],
                "tasks": {t["task_id"]: t["status"] for t in p.tasks},
                "art_types": sorted((final.get("artifacts") or {}).keys()),
                "art_ids": {t: rec["artifact_id"] for t, rec in
                            (final.get("artifact_registry") or {}).items()},
                "evals": len(final.get("evaluations") or []),
            })
        first = runs[0]
        c.chk("T20: same project status across runs",
              all(r["status"] == first["status"] for r in runs),
              [r["status"] for r in runs])
        c.chk("T20: same task terminal states",
              all(r["tasks"] == first["tasks"] for r in runs),
              [r["tasks"] for r in runs])
        c.chk("T20: same artifact types",
              all(r["art_types"] == first["art_types"] for r in runs))
        c.chk("T20: same artifact registry ids (deterministic commit order)",
              all(r["art_ids"] == first["art_ids"] for r in runs),
              [r["art_ids"] for r in runs])
        c.chk("T20: same eval count",
              all(r["evals"] == first["evals"] for r in runs),
              [r["evals"] for r in runs])
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# T21: Phase 6 sequential compatibility (max_concurrency=1)
# ------------------------------------------------------------------------- #
PROFILE_ARGS = {
    "family_profile": {"age": {"value": 35}, "marital_status": {"value": "已婚"}},
    "financial_profile": {"annual_income": {"value": "30万"}},
    "existing_protection": {"existing_insurance": {"value": "无"}},
    "notes_for_unknown": ["health_status"],
}
REQ_ARGS = {"requirements": [
    {"requirement_id": "REQ-MED", "requirement_type": "medical",
     "summary": "大额住院医疗", "priority": "P1_HIGH"}]}


@section
def test_t21_phase6_compat(c: Checks):
    d = fresh_dir()
    try:
        # the REAL Phase 6 agent path (SpecialistAgentExecutor + provider),
        # sequential because max_concurrency=1
        graph = {"tasks": [
            {"task_id": "task_A", "task_type": "client_profile"},
            {"task_id": "task_B", "task_type": "requirement_analysis",
             "dependencies": ["task_A"]},
            {"task_id": "task_C", "task_type": "risk_analysis",
             "dependencies": ["task_B"]},
        ]}
        scripts = {
            "task_A": [("record_client_profile", PROFILE_ARGS), "done"],
            "task_B": [("record_requirement_analysis", REQ_ARGS), "done"],
            "task_C": [("record_risk_assessment", RISK_ARGS), "done"],
        }
        provider = TaskScriptProvider(scripts)
        h, p = make_project(d, graph, agent_executor=provider,
                            max_concurrency=1)
        result = h.run(p)
        c.chk("T21: max_concurrency=1 keeps Phase 6 sequential behavior",
              result["status"] == "completed", result["status"])
        c.chk("T21: all tasks PASSED",
              all(t["status"] == "PASSED" for t in p.tasks),
              {t["task_id"]: t["status"] for t in p.tasks})
        evs = [e["event_type"] for e in p.events()]
        c.chk("T21: sequential path emits no parallel scheduler events",
              "task_scheduled" not in evs and "task_recovered" not in evs, evs)
        c.chk("T21: sequential lifecycle events intact",
              all(t in evs for t in ("task_started", "task_completed",
                                     "agent_started", "agent_completed")), evs)
    finally:
        cleanup(d)


# ------------------------------------------------------------------------- #
# Instrumentation audit: the overlap probe cannot false-pass (§6/§25)
# ------------------------------------------------------------------------- #
@section
def test_probe_teeth(c: Checks):
    """Prove the probe REJECTS sequential interleaving: a fake-parallel
    scheduler (A start→A end→B start→B end) must yield overlapped=False,
    so T3/T4/T18/T22 can only pass on real simultaneous execution."""
    # (a) sequential interleaving — the §6 antipattern — must NOT overlap
    seq_probe = OverlapProbe(need=2, timeout=0.2)
    for key in ("task_B", "task_C"):
        seq_probe.enter(key)
        seq_probe.wait(key)
        seq_probe.exit(key)
    c.chk("PROBE: sequential interleaving rejected (no overlap)",
          not seq_probe.overlapped, seq_probe.log)

    # (b) genuine overlap via threads must be detected
    par_probe = OverlapProbe(need=2, timeout=5.0)
    par_probe.enter("task_B")
    t = threading.Thread(target=lambda: (par_probe.enter("task_C"),
                                         par_probe.exit("task_C")))
    t.start()
    par_probe.wait("task_B")           # returns only once C entered
    c.chk("PROBE: simultaneous execution detected",
          par_probe.overlapped, par_probe.log)
    par_probe.exit("task_B")
    t.join()
    c.chk("PROBE: max_active counted correctly", par_probe.max_active == 2,
          par_probe.max_active)


def main():
    return run_sections(SECTIONS, "webui_test_parallel_log.txt",
                        "RUNTIME PARALLEL SCHEDULER")


if __name__ == "__main__":
    sys.exit(main())
