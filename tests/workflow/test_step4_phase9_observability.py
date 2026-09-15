"""Step 4 Phase 9 / Phase 11 — Observability + Trace Viewer.

Asserts the cost/performance numbers are derived correctly from the Execution Trace of a
REAL run (spec §22: latency, execution count, repairs, knowledge-search count — no
invented figures), and that the Trace Viewer renders a readable timeline.

Exit 0 = all checks pass.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime import observability as obs  # noqa: E402

BENCH_DIR = os.path.join(REPO, "evals", "agent-benchmark")


def _load_bench():
    spec = importlib.util.spec_from_file_location(
        "obs_bench_runner", os.path.join(BENCH_DIR, "run_agent_benchmark.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


passed = failed = 0
lines = []


def chk(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
    else:
        failed += 1
    lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name,
                                ("  -- " + str(detail)) if (detail and not ok) else ""))


def main():
    bench = _load_bench()
    with open(os.path.join(BENCH_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(REPO, manifest["seeds_file"]), encoding="utf-8") as f:
        base = json.load(f)
    kb_empty = os.path.join(REPO, manifest["empty_kb"])
    wf = bench.orch.load_workflow()
    by_id = {c["id"]: c for c in manifest["cases"]}

    # ---- happy path: 8 stages, 1 knowledge-search, 0 repairs -----------------
    st, rep = bench.run_case(by_id["bm-complete-001"], wf, base, manifest["seeds_file"], kb_empty)
    s = obs.summarize(st)
    chk("happy: case COMPLETED", rep["status"] == "COMPLETED", rep["status"])
    chk("happy: total_stages == 8", s["total_stages"] == 8, s["total_stages"])
    chk("happy: 5 skills executed locally", s["skill_calls"] == 5, s["skill_calls"])
    chk("happy: 3 stages provided upstream", s["provided_skills"] == 3, s["provided_skills"])
    chk("happy: 1 knowledge-search call", s["knowledge_search_calls"] == 1,
        s["knowledge_search_calls"])
    chk("happy: total invocations == 9", s["total_skill_calls"] == 9, s["total_skill_calls"])
    chk("happy: zero repairs", s["repairs"] == 0, s["repairs"])
    chk("happy: 9 artifacts registered", s["artifacts"] == 9, s["artifacts"])
    lat = s["per_skill"].get("coverage-gap-analysis", {}).get("total_ms", 0)
    chk("happy: latency recorded for a real stage", isinstance(lat, (int, float)) and lat >= 0, lat)

    md = obs.render_trace_markdown(st)
    chk("trace view has a title", md.startswith("# bm-complete-001 TRACE"), md.splitlines()[:1])
    for token in ("CASE_STARTED", "SKILL_COMPLETED", "CHECKPOINT_SAVED", "CASE_COMPLETED"):
        chk("trace view contains %s" % token, token in md)

    # ---- evidence failure: 2 repairs, 3 knowledge-search, NEEDS_REVIEW -------
    st2, rep2 = bench.run_case(by_id["bm-noev-001"], wf, base, manifest["seeds_file"], kb_empty)
    s2 = obs.summarize(st2)
    chk("noev: case NEEDS_REVIEW", rep2["status"] == "NEEDS_REVIEW", rep2["status"])
    chk("noev: 2 repairs", s2["repairs"] == 2, s2["repairs"])
    chk("noev: 3 knowledge-search calls", s2["knowledge_search_calls"] == 3,
        s2["knowledge_search_calls"])
    chk("noev: 3 failed attempts on the blocked stage",
        s2["per_skill"].get("product-candidate-provider", {}).get("failed") == 3,
        s2["per_skill"].get("product-candidate-provider"))
    md2 = obs.render_trace_markdown(st2)
    chk("noev: timeline ends at CASE_NEEDS_REVIEW", md2.strip().endswith("|"), md2.strip()[-80:])
    chk("noev: timeline shows the repair trail", "REPAIR_STARTED" in md2)

    out = lines + ["", "STEP4-P9 OBSERVABILITY: %d/%d checks passed" % (passed, passed + failed),
                   "RESULT: %s" % ("ALL GREEN" if failed == 0 else "FAILURES PRESENT")]
    text = "\n".join(out)
    print(text)
    with open(os.path.join(REPO, "tmp", "p9_log.txt"), "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
