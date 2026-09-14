#!/usr/bin/env python3
"""Run all 9 Canonical Contract tests for Insurance Agent V2 (Phase 1).

Exit 0 only if ALL contract tests pass.
Run: python tests/contracts/run_contract_tests.py
"""
import importlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

TEST_MODULES = [
    "test_client_profile_contract",
    "test_requirement_analysis_contract",
    "test_risk_assessment_contract",
    "test_coverage_gap_contract",
    "test_solution_plan_contract",
    "test_knowledge_query_contract",
    "test_knowledge_evidence_contract",
    "test_product_recommendation_contract",
    "test_insurance_report_contract",
]


def main():
    results = []
    for mod_name in TEST_MODULES:
        try:
            mod = importlib.import_module(mod_name)
            name, ok, detail = mod.run()
        except Exception as e:  # noqa: BLE001
            import traceback
            name = mod_name
            ok = False
            detail = "EXCEPTION: " + repr(e) + "\n" + traceback.format_exc()
        results.append((name, ok, detail))

    all_ok = True
    for name, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        print(f"[{status}] {name}")
        if not ok:
            print("       " + detail.replace("\n", "\n       "))

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"CONTRACT TESTS: {passed}/{len(results)} passed")
    log_lines = [f"[{'PASS' if ok else 'FAIL'}] {name}" for name, ok, _ in results]
    log_lines.append(f"CONTRACT TESTS: {passed}/{len(results)} passed")
    log_lines.append("RESULT: " + ("ALL GREEN" if all_ok else "FAILURES PRESENT"))
    with open(os.path.join(HERE, "_contract_test_log.txt"), "w", encoding="utf-8") as lf:
        lf.write("\n".join(log_lines) + "\n")
    if all_ok:
        print("RESULT: ALL GREEN")
        sys.exit(0)
    else:
        print("RESULT: FAILURES PRESENT")
        sys.exit(1)


if __name__ == "__main__":
    main()
