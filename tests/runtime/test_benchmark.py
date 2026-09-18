"""Phase 11 — Benchmark suite tests (T1–T3, T9, T15, T20, T25).

Drives evals/benchmark end-to-end: schema validity, runner execution, all
11 cases PASS, parallel consistency (1 vs 2), determinism (3 repeats of the
golden case), and the machine-readable metrics with hard gates = 0.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

sys.path.insert(0, os.path.join(REPO, "tests", "runtime"))
from evals.benchmark import runner as bench  # noqa: E402
from evals.benchmark import metrics as bm  # noqa: E402

SECTIONS = []
BENCH_DIR = os.path.join(REPO, "evals", "benchmark")


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="bt_", dir=os.path.join(REPO, "tmp"))


@section
def test_t1_schema(c: Checks):
    import jsonschema
    schema = json.load(open(os.path.join(BENCH_DIR, "schema.json"),
                           encoding="utf-8"))
    cases = bench.load_cases()
    c.chk("T1: benchmark cases exist", len(cases) == 11, len(cases))
    for case in cases:
        try:
            jsonschema.validate(case, schema)
            c.chk("T1: %s matches schema" % case["case_id"], True)
        except jsonschema.ValidationError as e:
            c.chk("T1: %s matches schema" % case["case_id"], False,
                  e.message[:120])
    ids = [x["case_id"] for x in cases]
    c.chk("T1: case ids unique B001..B011",
          ids == ["B%03d" % i for i in range(1, 12)], ids)


@section
def test_t2_t25_runner_all_cases(c: Checks):
    d = fresh_dir()
    try:
        results = []
        for case in bench.load_cases():
            out = bench.run_case(case, root=os.path.join(d, case["case_id"]))
            results.append(out)
            c.chk("T25: %s %s PASS" % (out["case_id"], out["name"]),
                  out["passed"], out["failures"])
        report = bm.compile_report(results)
        for gate in bm.HARD_GATES:
            c.chk("T25: hard gate %s == 0" % gate, report["metrics"][gate] == 0)
        c.chk("T25: benchmark_pass_rate == 1.0",
              report["metrics"]["benchmark_pass_rate"] == 1.0)
        c.chk("T25: all_passed verdict", report["all_passed"])
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_t9_parallel_consistency(c: Checks):
    case = bench.load_cases({"B007"})[0]
    ok, detail = bench.parallel_consistency(case)
    c.chk("T9: max_concurrency 1 vs 2 semantically equivalent", ok)
    if not ok:
        c.chk("T9: tasks equal",
              detail["mc1"]["tasks"] == detail["mc2"]["tasks"])
        c.chk("T9: artifacts equal",
              detail["mc1"]["artifacts"] == detail["mc2"]["artifacts"])
    case11 = bench.load_cases({"B011"})[0]
    ok2, _ = bench.parallel_consistency(case11)
    c.chk("T9: four-agent case 1 vs 2 equivalent", ok2)


@section
def test_t20_determinism(c: Checks):
    """Same input/graph/state/config 3 times → same semantic fingerprint.
    Timestamps, uuids and thread order are runtime metadata, excluded."""
    case = bench.load_cases({"B011"})[0]
    d = fresh_dir()
    try:
        fps = []
        for i in range(3):
            sub = os.path.join(d, "run%d" % i)
            os.makedirs(sub, exist_ok=True)
            h, provider = bench.build_harness(sub, case)
            graph = case["input"]["graph"]
            if isinstance(graph, list):
                graph = {"tasks": graph}
            p = h.create_project("det", task_graph=graph)
            from runtime import orchestrator as orch
            from runtime.state import store as ss
            state = orch.seed_case(bench.WF, p.case_id, {})
            ss.save(state, os.path.join(sub, p.project_id, "case"))
            h.run(p)
            fps.append(bench.semantic_fingerprint(h, p))
        first = fps[0]
        c.chk("T20: task states identical across 3 runs",
              all(f["tasks"] == first["tasks"] for f in fps))
        c.chk("T20: artifact ids identical (deterministic commit order)",
              all(f["artifact_ids"] == first["artifact_ids"] for f in fps))
        c.chk("T20: eval verdicts identical",
              all(f["eval_verdicts"] == first["eval_verdicts"] for f in fps))
        c.chk("T20: revision identical",
              all(f["revision"] == first["revision"] for f in fps))
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
def test_results_artifact(c: Checks):
    """python -m evals.benchmark.runner writes results + metrics to disk."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-m", "evals.benchmark.runner"],
        capture_output=True, text=True, cwd=REPO, timeout=600)
    c.chk("runner exit code 0", r.returncode == 0,
          r.stdout[-300:] if r.returncode else "")
    path = os.path.join(BENCH_DIR, "results", "results.json")
    c.chk("results.json written", os.path.exists(path))
    if os.path.exists(path):
        doc = json.load(open(path, encoding="utf-8"))
        c.chk("results carry metrics", "metrics" in doc
              and doc["metrics"]["cases_total"] == 11)
        c.chk("all cases passed in persisted results",
              all(x["passed"] for x in doc["results"]))


def main():
    return run_sections(SECTIONS, "webui_test_benchmark_log.txt",
                        "RUNTIME BENCHMARK SUITE")


if __name__ == "__main__":
    sys.exit(main())
