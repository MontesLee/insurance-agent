"""Phase 5 V2 dataset runner: product-recommendation.

Runs every case in evals/cases/product-recommendation-manifest.json (the single source of
truth) through the V2 entrypoint and asserts:
  * the V2 input validates against product-recommendation-input.schema.json
    (which machine-enforces that `candidate_solutions` is NOT supplied),
  * the canonical output validates against contracts/product-recommendation.schema.json,
  * per-case `expect` assertions.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
# scripts -> recommendation -> skills -> .trae -> insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from jsonschema import Draft7Validator  # noqa: E402

# The entrypoint filename is kebab-cased (AGENTS.md), so it cannot be imported by module
# name -- load it from its path instead.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "invoke_product_recommendation",
    os.path.join(HERE, "invoke-product-recommendation.py"),
)
ipr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ipr)

MANIFEST = os.path.join(SKILL_DIR, "evals", "cases", "product-recommendation-manifest.json")
CANONICAL_SCHEMA = os.path.join(REPO_ROOT, "contracts", "product-recommendation.schema.json")
INPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "product-recommendation-input.schema.json")
LOG = os.path.join(REPO_ROOT, "tests", "contracts", "_product_rec_dataset_log.txt")

LEGACY = {
    "requirement_analysis": ("requirement-analysis", "requirement_analysis"),
    "risk_assessment": ("risk-assessment", "risk-analysis"),
    "coverage_gap_analysis": ("coverage-gap-analysis", "coverage-gap-analysis"),
    "solution_plan": ("solution-plan", "solution"),
    "knowledge_evidence": ("knowledge-evidence", "knowledge-search"),
}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def envelope(key, payload):
    at, legacy = LEGACY[key]
    canonical_skill = {"requirement-analysis": "requirement-analysis",
                       "risk-assessment": "risk-analysis",
                       "coverage-gap-analysis": "coverage-gap-analysis",
                       "solution-plan": "solution",
                       "knowledge-evidence": "knowledge-search"}[at]
    return {
        "artifact_type": at,
        "skill": canonical_skill,
        "legacy_skill": legacy,
        "schema_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "payload": payload,
        "provenance": [],
    }


def check_case(case):
    """Return list of failure strings (empty == pass)."""
    fails = []
    raw = case["input"]

    # P1 guard: the V2 composite must never carry candidate_solutions.
    if "candidate_solutions" in raw:
        fails.append("P1 VIOLATION: input carries candidate_solutions")

    v2_input = {}
    for k, payload in raw.items():
        v2_input[k] = envelope(k, payload) if k in LEGACY else payload

    errs = [e.message for e in Draft7Validator(_load(INPUT_SCHEMA)).iter_errors(v2_input)]
    if errs:
        fails.extend("input-schema: " + e for e in errs)
        return fails

    result, warnings = ipr.run(v2_input)
    if result.get("_validation_errors"):
        fails.extend("output: " + e for e in result["_validation_errors"])
        return fails
    # Legacy-output / canonical schema findings are real defects, not noise.
    fails.extend("validation: " + w for w in warnings)

    cerrs = [e.message for e in Draft7Validator(_load(CANONICAL_SCHEMA)).iter_errors(result)]
    if cerrs:
        fails.extend("canonical-schema: " + e for e in cerrs)

    p = result["payload"]
    ex = case.get("expect", {})

    if "status" in ex and p.get("status") != ex["status"]:
        fails.append("status: expected %s got %s" % (ex["status"], p.get("status")))

    prim = p.get("primary_recommendation")
    prim_id = prim.get("candidate_id") if isinstance(prim, dict) else None
    if "primary_id" in ex and prim_id != ex["primary_id"]:
        fails.append("primary_id: expected %s got %s" % (ex["primary_id"], prim_id))

    if "human_review_required" in ex and p.get("human_review_required") != ex["human_review_required"]:
        fails.append("human_review_required: expected %s got %s"
                     % (ex["human_review_required"], p.get("human_review_required")))

    if "not_recommended" in ex:
        got = sorted(n.get("candidate_id") for n in p.get("not_recommended", []))
        if got != sorted(ex["not_recommended"]):
            fails.append("not_recommended: expected %s got %s" % (ex["not_recommended"], got))

    if "alternatives_include" in ex:
        got = {a.get("candidate_id") for a in p.get("alternatives", [])}
        for want in ex["alternatives_include"]:
            if want not in got:
                fails.append("alternatives: missing %s (got %s)" % (want, sorted(got)))

    if "candidate_count" in ex:
        n = len(p.get("candidate_evaluations", []))
        if n != ex["candidate_count"]:
            fails.append("candidate_count: expected %s got %s" % (ex["candidate_count"], n))

    if "evidence_insufficient_candidates" in ex:
        got = sorted(e.get("candidate_id") for e in p.get("candidate_evaluations", [])
                     if e.get("evidence", {}).get("status") != "supported")
        if got != sorted(ex["evidence_insufficient_candidates"]):
            fails.append("evidence_insufficient: expected %s got %s"
                         % (ex["evidence_insufficient_candidates"], got))

    if "unverifiable_constraints" in ex:
        got = sorted({u.get("type") for e in p.get("candidate_evaluations", [])
                      for u in e.get("constraint_fit", {}).get("unverifiable_constraints", [])})
        if got != sorted(ex["unverifiable_constraints"]):
            fails.append("unverifiable_constraints: expected %s got %s"
                         % (ex["unverifiable_constraints"], got))

    if "reason_codes_exclude" in ex:
        codes = set((prim or {}).get("reason_codes", []) or [])
        for bad in ex["reason_codes_exclude"]:
            if bad in codes:
                fails.append("reason_codes: must not contain %s (got %s)" % (bad, sorted(codes)))

    return fails


def main():
    manifest = _load(MANIFEST)
    lines = ["product-recommendation V2 dataset (%s)" % manifest.get("version"), ""]
    all_ok = True
    for case in manifest["cases"]:
        try:
            fails = check_case(case)
        except Exception as exc:  # noqa: BLE001
            import traceback
            fails = ["EXCEPTION: %s\n%s" % (exc, traceback.format_exc())]
        if fails:
            all_ok = False
            lines.append("[FAIL] %s" % case["name"])
            for f in fails:
                lines.append("       - %s" % f)
        else:
            lines.append("[PASS] %s  (%s)" % (case["name"], case.get("dimension", "-")))
    lines.append("")
    lines.append("DATASET RESULT: %s" % ("ALL GREEN" if all_ok else "FAILURES PRESENT"))
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
