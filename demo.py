#!/usr/bin/env python3
"""Insurance Agent — Demo Mode (Step 4 Phase 10 / Phase 11).

Runs a real client case through the WHOLE agent system and shows, live, what the agent
is doing — every skill, its verdict, every repair — then the final result plus the
observability summary and a Markdown trace.

    python demo.py                 # Demo A (happy path) + Demo B (insufficient evidence)
    python demo.py demo-a          # curated demo, ends with a report
    python demo.py demo-b          # deliberately broken: evidence missing -> repair -> NEEDS_REVIEW
    python demo.py --case bm-highrisk-001 --all   # run any benchmark case
    python demo.py --list          # list available cases

Exit 0 = the run finished (a NEEDS_REVIEW outcome is a CORRECT outcome and still exits 0).
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = HERE
sys.path.insert(0, REPO)

from runtime import orchestrator as orch  # noqa: E402
from runtime import trace as tr  # noqa: E402
from runtime import observability as obs  # noqa: E402

BENCH_DIR = os.path.join(REPO, "evals", "agent-benchmark")
BENCH_RUNNER = os.path.join(BENCH_DIR, "run_agent_benchmark.py")


def _load_bench():
    spec = importlib.util.spec_from_file_location("demo_bench_runner", BENCH_RUNNER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BENCH = _load_bench()

DEMOS = {
    "demo-a": ("bm-complete-006-single-medical",
               "完整案例（单一需求）：全链路 -> 真正落到一个具体产品 -> 推荐 + 报告（并标记 DEMO）"),
    "demo-b": ("bm-noev-001",
               "故障演示：知识库为空 -> Eval FAIL -> Repair -> 仍失败 -> NEEDS_REVIEW"),
    "demo-c": ("bm-complete-001",
               "多需求完整客户：策略层覆盖 5 个领域，但没有单一产品能覆盖全部 -> 诚实呈现，不硬推"),
}

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
if os.environ.get("NO_COLOR"):
    GREEN = RED = DIM = RESET = ""


def _print_progress(rec):
    """Live sink: called by trace.emit as the case runs."""
    ev = rec["event"]
    skill = rec.get("skill") or "-"
    if ev == "SKILL_COMPLETED":
        ms = rec.get("duration_ms")
        extra = " (%sms)" % ms if isinstance(ms, (int, float)) and ms else ""
        print("  %s[OK]%s %-26s %s PASS%s" % (GREEN, RESET, skill, rec.get("eval_status") or "", extra))
    elif ev == "TASK_FAILED":
        print("  %s[XX]%s %-26s %s %s" % (RED, RESET, skill, rec.get("eval_status") or "",
                                          str(rec.get("detail") or "")[:110]))
    elif ev == "REPAIR_STARTED":
        print("       %s+- repair: %s%s" % (DIM, str(rec.get("detail") or "")[:100], RESET))
    elif ev == "CHECKPOINT_SAVED":
        print("       %s+- checkpoint saved%s" % (DIM, RESET))
    elif ev == "CASE_WAITING":
        print("  %s[..]%s waiting for the client: %s" % (DIM, RESET, rec.get("detail")))
    elif ev in ("CASE_COMPLETED", "CASE_NEEDS_REVIEW"):
        print("  %s[==]%s %s" % (DIM, RESET, ev))


def _print_outcome(state):
    """Show what the case actually concluded: recommendation + product + safety marking."""
    arts = state.get("artifacts") or {}

    def _pay(art):
        if isinstance(art, dict) and isinstance(art.get("payload"), dict):
            return art["payload"]
        return art or {}

    rec = _pay(arts.get("product-recommendation"))
    lines = []
    if rec:
        lines.append("recommendation status: %s" % rec.get("status"))
        prim = rec.get("primary_recommendation") or {}
        prod = prim.get("product") or {}
        if prod:
            lines.append("primary product: %s %s (%s / catalog %s)"
                         % (prod.get("product_id"), prod.get("product_name"),
                            prod.get("product_version"), prod.get("catalog_version")))
        evs = rec.get("candidate_evaluations") or []
        if evs:
            lines.append("candidates evaluated: %d (primary=%d, not_recommended=%d, insufficient=%d)"
                         % (len(evs),
                            sum(1 for e in evs if e.get("recommendation_status") == "primary"),
                            sum(1 for e in evs if e.get("recommendation_status") == "not_recommended"),
                            sum(1 for e in evs if e.get("recommendation_status") == "insufficient_evidence")))
        if rec.get("evidence_refs"):
            lines.append("evidence refs: %s" % ", ".join(rec["evidence_refs"][:6]))

    rep = _pay(arts.get("insurance-report"))
    if rep:
        disc = (rep.get("structured_report") or {}).get("disclosure") or {}
        if disc.get("is_demo"):
            lines.append("SAFETY: DEMO products disclosed -> %s"
                         % ", ".join(disc.get("demo_products") or []))
        else:
            lines.append("SAFETY: no demo product named in the report")
        lines.append("SAFETY: catalog_checked=%s, unverified_products=%s"
                     % (disc.get("catalog_checked"), disc.get("unverified_products") or []))

    if lines:
        print()
        print("OUTCOME")
        for ln in lines:
            print("  " + ln)


def run_demo(name, case_id, wf, base, kb_empty, manifest):
    case = next((c for c in manifest["cases"] if c["id"] == case_id), None)
    if case is None:
        print("unknown case: %s" % case_id)
        return 1
    print("=" * 78)
    print("%s  —  %s" % (name, case.get("desc")))
    print("=" * 78)

    seeds = BENCH.apply_mutations(__import__("copy").deepcopy(base["artifacts"]),
                                 case.get("mutations", []))
    kb_dir = kb_empty if case.get("kb") == "empty" else None
    run_dir = os.path.join(REPO, "tmp", "demo", case_id)
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(run_dir, exist_ok=True)

    state = orch.seed_case(wf, case_id, seeds, provided_by=base.get("provided_by",
                                                                  "upstream-dialogue"))
    tr.set_sink(_print_progress)
    try:
        rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir, checkpoint_root=run_dir)
        approvals = 0
        while rep["status"] == "PAUSED_NEEDS_REVIEW" and approvals < 3:
            print("       %s+- human-review gate at %s (auto-approved in demo)%s"
                  % (DIM, rep["stopped_at"], RESET))
            orch.approve(state, rep["stopped_at"])
            approvals += 1
            rep = orch.run(state, wf, gate_policy="stop", kb_dir=kb_dir,
                           checkpoint_root=run_dir)
    finally:
        tr.clear_sink()

    print("-" * 78)
    print("RESULT: %s   (stopped_at=%s)" % (rep["status"], rep["stopped_at"]))
    for r in rep.get("reasons", [])[:3]:
        print("  reason: %s" % str(r)[:150])

    print()
    print(obs.render_summary_text(state))
    _print_outcome(state)
    trace_md = os.path.join(run_dir, "trace.md")
    with open(trace_md, "w", encoding="utf-8") as f:
        f.write(obs.render_trace_markdown(state))
    print()
    print("trace written to: %s" % trace_md)
    print()
    return 0


def main():
    args = [a for a in sys.argv[1:]]
    with open(os.path.join(BENCH_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(REPO, manifest["seeds_file"]), encoding="utf-8") as f:
        base = json.load(f)
    kb_empty = os.path.join(REPO, manifest["empty_kb"])
    wf = orch.load_workflow()

    if "--list" in args:
        for c in manifest["cases"]:
            print("%-26s %-24s %s" % (c["id"], c["category"], c.get("desc")))
        print("\ncurated demos:")
        for k, (cid, desc) in DEMOS.items():
            print("%-10s -> %-24s %s" % (k, cid, desc))
        return 0

    if "--case" in args:
        cid = args[args.index("--case") + 1]
        return run_demo("case %s" % cid, cid, wf, base, kb_empty, manifest)

    which = args[0] if args and not args[0].startswith("-") else None
    targets = [which] if which else ["demo-a", "demo-b"]
    rc = 0
    for name in targets:
        if name not in DEMOS:
            print("unknown demo: %s (try --list)" % name)
            return 2
        case_id, _ = DEMOS[name]
        rc |= run_demo(name, case_id, wf, base, kb_empty, manifest)
    return rc


if __name__ == "__main__":
    sys.exit(main())
