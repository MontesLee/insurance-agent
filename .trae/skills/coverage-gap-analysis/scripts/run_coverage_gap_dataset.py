"""Coverage-gap-analysis dataset runner (V2 Phase 2).

For each case in evals/cases/manifest.json:
  1. load the composite fixture (client_profile + requirement_analysis + risk_assessment)
  2. run the deterministic engine -> strict CoverageGap payload
  3. wrap into the Canonical Contract envelope and validate against
     contracts/coverage-gap-analysis.schema.json
  4. assert the per-case checks (status / gap count / gap levels / skip domain / info gaps)

Writes a result log to tests/contracts/_coverage_gap_dataset_log.txt (PowerShell redirection
mangles UTF-16, so we persist from Python). Exit 0 = all cases pass; 1 = any failure.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from jsonschema import Draft7Validator  # noqa: E402

from coverage_gap_engine import analyze, load_rules  # noqa: E402
from adapters.base import make_envelope  # noqa: E402

CASES_DIR = os.path.join(SKILL_DIR, "evals", "cases")
CONTRACT_SCHEMA = os.path.join(REPO_ROOT, "contracts", "coverage-gap-analysis.schema.json")
LOG_PATH = os.path.join(REPO_ROOT, "tests", "contracts", "_coverage_gap_dataset_log.txt")


def load_schema():
    with open(CONTRACT_SCHEMA, encoding="utf-8") as f:
        return json.load(f)


def check_case(case: dict, schema: dict) -> tuple[bool, list]:
    fixture_path = os.path.join(CASES_DIR, case["fixture"])
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    rules = load_rules()
    payload = analyze(data.get("client_profile"), data.get("requirement_analysis"), data.get("risk_assessment"), rules)
    artifact = make_envelope(
        artifact_type="coverage-gap-analysis",
        skill="coverage-gap-analysis",
        legacy_skill="coverage-gap-analysis",
        payload=payload,
        provenance=[{"source_type": "RISK", "source_id": g["related_risk_ids"][0], "confidence": g.get("confidence")} for g in payload.get("gaps", [])],
    )

    # 1) contract validation
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    if errors:
        msgs = [f"CONTRACT:{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
        return False, msgs

    # 2) per-case checks
    fails = []
    c = case.get("checks", {})
    gaps = payload.get("gaps", [])
    levels = {g["gap_level"] for g in gaps}
    domains = {g["domain"] for g in gaps}

    if "expected_status" in c and payload.get("status") != c["expected_status"]:
        fails.append(f"status={payload.get('status')} != expected {c['expected_status']}")
    if "min_gaps" in c and len(gaps) < c["min_gaps"]:
        fails.append(f"gaps={len(gaps)} < min {c['min_gaps']}")
    for lv in c.get("expect_gap_levels", []):
        if lv not in levels:
            fails.append(f"missing expected gap_level {lv}")
    for lv in c.get("deny_gap_levels", []):
        if lv in levels:
            fails.append(f"unexpected gap_level {lv} present")
    if "must_skip_domain" in c and c["must_skip_domain"] in domains:
        fails.append(f"domain {c['must_skip_domain']} should be skipped (SUFFICIENT) but produced a gap")
    if c.get("require_information_gaps") and not payload.get("information_gaps"):
        fails.append("information_gaps expected but empty")

    return (len(fails) == 0, fails)


def main():
    schema = load_schema()
    manifest_path = os.path.join(CASES_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    lines = [f"COVERAGE-GAP DATASET: {len(manifest['cases'])} cases", ""]
    all_ok = True
    for case in manifest["cases"]:
        ok, detail = check_case(case, schema)
        tag = "PASS" if ok else "FAIL"
        lines.append(f"[{tag}] {case['case_id']} | {case.get('intent','')}")
        if not ok:
            all_ok = False
            for d in detail:
                lines.append(f"    - {d}")
    lines.append("")
    lines.append("RESULT: " + ("ALL GREEN" if all_ok else "FAILURES PRESENT"))

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
