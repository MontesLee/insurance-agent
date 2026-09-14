"""Solution dataset runner (V2 Phase 3).

For each case in evals/cases/manifest.json:
  1. load the composite fixture (coverage_gap_analysis + requirement_analysis + risk_assessment)
  2. run the deterministic engine -> strict SolutionPlan payload
  3. wrap into the Canonical Contract envelope and validate against
     contracts/solution-plan.schema.json
  4. assert the per-case checks (status / solution count / ordered solution types /
     ordered priorities / primary type / information gaps / trade-offs / rejected directions)

Writes a result log to tests/contracts/_solution_dataset_log.txt (PowerShell redirection
mangles UTF-16, so we persist from Python). Exit 0 = all cases pass; 1 = any failure.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
# scripts -> solution -> skills -> .trae -> <repo root>
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from jsonschema import Draft7Validator  # noqa: E402

from solution_engine import analyze, load_rules  # noqa: E402
from adapters.base import make_envelope  # noqa: E402

CASES_DIR = os.path.join(SKILL_DIR, "evals", "cases")
CONTRACT_SCHEMA = os.path.join(REPO_ROOT, "contracts", "solution-plan.schema.json")
LOG_PATH = os.path.join(REPO_ROOT, "tests", "contracts", "_solution_dataset_log.txt")


def load_schema():
    with open(CONTRACT_SCHEMA, encoding="utf-8") as f:
        return json.load(f)


def build_provenance(payload: dict) -> list:
    prov = []
    for s in payload.get("solutions", []):
        for gid in s.get("related_gap_ids", []):
            prov.append({"source_type": "COVERAGE_GAP", "source_id": gid, "field": "solutions", "confidence": s.get("confidence")})
        for rid in s.get("related_risk_ids", []):
            prov.append({"source_type": "RISK", "source_id": rid, "field": "solutions", "confidence": s.get("confidence")})
    return prov


def check_case(case: dict, schema: dict) -> tuple:
    fixture_path = os.path.join(CASES_DIR, case["fixture"])
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)

    rules = load_rules()
    payload = analyze(
        data.get("coverage_gap_analysis"),
        data.get("requirement_analysis"),
        data.get("risk_assessment"),
        rules,
    )
    artifact = make_envelope(
        artifact_type="solution-plan",
        skill="solution",
        legacy_skill="solution",
        payload=payload,
        provenance=build_provenance(payload),
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
    solutions = payload.get("solutions", [])
    types = [s.get("solution_type") for s in solutions]
    prios = [s.get("priority") for s in solutions]
    info_gaps = payload.get("information_gaps") or []

    if "expected_status" in c and payload.get("status") != c["expected_status"]:
        fails.append(f"status={payload.get('status')} != expected {c['expected_status']}")
    if "min_solutions" in c and len(solutions) < c["min_solutions"]:
        fails.append(f"solutions={len(solutions)} < min {c['min_solutions']}")
    if "max_solutions" in c and len(solutions) > c["max_solutions"]:
        fails.append(f"solutions={len(solutions)} > max {c['max_solutions']}")
    if "expect_solution_types" in c and types != c["expect_solution_types"]:
        fails.append(f"solution_types={types} != expected {c['expect_solution_types']}")
    if "expect_priorities" in c and prios != c["expect_priorities"]:
        fails.append(f"priorities={prios} != expected {c['expect_priorities']}")
    if "primary_solution_type" in c and payload.get("solution_type") != c["primary_solution_type"]:
        fails.append(f"primary solution_type={payload.get('solution_type')} != expected {c['primary_solution_type']}")

    if c.get("require_information_gaps") and not info_gaps:
        fails.append("information_gaps expected but empty")
    if c.get("deny_information_gaps") and info_gaps:
        fails.append(f"information_gaps unexpected: {info_gaps}")

    if "expect_rejected_direction_contains" in c:
        needle = c["expect_rejected_direction_contains"]
        if not any(
            needle in (rd.get("direction") or "")
            for s in solutions
            for rd in (s.get("rejected_directions") or [])
        ):
            fails.append(f"no rejected_direction contains '{needle}'")

    if "expect_trade_off_axis" in c:
        axis = c["expect_trade_off_axis"]
        if not any(
            t.get("axis") == axis for s in solutions for t in (s.get("trade_offs") or [])
        ):
            fails.append(f"no trade_off with axis '{axis}'")

    return (len(fails) == 0, fails)


def main():
    schema = load_schema()
    manifest_path = os.path.join(CASES_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    lines = [f"SOLUTION DATASET: {len(manifest['cases'])} cases", ""]
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
