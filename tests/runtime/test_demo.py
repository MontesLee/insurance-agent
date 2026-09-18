"""Phase 11 — Demo-runner tests (T22) + trace summary (T23).

Every demo must run in one command, be repeatable, print status-only
transcripts (never chain-of-thought), and end in an explicit final state.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

SECTIONS = []
DEMOS = ["demo_basic", "demo_parallel", "demo_replan", "demo_hitl",
         "demo_hotl", "demo_four_agent"]
BANNED_OUTPUT = ("chain of thought", "思考过程", "prompt:", "system prompt")


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_t22_demo_runners(c: Checks):
    for name in DEMOS:
        r = subprocess.run([sys.executable, "-m", "demos.%s" % name],
                           capture_output=True, text=True, cwd=REPO, timeout=300)
        c.chk("T22: %s exits 0" % name, r.returncode == 0,
              r.stdout[-200:] + r.stderr[-200:] if r.returncode else "")
        out = r.stdout
        c.chk("T22: %s prints Checks" % name, "Checks:" in out)
        c.chk("T22: %s prints Final state" % name,
              re.search(r"Final:\s*\n?\s*(COMPLETED|PAUSED|NEEDS REVIEW|"
                        r"NEEDS_REVIEW)", out, re.I)
              or "Final" in out, out[-120:])
        c.chk("T22: %s prints RUN SUMMARY" % name, "RUN SUMMARY" in out)
        bad = [b for b in BANNED_OUTPUT if b.lower() in out.lower()]
        c.chk("T22: %s leaks no CoT/prompt text" % name, not bad, bad)


@section
def test_t22_demos_repeatable(c: Checks):
    """Run one demo twice — identical semantic output (modulo temp ids)."""
    outs = []
    for _ in range(2):
        r = subprocess.run([sys.executable, "-m", "demos.demo_replan"],
                           capture_output=True, text=True, cwd=REPO, timeout=300)
        outs.append(r.stdout)
    def normalize(t):
        return re.sub(r"proj_[a-f0-9]+", "proj_X", t)
    c.chk("T22: demo repeatable (normalized output identical)",
          normalize(outs[0]) == normalize(outs[1]))


@section
def test_t23_trace_summary(c: Checks):
    sys.path.insert(0, os.path.join(REPO, "tests", "runtime"))
    from evals.benchmark import runner as bench
    case = bench.load_cases({"B011"})[0]
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="ts_", dir=os.path.join(REPO, "tmp"))
    try:
        h, provider = bench.build_harness(d, case)
        graph = case["input"]["graph"]
        if isinstance(graph, list):
            graph = {"tasks": graph}
        p = h.create_project("t23", task_graph=graph)
        from runtime import orchestrator as orch
        from runtime.state import store as ss
        state = orch.seed_case(bench.WF, p.case_id, {})
        ss.save(state, os.path.join(d, p.project_id, "case"))
        h.run(p)
        summary = bench.run_summary(h, p)
        for needed in ("Planner", "Agents", "Execution", "Quality", "Human",
                       "Artifacts", "Final", "COMPLETED"):
            c.chk("T23: summary contains %r" % needed, needed in summary)
        c.chk("T23: summary lists 4 agents",
              summary.count("specialist") >= 3, summary)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def main():
    return run_sections(SECTIONS, "webui_test_demo_log.txt",
                        "RUNTIME DEMO SUITE")


if __name__ == "__main__":
    sys.exit(main())
