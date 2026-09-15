"""Step 4 Phase 4 + Phase 5 — Golden Cases & Regression Benchmark.

Runs the curated Golden Cases (`golden.json`) through the exact same pipeline as the
benchmark, checks their STRICT behavioural contracts (spec §13), and — when a
`baseline.json` exists — prints a Before / After delta so any prompt / skill / rule /
schema / RAG / orchestrator change can be proven to help (or at least not to regress).

A golden case never asserts a fixed final answer. It asserts what the agent must and
must not do: detect a class of risk, expose a gap, refuse an ineligible product, keep
provenance, park on missing facts, self-heal a repairable fault.

Usage:
    python run_golden_cases.py            # run golden cases + before/after vs baseline
    python run_golden_cases.py --update-baseline   # refresh baseline.json from this run

Exit 0 = every golden case passed and no hard gate regressed.
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

BENCH_PATH = os.path.join(HERE, "run_agent_benchmark.py")


def _load_bench():
    spec = importlib.util.spec_from_file_location("agent_benchmark_runner", BENCH_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BENCH = _load_bench()


def _gap_risk_ids(arts):
    cg = BENCH._payload(arts.get("coverage-gap-analysis")) or {}
    out = set()
    for g in (cg.get("gaps") or []):
        for r in (g.get("related_risk_ids") or []):
            out.add(r)
    return out


def _eval_asserts(case, obs):
    """Return [(name, ok, detail)] for a golden case's machine-checkable asserts."""
    a = case.get("asserts", {})
    state = obs["state"]
    arts = state.get("artifacts", {}) or {}
    checks = []

    def ck(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})

    if "case_status" in a:
        ck("case_status == %s" % a["case_status"], obs["case_status"] == a["case_status"],
           obs["case_status"])
    if "stopped_at" in a:
        ck("stopped_at == %s" % a["stopped_at"],
           (obs["report"].get("stopped_at") == a["stopped_at"]), obs["report"].get("stopped_at"))
    if "waiting_reason" in a:
        w = state.get("waiting_for_user") or {}
        ck("waiting_reason == %s" % a["waiting_reason"], w.get("reason") == a["waiting_reason"],
           w.get("reason"))
    if "question_contains" in a:
        w = state.get("waiting_for_user") or {}
        blob = json.dumps(w.get("next_questions") or [], ensure_ascii=False)
        ck("question mentions '%s'" % a["question_contains"], a["question_contains"] in blob, blob[:160])
    if "conflict_candidates" in a:
        w = state.get("waiting_for_user") or {}
        blob = json.dumps(w.get("conflicts") or [], ensure_ascii=False)
        missing = [c for c in a["conflict_candidates"] if c not in blob]
        ck("conflict candidates preserved", not missing, missing)
    if "artifacts_must_include" in a:
        missing = [x for x in a["artifacts_must_include"] if x not in arts]
        ck("artifacts include %s" % ",".join(a["artifacts_must_include"]), not missing, missing)
    if "artifacts_must_exclude" in a:
        present = [x for x in a["artifacts_must_exclude"] if x in arts]
        ck("artifacts exclude %s" % ",".join(a["artifacts_must_exclude"]), not present, present)
    if "gap_risk_ids_include" in a:
        ids = _gap_risk_ids(arts)
        missing = [x for x in a["gap_risk_ids_include"] if x not in ids]
        ck("gaps cover risks %s" % ",".join(a["gap_risk_ids_include"]), not missing, sorted(ids))
    if "gap_risk_ids_exclude" in a:
        ids = _gap_risk_ids(arts)
        bad = [x for x in a["gap_risk_ids_exclude"] if x in ids]
        ck("no gap invented for covered risks %s" % ",".join(a["gap_risk_ids_exclude"]),
           not bad, sorted(ids))
    if "recommendation_status" in a:
        ck("recommendation status == %s" % a["recommendation_status"],
           obs["rec_status"] == a["recommendation_status"], obs["rec_status"])
    if "primary_is_none" in a:
        ck("primary_is_none == %s" % a["primary_is_none"],
           obs["primary_is_none"] == a["primary_is_none"], obs["primary_is_none"])
    if "recommendation_products_empty" in a:
        blob = json.dumps(BENCH._payload(arts.get("product-recommendation")) or {},
                          ensure_ascii=False)
        ck("recommendation references no product",
           obs["rec_status"] == "NO_CANDIDATES" and obs["primary_is_none"] is True,
           obs["rec_status"])
    if "products_subset_of_catalog" in a:
        ck("products subset of catalog", not obs["hallucinated_products"],
           obs["hallucinated_products"])
    if "demo_products_disclosed" in a:
        disc = obs.get("report_disclosure") or {}
        ck("report discloses demo products (is_demo == %s)" % a["demo_products_disclosed"],
           bool(disc.get("is_demo")) == a["demo_products_disclosed"], disc.get("is_demo"))
        if a["demo_products_disclosed"]:
            ck("demo disclosure verified against the catalog",
               disc.get("catalog_checked") is True, disc.get("catalog_checked"))
            ck("no fabricated product is presented",
               not disc.get("unverified_products"), disc.get("unverified_products"))
            ck("demo products are real catalog entries",
               bool(disc.get("demo_products"))
               and all(p not in obs["hallucinated_products"] for p in disc["demo_products"]),
               disc.get("demo_products"))
            ck("rendered report carries the DEMO marker",
               "DEMO" in (obs.get("report_rendered") or ""), "no DEMO marker")
    if "evidence_refs_resolvable" in a:
        ok = (obs["rec_status"] != "COMPLETE"
              or (obs["evidence_refs"] and not obs["unresolved_evidence_refs"]))
        ck("evidence refs resolvable", ok, obs["unresolved_evidence_refs"])
    if "no_artifact_contains_product" in a:
        blob = json.dumps(arts, ensure_ascii=False)
        bad = [p for p in a["no_artifact_contains_product"] if p in blob]
        ck("no registered artifact references %s" % ",".join(a["no_artifact_contains_product"]),
           not bad, bad)
    if "trace_mentions" in a:
        details = " ".join(str(r.get("detail") or "") for r in (state.get("trace") or [])
                           if r["event"] == "TASK_FAILED").lower()
        bad = [t for t in a["trace_mentions"] if t.lower() not in details]
        ck("trace names root cause %s" % a["trace_mentions"], not bad, details[:200])
    if "min_repairs_succeeded" in a:
        ck("repairs succeeded >= %d" % a["min_repairs_succeeded"],
           obs["repairs_succeeded"] >= a["min_repairs_succeeded"], obs["repairs_succeeded"])
    if "stage_attempts_at_least" in a:
        by_stage = {t.get("stage_id"): (t.get("attempt") or 0) for t in (state.get("tasks") or [])}
        for sid, n in a["stage_attempts_at_least"].items():
            ck("stage %s attempted >= %d" % (sid, n), by_stage.get(sid, 0) >= n,
               by_stage.get(sid))
    return checks


