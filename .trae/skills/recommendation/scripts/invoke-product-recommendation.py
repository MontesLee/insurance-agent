"""Phase 5 V2 entrypoint: product-recommendation.

Input  : canonical V2 composite (requirement_analysis + risk_assessment +
         coverage_gap_analysis + solution_plan [+ knowledge_evidence] [+ constraints]).
         `candidate_solutions` is FORBIDDEN here -- it is derived from solution_plan.
Output : canonical ProductRecommendation artifact (contract-validated).

Pipeline:
    V2 input --(schema)--> translate SolutionPlan -> candidates --> legacy engine
             --(schema)--> adapter --> canonical contract --(schema)--> out

The evaluation logic itself is NOT re-implemented; it still runs through
recommendation_engine, which keeps the 11 legacy eval cases as the regression baseline.
"""
from __future__ import annotations

import argparse
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

from solution_to_candidates import build_v2_input, load_rules as load_translate_rules  # noqa: E402
from recommendation_engine import generate_recommendation, load_rules as load_engine_rules  # noqa: E402
from adapters.recommendation_adapter import to_canonical  # noqa: E402

INPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "product-recommendation-input.schema.json")
OUTPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "recommendation-output.schema.json")
CANONICAL_SCHEMA = os.path.join(REPO_ROOT, "contracts", "product-recommendation.schema.json")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _validate(instance, schema_path, label):
    if not os.path.exists(schema_path):
        return ["%s: schema missing at %s" % (label, schema_path)]
    try:
        from jsonschema import Draft7Validator
    except ImportError:
        return ["%s: jsonschema not installed; skipped" % label]
    v = Draft7Validator(_load(schema_path))
    return ["%s: %s" % (label, e.message) for e in sorted(v.iter_errors(instance), key=str)]


def run(v2_input, translate_rules=None, engine_rules=None):
    """Returns (canonical_artifact, warnings).

    The canonical contract sets `additionalProperties: false`, so validation findings must
    be returned alongside the artifact -- never injected into it.
    """
    errors = _validate(v2_input, INPUT_SCHEMA, "V2 input")
    if errors:
        return {"_validation_errors": errors, "status": "INSUFFICIENT_INPUT"}, errors

    legacy_input = build_v2_input(
        requirement_analysis=v2_input.get("requirement_analysis"),
        risk_assessment=v2_input.get("risk_assessment"),
        coverage_gap_analysis=v2_input.get("coverage_gap_analysis"),
        solution_plan=v2_input.get("solution_plan"),
        knowledge_evidence=v2_input.get("knowledge_evidence"),
        constraints=v2_input.get("constraints"),
        rules=translate_rules,
    )

    out = generate_recommendation(legacy_input, engine_rules)

    warnings = _validate(out, OUTPUT_SCHEMA, "legacy output")
    canonical = to_canonical(out)
    warnings += _validate(canonical, CANONICAL_SCHEMA, "canonical output")

    canonical["payload"]["candidate_source"] = "solution_plan"
    canonical["payload"]["derivation"] = {
        "candidate_solutions_supplied_as_input": False,
        "candidate_solutions_derived_from": "solution_plan.solutions[]",
    }
    return canonical, warnings


def main():
    ap = argparse.ArgumentParser(description="product-recommendation (V2 canonical entrypoint)")
    ap.add_argument("--input", required=True, help="V2 composite input JSON")
    ap.add_argument("--output", required=False, help="Where to write the canonical output JSON")
    ap.add_argument("--rules", required=False, help="Override engine rules JSON")
    ap.add_argument("--translate-rules", required=False, help="Override translator rules JSON")
    a = ap.parse_args()

    v2_input = _load(a.input)
    tr = load_translate_rules(a.translate_rules) if a.translate_rules else None
    er = load_engine_rules(a.rules) if a.rules else None

    result, warnings = run(v2_input, tr, er)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("written: %s" % a.output)
    else:
        print(text)
    for w in warnings:
        print("[warn] %s" % w, file=sys.stderr)
    sys.exit(1 if result.get("_validation_errors") else 0)


if __name__ == "__main__":
    main()
