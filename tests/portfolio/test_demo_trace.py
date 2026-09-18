"""Phase 12 — Portfolio demo + trace acceptance: the 6-act demo runs real
executions in every act, its trace comes from the durable event log, and
the output stays status-only."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _portfolio_common import Checks, run_sections, run_cmd  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def test_portfolio_demo_full(c: Checks):
    rc, out, err = run_cmd(["-m", "demos.demo_portfolio"], timeout=1200)
    c.chk("portfolio demo: exit 0", rc == 0, err[-200:])
    for act in ("ACT 1", "ACT 2", "ACT 3", "ACT 4", "ACT 5", "ACT 6"):
        c.chk("portfolio demo: %s present" % act, act in out)
    c.chk("portfolio demo: trace is T+ normalized from the event log",
          "T+" in out)
    c.chk("portfolio demo: replan act PASS", "B006: PASS" in out)
    c.chk("portfolio demo: HOTL act PASS", "B010: PASS" in out)
    c.chk("portfolio demo: HITL act PASS", "B008: PASS" in out)
    c.chk("portfolio demo: SE domain swap shown", "FINAL      COMPLETED" in out
          and "domain adapter" in out)
    c.chk("portfolio demo: lineage verified", "Lineage: verified" in out)
    c.chk("portfolio demo: no CoT/prompt leakage",
          "chain of thought" not in out.lower()
          and "system prompt" not in out.lower())


@section
def test_trace_summary_from_durable_state(c: Checks):
    """run_summary() must derive every number from durable state: run it on
    a real project, then tamper the state and watch the numbers change."""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "tests", "runtime"))
    from evals.benchmark import runner as bench
    import tempfile, shutil
    d = tempfile.mkdtemp(prefix="tr_", dir=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "tmp"))
    try:
        case = bench.load_cases({"B001"})[0]
        h, provider = bench.build_harness(d, case)
        graph = case["input"]["graph"]
        if isinstance(graph, list):
            graph = {"tasks": graph}
        p = h.create_project("tr", task_graph=graph)
        from runtime import orchestrator as orch
        from runtime.state import store as ss
        state = orch.seed_case(bench.WF, p.case_id, {})
        ss.save(state, os.path.join(d, p.project_id, "case"))
        h.run(p)
        s1 = bench.run_summary(h, p)
        c.chk("trace: summary reflects the real run (9-12 tasks line)",
              "Tasks:" in s1 and "Evaluations:" in s1)
        # tamper durable state -> summary must change (proves derivation)
        p.tasks[0]["status"] = "NEEDS_REVIEW"
        p._save()
        s2 = bench.run_summary(h, p)
        c.chk("trace: summary follows durable state (tamper detected)",
              s1 != s2)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_all_demos_leak_free(c: Checks):
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    tmp = os.path.join(repo, "tmp")
    for demo in ("demo_basic", "demo_insurance", "demo_generalization",
                 "demo_portfolio"):
        before = set(os.listdir(tmp))
        rc, _, _ = run_cmd(["-m", "demos.%s" % demo], timeout=1200)
        after = set(os.listdir(tmp))
        new = [d for d in after - before
               if d.startswith(("demo_", "bench_")) and
               os.path.isdir(os.path.join(tmp, d))]
        c.chk("leak-free: %s leaves no temp dirs" % demo,
              rc == 0 and not new, new)


def main():
    return run_sections(SECTIONS, "webui_test_demo_trace_log.txt",
                        "PORTFOLIO DEMO & TRACE")


if __name__ == "__main__":
    sys.exit(main())