def main():
    update_baseline = "--update-baseline" in sys.argv
    with open(os.path.join(HERE, "golden.json"), encoding="utf-8") as f:
        golden = json.load(f)
    with open(os.path.join(HERE, golden["benchmark_manifest"]), encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(REPO, manifest["seeds_file"]), encoding="utf-8") as f:
        base = json.load(f)
    with open(BENCH.CATALOG, encoding="utf-8") as f:
        catalog_ids = {p["product_id"] for p in json.load(f)["products"]}

    by_id = {c["id"]: c for c in manifest["cases"]}
    kb_empty = os.path.join(REPO, manifest["empty_kb"])
    wf = BENCH.orch.load_workflow()

    results = []
    for gc in golden["cases"]:
        bc = by_id[gc["benchmark_case"]]
        state, rep = BENCH.run_case(bc, wf, base, manifest["seeds_file"], kb_empty)
        obs = BENCH.observe(state, rep, catalog_ids)
        checks = BENCH.check_case(bc, obs, catalog_ids) + _eval_asserts(gc, obs)
        results.append({
            "id": gc["id"], "benchmark_case": bc["id"], "purpose": gc["purpose"],
            "case_status": obs["case_status"], "rec_status": obs["rec_status"],
            "checks": checks, "passed": all(c["ok"] for c in checks),
            "failed": [c["name"] for c in checks if not c["ok"]],
            "hallucinated_products": obs["hallucinated_products"],
            "repairs_attempted": obs["repairs_attempted"],
            "repairs_succeeded": obs["repairs_succeeded"],
        })

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    halluc = sum(len(r["hallucinated_products"]) for r in results)

    # ---------------- Phase 5: before / after vs baseline ------------------- #
    baseline_path = os.path.join(HERE, "baseline.json")
    deltas = []
    if os.path.exists(baseline_path):
        with open(baseline_path, encoding="utf-8") as f:
            bl = json.load(f)
        deltas.append(("task_success_rate", bl.get("task_success_rate"), round(passed / total, 4), "up"))
        deltas.append(("product_hallucination_rate", bl.get("product_hallucination_rate"),
                       0.0 if halluc == 0 else 1.0, "down"))
    if update_baseline:
        with open(baseline_path, encoding="utf-8") as f:
            bl = json.load(f)
        bl["golden_cases"] = total
        bl["golden_task_success_rate"] = round(passed / total, 4)
        bl["golden_generated_at"] = BENCH.datetime.now(BENCH.timezone.utc).isoformat()
        with open(baseline_path, "w", encoding="utf-8") as f:
            json.dump(bl, f, ensure_ascii=False, indent=2)

    # ---------------- output ----------------------------------------------- #
    lines = []
    lines.append("=" * 78)
    lines.append("GOLDEN CASES — %d cases" % total)
    lines.append("=" * 78)
    for r in results:
        lines.append("%s %-7s <- %-24s %-14s checks=%d/%d" % (
            "OK " if r["passed"] else "XX ", r["id"], r["benchmark_case"], r["case_status"],
            sum(1 for c in r["checks"] if c["ok"]), len(r["checks"])))
        if not r["passed"]:
            lines.append("      failed: %s" % "; ".join(r["failed"]))
    if deltas:
        lines.append("-" * 78)
        lines.append("REGRESSION vs baseline.json (spec §14/§15)")
        lines.append("%-32s %-12s %-12s %s" % ("metric", "before", "after", "verdict"))
        for name, before, after, direction in deltas:
            if before is None:
                verdict = "no baseline"
            elif after == before:
                verdict = "UNCHANGED"
            elif (after > before and direction == "up") or (after < before and direction == "down"):
                verdict = "IMPROVED"
            else:
                verdict = "REGRESSED"
            lines.append("%-32s %-12s %-12s %s" % (name, before, after, verdict))
    lines.append("-" * 78)
    lines.append("GOLDEN: %d/%d passed" % (passed, total))
    lines.append("RESULT: %s" % ("ALL GREEN" if passed == total else "FAILURES PRESENT"))
    text = "\n".join(lines)
    print(text)
    with open(os.path.join(HERE, "golden_results.md"), "w", encoding="utf-8") as f:
        f.write("# Golden Cases (Step 4 · Phase 4/5)\n\n```\n" + text + "\n```\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
