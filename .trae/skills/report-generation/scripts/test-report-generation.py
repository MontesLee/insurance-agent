"""Unit-test wrapper for Skill 6 Report Generation.

Run: python test-report-generation.py
Asserts:
  1. All dataset cases pass (engine + validator + expect).
  2. Negative self-check #1: a structurally-valid but semantically-broken output
     (status=success with empty provenance) MUST be rejected by validate_output.
  3. Negative self-check #2: a report containing a monetary figure with no upstream
     source MUST be flagged as HALLUCINATION by the engine's validate_report.
"""
from __future__ import annotations

import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import run_report_dataset as ds  # noqa: E402
from validate_report import validate_output  # noqa: E402
from report_generation_engine import validate_report as engine_validate, load_rules  # noqa: E402


def _negative_provenance_check():
    broken = {
        "skill": "report-generation", "version": "0.1", "status": "success",
        "structured_report": {
            "title": "x", "version": "1.0", "generated_at": "2026-01-01T00:00:00Z",
            "client_profile": {"fields": [{"label": "年龄", "value": "30", "status": "KNOWN", "source": "client_state.family_profile.age"}], "note": "ok"},
            "financial_profile": {"table": [], "note": "ok"},
            "risk_exposure": {rc: {"present": False, "risk_category": rc, "note": "n"} for rc in ["R1", "R2", "R3", "R4", "R5"]},
            "coverage_gaps": [], "requirement_priorities": [], "recommended_directions": [],
            "information_gaps": [], "next_actions": [],
        },
        "rendered_report": "x", "validation": {"passed": True, "errors": [], "warnings": [], "conflicts": []},
        "metadata": {"source_skills": ["client-intake"], "upstream_status": {}, "conflicts": [], "warnings": []},
        "provenance": [],
    }
    ok, errors = validate_output(broken)
    assert not ok, f"negative #1 failed: broken output (success+empty provenance) was accepted (errors={errors})"
    return True


def _negative_hallucination_check():
    rules = load_rules()
    normalized = {
        "client_state": {"missing": True, "financial_profile": {}},
        "requirement_analysis": {"missing": True},
        "risk_analysis": {"missing": True},
        "knowledge_search": {"missing": True},
        "recommendation": {"missing": True},
        "missing_core": [], "all_core_missing": False,
    }
    report = {
        "status": "success",
        "structured_report": {
            "title": "x", "version": "1.0", "generated_at": "2026-01-01T00:00:00Z",
            "client_profile": {"fields": [], "note": "ok"},
            "financial_profile": {"table": [], "note": "ok"},
            "risk_exposure": {rc: {"present": False, "risk_category": rc, "note": "n"} for rc in ["R1", "R2", "R3", "R4", "R5"]},
            "coverage_gaps": [], "requirement_priorities": [], "recommended_directions": [],
            "information_gaps": [], "next_actions": [],
        },
        "rendered_report": "客户年收入 9999万，房贷 8888万。",
        "metadata": {"conflicts": []},
        "provenance": [{"claim": "x", "source": "client_state", "confidence": "medium"}],
    }
    result = engine_validate(report, rules, normalized)
    bad = [e for e in result["errors"] if e.startswith("HALLUCINATION")]
    assert bad, f"negative #2 failed: hallucinated monetary figure not flagged (errors={result['errors']})"
    return True


def main():
    results = ds.run_all()
    failures = [(n, p) for n, ok, p in results if not ok]
    neg1 = _negative_provenance_check()
    neg2 = _negative_hallucination_check()

    all_pass = (not failures) and neg1 and neg2
    for name, ok, problems in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        for p in problems:
            print(f"       - {p}")
    print()
    print(f"negative self-check #1 (broken provenance rejected): {'OK' if neg1 else 'FAIL'}")
    print(f"negative self-check #2 (hallucination flagged):      {'OK' if neg2 else 'FAIL'}")
    print()
    if all_pass:
        print("TEST RESULT: ALL GREEN")
        sys.exit(0)
    else:
        print("TEST RESULT: FAILURES PRESENT")
        sys.exit(1)


if __name__ == "__main__":
    main()
