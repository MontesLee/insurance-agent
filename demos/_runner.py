"""Shared demo plumbing: run a benchmark case by id, print a compact,
status-only transcript and the RUN SUMMARY."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
for p in (REPO, os.path.join(REPO, "tests", "runtime")):
    if p not in sys.path:
        sys.path.insert(0, p)

from evals.benchmark import runner as bench  # noqa: E402


def run_demo(case_id: str) -> int:
    case = bench.load_cases({case_id})[0]
    root = tempfile.mkdtemp(prefix="demo_", dir=os.path.join(REPO, "tmp"))
    try:
        h, provider = bench.build_harness(root, case)
        graph = case["input"]["graph"]
        if isinstance(graph, list):
            graph = {"tasks": graph}
        p = h.create_project(case_id, task_graph=graph)
        from runtime import orchestrator as orch
        from runtime.state import store as ss
        state = orch.seed_case(bench.WF, p.case_id, {})
        ss.save(state, os.path.join(root, p.project_id, "case"))

        # replay durable events as the run progresses: run in one shot, then
        # print the event transcript from events.jsonl (status-only fields)
        result = h.run(p)
        for step in case["input"].get("human_steps", []):
            bench._apply_human_step(h, p, step)
            result = h.run(p)

        final = ss.load(os.path.join(root, p.project_id, "case"), p.case_id) or {}
        out = bench.run_case.__doc__ and {}  # noqa — keep linters calm
        checks = bench.verify(case, h, p, result, provider)
        print("=== %s (%s) ===" % (case_id, case["name"]))
        for e in p.events():
            et = e["event_type"]
            line = None
            if et in ("task_started", "task_completed"):
                line = "%-18s %s" % (et, e.get("task_id", ""))
            elif et == "task_failed":
                line = "%-18s %s (%s)" % (et, e.get("task_id", ""),
                                          str(e.get("reason", ""))[:40])
            elif et in ("agent_started", "agent_completed"):
                line = "%-18s %s" % (et, e.get("agent_id", ""))
            elif et in ("replan_triggered", "replan_completed", "replan_failed"):
                line = "%-18s" % et
            elif et.startswith("approval_") or et in ("runtime_paused",
                                                      "runtime_resumed"):
                line = "%-18s" % et
            elif et in ("intervention_notified", "monitor_signal_detected"):
                line = "%-18s" % et
            if line:
                print(line)
        print()
        failed = [k for k, (ok, _) in checks.items() if not ok]
        print("Checks: %d/%d PASS%s" % (
            sum(1 for ok, _ in checks.values() if ok), len(checks),
            ("  (failed: %s)" % ", ".join(failed)) if failed else ""))
        print("Artifacts: %d" % len(final.get("artifacts") or {}))
        print("Final: %s" % str(result.get("status", "")).upper())
        print()
        print(bench.run_summary(h, p))
        return 0 if not failed else 1
    finally:
        shutil.rmtree(root, ignore_errors=True)
