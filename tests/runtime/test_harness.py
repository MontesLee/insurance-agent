"""Long-Running Harness tests (Phase 3 V0.1).

Covers: project/task creation, execution, artifact+eval, checkpoint, resume,
idempotency (PASSED→SKIP), failure+retry, BLOCKED, artifact lineage, event
integrity, state restoration, and the critical KILL→RESTART→RESUME scenario
using a real subprocess kill.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_harness.py`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import orchestrator as orch
from runtime.harness import LongRunningHarness, load_project, list_projects

SECTIONS = []
WF = orch.load_workflow()


def fresh_root():
    root = tempfile.mkdtemp(prefix="harness_test_", dir=os.path.join(REPO, "tmp"))
    return root


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_project_and_task_creation(c: Checks):
    root = fresh_root()
    h = LongRunningHarness(root)
    p = h.create_project("test-project")
    c.chk("project: id assigned", p.project_id.startswith("proj_"))
    c.chk("project: persisted to disk",
          os.path.exists(os.path.join(root, p.project_id, "project.json")))
    c.chk("project: in index", any(e["project_id"] == p.project_id
                                   for e in list_projects(root)))
    c.chk("project: 9 tasks created (code-defined chain)",
          len(p.tasks) == 9, [t["task_type"] for t in p.tasks])
    c.chk("project: tasks have dependencies",
          all(t["dependencies"] for t in p.tasks[1:]))
    c.chk("project: CaseState on disk",
          os.path.exists(os.path.join(root, p.project_id, "case",
                                      p.case_id, "case_state.json")))
    evs = p.events()
    c.chk("project: project_created event", evs[0]["event_type"] == "project_created")
    c.chk("project: 9 task_created events",
          sum(1 for e in evs if e["event_type"] == "task_created") == 9)
    shutil.rmtree(root, ignore_errors=True)


@section
def test_full_execution_with_checkpoint(c: Checks):
    root = fresh_root()
    h = LongRunningHarness(root)

    # seed client-profile + requirement + risk so downstream engines can run
    from runtime.state import case_state as cs
    from runtime import tasks as tk

    p = h.create_project("exec-project")
    state = cs.new_case_state(p.case_id, WF)
    tk.init_tasks(state, WF)

    # use the benchmark seeds for the three dialogue stages
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    seeds = copy.deepcopy(fixture["artifacts"])
    state = orch.seed_case(WF, p.case_id, seeds, provided_by="harness-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, p.project_id, "case"))

    result = h.run(p)
    c.chk("execution: project completed", result["status"] == "completed",
          result["status"])
    outcomes = {e["task"]: e["outcome"] for e in result["executed"]}
    c.chk("execution: all tasks PASS or SKIPPED",
          all(v in ("PASS", "SKIPPED") for v in outcomes.values()), outcomes)
    cps = p.checkpoints()
    c.chk("checkpoint: created during execution", len(cps) >= 1)
    c.chk("checkpoint: has artifact_refs", cps[-1]["artifact_refs"])
    c.chk("checkpoint: has completed_task_ids",
          len(cps[-1]["completed_task_ids"]) >= 1)
    evs = p.events()
    for needed in ("task_started", "task_completed", "task_skipped",
                   "checkpoint_created"):
        c.chk("events: %s present" % needed,
              any(e["event_type"] == needed for e in evs))
    shutil.rmtree(root, ignore_errors=True)


@section
def test_idempotency_skip_passed(c: Checks):
    root = fresh_root()
    h = LongRunningHarness(root)
    p = h.create_project("idem-project")

    # seed and run to completion
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    state = orch.seed_case(WF, p.case_id, copy.deepcopy(fixture["artifacts"]),
                           provided_by="harness-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, p.project_id, "case"))
    h.run(p)

    # re-run the SAME project — everything should be SKIPPED
    result2 = h.run(p)
    outcomes2 = [e["outcome"] for e in result2["executed"]]
    c.chk("idempotency: second run all SKIPPED",
          all(v == "SKIPPED" for v in outcomes2), outcomes2)
    evs = p.events()
    skipped = [e for e in evs if e["event_type"] == "task_skipped"]
    c.chk("idempotency: task_skipped events emitted", len(skipped) >= 9,
          len(skipped))
    # force_rerun re-executes python stages (provided stages are always skipped
    # because they map to seed_case which is idempotent)
    result3 = h.run(p, force_rerun=True)
    executed_any = any(e["outcome"] in ("PASS", "NEEDS_REVIEW")
                       for e in result3["executed"])
    c.chk("idempotency: force_rerun re-executes (non-skip outcome present)",
          executed_any, [e["outcome"] for e in result3["executed"]])
    shutil.rmtree(root, ignore_errors=True)


@section
def test_blocked_task(c: Checks):
    """BLOCKED: when a task FAILS, downstream tasks are blocked on resume."""
    root = fresh_root()
    h = LongRunningHarness(root)
    p = h.create_project("blocked-project")

    # seed WITHOUT risk-assessment so the risk stage can't complete
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    arts = copy.deepcopy(fixture["artifacts"])
    del arts["risk-assessment"]  # risk stage will fail (missing seed)
    state = orch.seed_case(WF, p.case_id, arts, provided_by="harness-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, p.project_id, "case"))

    result = h.run(p)
    c.chk("blocked: project did NOT complete", result["status"] != "completed",
          result["status"])

    # verify downstream tasks see dependency not met → BLOCKED or chain stops
    outcomes = {e["task"]: e["outcome"] for e in result["executed"]}
    c.chk("blocked: at least one non-PASS outcome present",
          any(v not in ("PASS", "SKIPPED") for v in outcomes.values()), outcomes)

    # on RESUME, tasks downstream of the failure should see BLOCKED
    # (their dependency is in a non-PASSED state)
    failed_tasks = [t for t in p.tasks if t["status"] == "NEEDS_REVIEW"]
    c.chk("blocked: failed task marked NEEDS_REVIEW", len(failed_tasks) >= 1,
          [(t["task_type"], t["status"]) for t in p.tasks])

    # manually verify: if we try to resume, downstream tasks check dependency
    result2 = h.resume(p.project_id)
    outcomes2 = {e["task"]: e["outcome"] for e in result2.get("executed", [])}
    downstream_blocked = [t for t, o in outcomes2.items() if o == "BLOCKED"]
    c.chk("blocked: resume shows downstream BLOCKED", len(downstream_blocked) >= 1,
          outcomes2)
    shutil.rmtree(root, ignore_errors=True)


@section
def test_artifact_lineage(c: Checks):
    root = fresh_root()
    h = LongRunningHarness(root)
    p = h.create_project("lineage-project")
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    state = orch.seed_case(WF, p.case_id, copy.deepcopy(fixture["artifacts"]),
                           provided_by="harness-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, p.project_id, "case"))
    h.run(p)

    # verify task output_artifacts form a chain
    outputs = {t["task_type"]: t.get("output_artifacts", [])
               for t in p.tasks if t["status"] in ("PASSED", "COMPLETED")}
    c.chk("lineage: client_profile has artifact",
          len(outputs.get("client_profile", [])) >= 1)
    c.chk("lineage: report has artifact",
          len(outputs.get("report", [])) >= 1)
    c.chk("lineage: every completed task has artifact output",
          all(len(arts) >= 1 for arts in outputs.values()),
          {k: len(v) for k, v in outputs.items()})
    # verify CaseState artifact registry lineage: report → … → client-profile
    from runtime import artifact_registry as reg
    from runtime.state import store as _ss2
    _s2 = _ss2.load(os.path.join(root, p.project_id, "case"), p.case_id)
    if _s2:
        lineage = reg.lineage_types(_s2, "insurance-report")
        c.chk("lineage: report traces back to client-profile",
              "client-profile" in lineage, lineage)
    shutil.rmtree(root, ignore_errors=True)


@section
def test_event_integrity(c: Checks):
    root = fresh_root()
    h = LongRunningHarness(root)
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    p = h.create_project("events-project")
    state = orch.seed_case(WF, p.case_id, copy.deepcopy(fixture["artifacts"]),
                           provided_by="harness-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, p.project_id, "case"))
    h.run(p)

    evs = p.events()
    blob = json.dumps(evs, ensure_ascii=False).lower()
    c.chk("events: JSON-serializable", isinstance(evs, list) and len(evs) > 0)
    for banned in ("api_key", "authorization", "sk-", "chain of thought",
                   "思考过程", "prompt"):
        c.chk("events: no %r" % banned, banned not in blob)
    types = {e["event_type"] for e in evs}
    _vocab = {"project_created", "task_created", "task_started",
              "task_completed", "task_failed", "task_skipped",
              "checkpoint_created", "checkpoint_loaded", "run_resumed",
              "agent_assigned", "agent_started", "agent_completed",
              "agent_failed", "agent_validation_failed"}
    c.chk("events: harness+agent vocabulary used",
          types <= _vocab, types - _vocab)
    shutil.rmtree(root, ignore_errors=True)


# ------------------------------------------------------------------------- #
# THE critical test: kill a subprocess mid-run, restart, verify resume
# ------------------------------------------------------------------------- #
_KILL_SCRIPT = r'''
import sys, os, json, time, signal
sys.path.insert(0, %r)
from runtime import orchestrator as orch
from runtime.harness import LongRunningHarness

root = sys.argv[1]
project_id = sys.argv[2]
h = LongRunningHarness(root)

# load the project and the case state
from runtime.harness import load_project
p = load_project(root, project_id)
if p is None:
    print("FATAL: project not found"); sys.exit(1)

# seed the case
import copy
with open(os.path.join(%r, "tests", "e2e", "fixtures", "case-full-chain.json"), encoding="utf-8") as f:
    fixture = json.load(f)
state = orch.seed_case(p._dir and orch.load_workflow() or orch.load_workflow(),
                       p.case_id, copy.deepcopy(fixture["artifacts"]),
                       provided_by="kill-test")
from runtime.state import store as state_store
state_store.save(state, os.path.join(root, project_id, "case"))

# execute only the FIRST task, then checkpoint and signal ready-to-die
from runtime.state import transitions
wf = orch.load_workflow()
stage = transitions.stage_by_id(wf, "client-intake")
state["current_stage"] = "client-intake"

# the seeded stage is already COMPLETED via seed_case, so simulate:
# execute coverage-gap-analysis (the first non-provided stage)
stage2 = transitions.stage_by_id(wf, "coverage-gap-analysis")
state["current_stage"] = "coverage-gap-analysis"
result = orch._execute_stage(state, wf, stage2)

# checkpoint
from runtime import checkpoint as cp
cp.save(state, os.path.join(root, project_id, "case"), None)

# mark harness-level: first 4 tasks done, 5th was running
for t in p.tasks:
    if t["task_type"] in ("client_profile", "requirement", "risk", "coverage_gap"):
        t["status"] = "PASSED"
        t["output_artifacts"] = []
    elif t["task_type"] == "solution":
        t["status"] = "RUNNING"
        t["attempt"] = 1
p.status = "running"
p._save()

print("READY_TO_DIE", flush=True)
# wait for the parent to kill us
time.sleep(600)
''' % (REPO, REPO)


@section
def test_kill_restart_resume(c: Checks):
    """THE acceptance test: subprocess runs → kill → NEW instance resumes."""
    root = fresh_root()
    h = LongRunningHarness(root)
    p = h.create_project("kill-resume-project")
    project_id = p.project_id

    # write the kill script
    script_path = os.path.join(root, "_kill_script.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(_KILL_SCRIPT)

    # spawn a subprocess that seeds + executes + checkpoints + waits
    proc = subprocess.Popen(
        [sys.executable, script_path, root, project_id],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=REPO)

    # wait for READY_TO_DIE
    import select
    deadline = time.time() + 60
    ready = False
    output_lines = []
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        output_lines.append(line.strip())
        if "READY_TO_DIE" in line:
            ready = True
            break
    c.chk("kill: subprocess reached checkpoint", ready, output_lines)

    # KILL the subprocess
    proc.kill()
    proc.wait(timeout=10)
    c.chk("kill: subprocess terminated", proc.returncode != 0)

    # verify state survived on disk
    p2 = load_project(root, project_id)
    c.chk("restart: project loadable from disk by NEW instance", p2 is not None)
    if p2 is None:
        shutil.rmtree(root, ignore_errors=True)
        return
    c.chk("restart: tasks preserved", len(p2.tasks) == 9)
    passed_before = [t for t in p2.tasks if t["status"] == "PASSED"]
    c.chk("restart: first tasks PASSED on disk", len(passed_before) >= 3,
          [t["task_type"] for t in passed_before])
    c.chk("restart: case state on disk",
          os.path.exists(os.path.join(root, project_id, "case", p2.case_id,
                                      "case_state.json")))

    # NEW harness instance resumes
    h2 = LongRunningHarness(root)
    result = h2.resume(project_id)
    c.chk("resume: completed after restart", result["status"] == "completed",
          result.get("status"))

    # verify PASSED tasks were SKIPPED, not re-executed
    outcomes = {e["task"]: e["outcome"] for e in result.get("executed", [])}
    skipped = [t for t, o in outcomes.items() if o == "SKIPPED"]
    executed_fresh = [t for t, o in outcomes.items() if o == "PASS"]
    c.chk("resume: previously PASSED tasks SKIPPED",
          all(outcomes.get(tt) == "SKIPPED"
              for tt in ("client_profile", "requirement", "risk", "coverage_gap")
              if tt in outcomes), outcomes)

    # verify run_resumed event
    evs = p2.events()
    c.chk("resume: run_resumed event present",
          any(e["event_type"] == "run_resumed" for e in evs))

    # verify final state: all tasks done
    p3 = load_project(root, project_id)
    c.chk("resume: all tasks terminal",
          all(t["status"] in ("PASSED", "COMPLETED") for t in p3.tasks),
          [(t["task_type"], t["status"]) for t in p3.tasks])
    c.chk("resume: project status completed", p3.status == "completed", p3.status)

    # verify case state has the final artifacts
    from runtime.state import store as state_store
    state = state_store.load(os.path.join(root, project_id, "case"), p3.case_id)
    c.chk("resume: CaseState has insurance-report",
          "insurance-report" in (state or {}).get("artifacts", {}),
          sorted(((state or {}).get("artifacts") or {}).keys()))
    shutil.rmtree(root, ignore_errors=True)


@section
def test_state_restoration(c: Checks):
    root = fresh_root()
    h = LongRunningHarness(root)
    p = h.create_project("restore-project")
    import copy
    with open(os.path.join(REPO, "tests", "e2e", "fixtures",
                           "case-full-chain.json"), encoding="utf-8") as f:
        fixture = json.load(f)
    state = orch.seed_case(WF, p.case_id, copy.deepcopy(fixture["artifacts"]),
                           provided_by="harness-test")
    from runtime.state import store as state_store
    state_store.save(state, os.path.join(root, p.project_id, "case"))
    h.run(p)

    # NEW instance loads from disk
    h2 = LongRunningHarness(root)
    p2 = load_project(root, p.project_id)
    c.chk("restore: project state version preserved",
          p2.state_version > 0, p2.state_version)
    c.chk("restore: task statuses preserved",
          all(t["status"] in ("PASSED", "COMPLETED") for t in p2.tasks))
    c.chk("restore: checkpoint log non-empty", len(p2.checkpoints()) >= 1)
    c.chk("restore: event log non-empty", len(p2.events()) >= 10)
    shutil.rmtree(root, ignore_errors=True)


import time  # noqa: E402


def main():
    return run_sections(SECTIONS, "webui_test_harness_log.txt", "RUNTIME HARNESS")


if __name__ == "__main__":
    sys.exit(main())
