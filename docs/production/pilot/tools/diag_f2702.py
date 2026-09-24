"""F27-02 diagnostic — Recommendation/Evidence logic probe (READ-ONLY
vs production: this adds a NEW diagnostic script only; runtime and
skills are untouched).

Hypothesis under test (pilot-results.md F27-02): the 12/12
INCOMPLETE_EVIDENCE / primary={} outcomes are CONTENT-driven
(single-domain demo catalog vs multi-requirement cases), not a
recommendation-engine defect.

Case A — full pipeline, single requirement the catalog CAN cover
    (keep REQ-MED only; default fixture KB with real evidence):
    EXPECT status COMPLETE + a primary recommendation EXISTS.
Case B — same upstream artifacts, knowledge evidence REMOVED,
    fed directly to the recommendation skill entrypoint
    (invoke-product-recommendation.run):
    EXPECT primary BLOCKED + status INCOMPLETE_EVIDENCE
    (eligible-but-unjustified candidate, no fabrication).

A PASS + B PASS  => the recommendation/evidence runtime logic is
behaving as designed; F27-02 reclassifies to a catalog/evidence
content gap. A FAIL => first-rejection-point report instead.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                    "..", "..", "..", ".."))
sys.path.insert(0, REPO)
PILOT = os.path.join(REPO, "docs", "production", "pilot")

PG_PASSWORD = ""
try:
    PG_PASSWORD = open(
        r"C:\Users\aubor\AppData\Local\Temp\pg_cred.txt"
    ).read().strip().split("=", 1)[1]
except (FileNotFoundError, IndexError):
    pass


def _bench():
    spec = importlib.util.spec_from_file_location(
        "run_agent_benchmark",
        os.path.join(REPO, "evals", "agent-benchmark",
                     "run_agent_benchmark.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    results = {}
    bm = _bench()
    manifest = json.load(open(os.path.join(REPO, "evals",
                                           "agent-benchmark",
                                           "manifest.json"),
                              encoding="utf-8"))
    base = json.load(open(os.path.join(REPO, manifest["seeds_file"]),
                          encoding="utf-8"))
    from runtime import orchestrator as orch
    wf = orch.load_workflow()

    # ---- Case A: full pipeline, REQ-MED only ---------------------- #
    root = os.path.join(REPO, "tmp", "pilot27", "DIAG-A")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root)
    seeds = bm.apply_mutations(copy.deepcopy(base["artifacts"]),
                               [{"op": "keep_requirements",
                                 "requirement_ids": ["REQ-MED"]}])
    state = orch.seed_case(wf, "DIAG-A", seeds,
                           provided_by="upstream-dialogue")
    rep = orch.run(state, wf, gate_policy="stop",
                   checkpoint_root=root)
    approvals = 0
    while rep["status"] == "PAUSED_NEEDS_REVIEW" and approvals < 3:
        orch.approve(state, rep["stopped_at"])
        approvals += 1
        rep = orch.run(state, wf, gate_policy="stop",
                       checkpoint_root=root)
    adir = os.path.join(root, "DIAG-A", "artifacts")
    rec = json.load(open(os.path.join(adir,
                                      "product-recommendation.json"),
                         encoding="utf-8"))
    rp = rec.get("payload", rec)
    prim = rp.get("primary_recommendation") or {}
    blocking_uncert = [u for u in (rp.get("uncertainties") or [])
                       if u.get("type") in ("insufficient_evidence",
                                            "evidence_conflict",
                                            "missing_information")]
    results["A"] = {
        "case_status": rep["status"],
        "rec_status": rp.get("status"),
        "primary_exists": bool(prim),
        "primary_cid": prim.get("candidate_id"),
        "not_recommended": len(rp.get("not_recommended") or []),
        "blocking_uncertainties": [
            {"type": u.get("type"), "detail": str(
                u.get("detail") or u.get("message") or "")[:100]}
            for u in blocking_uncert[:3]],
        "human_review_required": rp.get("human_review_required"),
        "expect": "primary exists (status may carry uncertainty "
                  "downgrades by design, engine L642-660)",
        "pass": rep["status"] == "COMPLETED" and bool(prim),
    }

    # ---- Case B: same artifacts, evidence stripped ---------------- #
    spec = importlib.util.spec_from_file_location(
        "invoke_product_recommendation",
        os.path.join(REPO, ".trae", "skills", "recommendation",
                     "scripts", "invoke-product-recommendation.py"))
    ipr = importlib.util.module_from_spec(spec)
    sys.modules["invoke_product_recommendation"] = ipr
    spec.loader.exec_module(ipr)
    rec_run = ipr.run
    v2 = {
        "requirement_analysis": json.load(open(
            os.path.join(adir, "requirement-analysis.json"),
            encoding="utf-8")).get("payload"),
        "risk_assessment": json.load(open(
            os.path.join(adir, "risk-assessment.json"),
            encoding="utf-8")).get("payload"),
        "coverage_gap_analysis": json.load(open(
            os.path.join(adir, "coverage-gap-analysis.json"),
            encoding="utf-8")).get("payload"),
        "solution_plan": json.load(open(
            os.path.join(adir, "solution-plan.json"),
            encoding="utf-8")).get("payload"),
        "product_candidates": json.load(open(
            os.path.join(adir, "product-candidates.json"),
            encoding="utf-8")).get("payload"),
        "knowledge_evidence": {"status": "insufficient_evidence",
                               "results": []},
    }
    # keys follow the V2 composite contract; tolerate naming variants
    v2b = copy.deepcopy(v2)
    for k in ("knowledge_evidence", "knowledge-evidence"):
        if k in v2b:
            v2b[k] = {"status": "insufficient_evidence", "results": []}
    try:
        out_b = rec_run(copy.deepcopy(v2b))
        if isinstance(out_b, tuple):
            out_b = out_b[0]
        ob = out_b if isinstance(out_b, dict) else json.loads(out_b)
        obp = ob.get("payload", ob)
        prim_b = obp.get("primary_recommendation") or {}
        results["B"] = {
            "rec_status": obp.get("status"),
            "primary_exists": bool(prim_b),
            "not_recommended": len(obp.get("not_recommended") or []),
            "insufficient_count": sum(
                1 for e in (obp.get("candidate_evaluations") or [])
                if e.get("recommendation_status")
                == "insufficient_evidence"),
            "expect": "primary BLOCKED + INCOMPLETE_EVIDENCE",
            "pass": not prim_b
            and obp.get("status") == "INCOMPLETE_EVIDENCE",
        }
    except Exception as e:  # noqa: BLE001 — diagnostic, report raw
        results["B"] = {"error": "%s: %s" % (type(e).__name__,
                                             str(e)[:200]),
                        "pass": False}

    json.dump(results, open(os.path.join(PILOT, "data",
                                         "diag-f2702.json"), "w",
                            encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(results, ensure_ascii=False, indent=1))
    verdict = ("LOGIC OK — F27-02 = catalog/evidence content gap"
               if results["A"]["pass"] and results["B"]["pass"]
               else "FIRST-REJECTION-POINT ANALYSIS REQUIRED")
    print("VERDICT:", verdict)
    return 0


if __name__ == "__main__":
    sys.exit(main())
