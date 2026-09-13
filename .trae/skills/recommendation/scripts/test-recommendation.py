"""Unit-test wrapper for Skill 5 Recommendation.

Run: python test-recommendation.py
Asserts:
  1. All dataset cases pass (engine + validator + expect).
  2. Negative self-check: a deliberately broken output (primary has a hard-constraint
     violation) MUST be rejected by validate_output — "inject pollution -> must go red".
"""
from __future__ import annotations

import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import run_recommendation_dataset as ds  # noqa: E402
from validate_output import validate_output  # noqa: E402


def _negative_validator_check():
    broken = {
        "skill": "recommendation",
        "version": "0.1",
        "status": "COMPLETE",
        "decision_context": {"priority_goals": [], "risk_gaps": [], "hard_constraints": [], "uncertainties": []},
        "candidate_evaluations": [{
            "candidate_id": "X",
            "requirement_fit": {"overall": "strong_fit", "score": 1.0, "matched": ["REQ-1"], "partial": [], "unmet": []},
            "risk_fit": {"overall": "strong_fit", "score": 1.0, "covered_risks": ["R1-001"], "remaining_gaps": []},
            "constraint_fit": {"hard_constraints": [], "soft_constraints": [], "violations": [
                {"type": "budget", "detail": "premium 40000 > 30000", "severity": "hard"}]},
            "evidence": {"status": "supported", "refs": ["KB-001"], "missing_evidence": []},
            "tradeoffs": [], "uncertainties": [], "recommendation_status": "primary", "provenance": []
        }],
        "primary_recommendation": {"candidate_id": "X", "fit": "strong_fit", "reason_codes": ["covers_high_priority_risk"], "provenance": []},
        "alternatives": [], "not_recommended": [], "tradeoffs": [], "uncertainties": [],
        "evidence_refs": ["KB-001"], "human_review_required": False,
    }
    ok, errors = validate_output(broken)
    assert not ok, f"negative check failed: broken output was accepted (errors={errors})"
    return True


def main():
    results = ds.run_all()
    failures = [(n, p) for n, ok, p in results if not ok]
    neg_ok = _negative_validator_check()

    all_pass = (not failures) and neg_ok
    for name, ok, problems in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        for p in problems:
            print(f"       - {p}")
    print()
    if all_pass:
        print("TEST RESULT: ALL GREEN")
        sys.exit(0)
    else:
        print("TEST RESULT: FAILURES PRESENT")
        sys.exit(1)


if __name__ == "__main__":
    main()
