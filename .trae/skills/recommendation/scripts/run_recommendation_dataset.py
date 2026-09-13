"""Full Eval regression runner for Skill 5 Recommendation.

Reads the single-source-of-truth manifest (evals/cases/dataset-manifest.json), runs the
deterministic engine + validator on every case, and asserts against each case's `expect` block.
Exit 0 only if ALL cases pass; non-zero otherwise.

Run: python run_recommendation_dataset.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
# REPO_ROOT = .trae/skills/recommendation -> up to insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from recommendation_engine import generate_recommendation, load_rules  # noqa: E402
from validate_output import validate_output  # noqa: E402

MANIFEST = os.path.join(HERE, "..", "evals", "cases", "dataset-manifest.json")


def _check_expect(case, out, struct_ok, struct_errs):
    expect = case.get("expect", {})
    problems = []
    if not struct_ok:
        problems.append("OUTPUT_INVALID: " + "; ".join(struct_errs))
    if "status" in expect and out.get("status") != expect["status"]:
        problems.append(f"status={out.get('status')} expected {expect['status']}")
    # primary id (exact)
    if "primary_id" in expect:
        got = (out.get("primary_recommendation") or {}).get("candidate_id")
        if expect["primary_id"] is None:
            if got is not None:
                problems.append(f"primary={got} expected None")
        elif got != expect["primary_id"]:
            problems.append(f"primary={got} expected {expect['primary_id']}")
    # primary in (a set of acceptable ids)
    if "primary_in" in expect:
        got = (out.get("primary_recommendation") or {}).get("candidate_id")
        if got not in expect["primary_in"]:
            problems.append(f"primary={got} not in {expect['primary_in']}")
    if "human_review_required" in expect and out.get("human_review_required") != expect["human_review_required"]:
        problems.append(f"human_review={out.get('human_review_required')} expected {expect['human_review_required']}")
    if "not_recommended" in expect:
        got_nr = sorted(e["candidate_id"] for e in out.get("not_recommended", []))
        exp_nr = sorted(expect["not_recommended"])
        if got_nr != exp_nr:
            problems.append(f"not_recommended={got_nr} expected {exp_nr}")
    if "evidence_insufficient_candidates" in expect:
        ev_by_id = {e["candidate_id"]: e["evidence"]["status"] for e in out.get("candidate_evaluations", [])}
        for cid in expect["evidence_insufficient_candidates"]:
            if ev_by_id.get(cid) not in ("insufficient", "conflict"):
                problems.append(f"candidate {cid} evidence={ev_by_id.get(cid)} not insufficient/conflict")
    if "expect_candidate_fit" in expect:
        fits = {e["candidate_id"]: e["requirement_fit"]["overall"] for e in out.get("candidate_evaluations", [])}
        for cid, lbl in expect["expect_candidate_fit"].items():
            if fits.get(cid) != lbl:
                problems.append(f"candidate {cid} req_fit={fits.get(cid)} expected {lbl}")
    if "expect_candidate_risk_gaps" in expect:
        gaps = {e["candidate_id"]: sorted(e["risk_fit"]["remaining_gaps"]) for e in out.get("candidate_evaluations", [])}
        for cid, gl in expect["expect_candidate_risk_gaps"].items():
            if gaps.get(cid) != sorted(gl):
                problems.append(f"candidate {cid} risk_gaps={gaps.get(cid)} expected {sorted(gl)}")
    return problems


def run_all(rules=None):
    if rules is None:
        rules = load_rules()
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    results = []
    for case in manifest["cases"]:
        out = generate_recommendation(case["input"], rules)
        ok_struct, errs = validate_output(out)
        problems = _check_expect(case, out, ok_struct, errs)
        ok = (len(problems) == 0)
        results.append((case["name"], ok, problems))
    return results


def main():
    results = run_all()
    all_ok = True
    for name, ok, problems in results:
        if ok:
            print(f"[PASS] {name}")
        else:
            all_ok = False
            print(f"[FAIL] {name}")
            for p in problems:
                print(f"       - {p}")
    print()
    if all_ok:
        print("DATASET RESULT: ALL GREEN")
        sys.exit(0)
    else:
        print("DATASET RESULT: FAILURES PRESENT")
        sys.exit(1)


if __name__ == "__main__":
    main()
