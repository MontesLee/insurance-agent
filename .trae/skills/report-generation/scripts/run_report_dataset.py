"""Full Eval regression runner for Skill 6 Report Generation.

Reads the single-source-of-truth manifest (evals/cases/dataset-manifest.json), runs the
deterministic engine + validator on every case, and asserts against each case's `expect`.
Exit 0 only if ALL cases pass; non-zero otherwise.

Run: python run_report_dataset.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from report_generation_engine import generate_report, load_rules  # noqa: E402
from validate_report import validate_output  # noqa: E402

MANIFEST = os.path.join(HERE, "..", "evals", "cases", "dataset-manifest.json")


def _check_expect(case, out, struct_ok, struct_errs):
    expect = case.get("expect", {})
    problems = []
    if not struct_ok:
        problems.append("OUTPUT_INVALID: " + "; ".join(struct_errs))

    if "status" in expect and out.get("status") != expect["status"]:
        problems.append(f"status={out.get('status')} expected {expect['status']}")

    if expect.get("provenance_nonempty") is True and not out.get("provenance"):
        problems.append("provenance is empty (expected non-empty)")

    if "rendered_forbids" in expect:
        rendered = out.get("rendered_report", "") or ""
        for tok in expect["rendered_forbids"]:
            if tok and tok in rendered:
                problems.append(f"rendered_report contains forbidden token '{tok}'")

    warnings = (out.get("metadata", {}) or {}).get("warnings", []) or []
    if "metadata_warnings_contains" in expect:
        for w in expect["metadata_warnings_contains"]:
            if not any(w in x for x in warnings):
                problems.append(f"metadata.warnings missing '{w}' (got {warnings})")

    conflicts = (out.get("metadata", {}) or {}).get("conflicts", []) or []
    if expect.get("metadata_conflicts_nonempty") is True and not conflicts:
        problems.append("metadata.conflicts expected non-empty but empty")
    if expect.get("metadata_conflicts_nonempty") is False and conflicts:
        problems.append(f"metadata.conflicts expected empty but got {conflicts}")

    vconf = (out.get("validation", {}) or {}).get("conflicts", []) or []
    if expect.get("validation_conflicts_nonempty") is True and not vconf:
        problems.append("validation.conflicts expected non-empty but empty")
    if expect.get("validation_conflicts_nonempty") is False and vconf:
        problems.append(f"validation.conflicts expected empty but got {vconf}")

    gaps = out.get("structured_report", {}).get("information_gaps", []) or []
    gap_fields = " ".join(g.get("field", "") for g in gaps)
    if "information_gaps_contains" in expect:
        for f in expect["information_gaps_contains"]:
            if f not in gap_fields:
                problems.append(f"information_gaps missing field '{f}' (got {gap_fields})")

    actions = out.get("structured_report", {}).get("next_actions", []) or []
    action_text = " ".join(a.get("action", "") + " " + a.get("reason", "") for a in actions)
    if "next_actions_contains" in expect:
        for f in expect["next_actions_contains"]:
            if f not in action_text:
                problems.append(f"next_actions missing reference to '{f}'")

    return problems


def run_all(rules=None):
    if rules is None:
        rules = load_rules()
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    results = []
    for case in manifest["cases"]:
        out = generate_report(case["input"], rules)
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
