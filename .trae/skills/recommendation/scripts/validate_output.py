"""Deterministic output validator for Skill 5 Recommendation.

Two layers (mirrors AGENTS.md §5 "code does deterministic validation"):
  1. Structural: jsonschema Draft7 validation of RecommendationOutput.
  2. Consistency: business-invariant checks that a schema cannot express, e.g.
     - primary_recommendation.candidate_id must exist in candidate_evaluations
     - a candidate with a hard-constraint violation must NOT be primary
       (unless explicitly flagged exception + human_review_required)
     - status=insufficient_evidence / a candidate with insufficient evidence
       must carry an uncertainty entry
     - status=COMPLETE with a primary must expose non-empty evidence_refs

Run: python validate_output.py <output.json> [--schema <path>]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover
    Draft7Validator = None


SCHEMA_PATH = os.path.join(HERE, "..", "schemas", "recommendation-output.schema.json")

FIT_LABELS = ["strong_fit", "good_fit", "partial_fit", "poor_fit", "not_suitable", "insufficient_evidence"]


def _load_schema(path=None):
    with open(path or SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate_structure(obj, schema_path=None):
    """Return list of structural error strings (empty == OK)."""
    if Draft7Validator is None:
        return ["jsonschema not available"]
    schema = _load_schema(schema_path)
    validator = Draft7Validator(schema)
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in validator.iter_errors(obj)]


def validate_consistency(obj):
    """Return list of consistency-violation strings (empty == OK)."""
    errors = []

    if not isinstance(obj, dict):
        return ["output is not an object"]

    status = obj.get("status")
    primary = obj.get("primary_recommendation")
    evals = obj.get("candidate_evaluations", []) or []
    by_id = {e.get("candidate_id"): e for e in evals}

    # 1. primary must reference an evaluated candidate
    if primary is not None:
        pid = primary.get("candidate_id")
        if pid not in by_id:
            errors.append(f"primary_recommendation.candidate_id '{pid}' not in candidate_evaluations")
        else:
            pe = by_id[pid]
            # hard-constraint violation cannot be primary unless exception
            hcv = [v for v in pe.get("constraint_fit", {}).get("violations", []) if v.get("severity") == "hard"]
            if hcv and pe.get("recommendation_status") == "primary":
                errors.append(f"candidate '{pid}' has hard-constraint violation but is primary "
                              f"(requires exception + human_review_required)")
            # evidence-insufficient cannot be primary
            if pe.get("evidence", {}).get("status") in ("insufficient", "conflict") \
                    and pe.get("recommendation_status") == "primary":
                errors.append(f"candidate '{pid}' has insufficient evidence but is primary")

    # 2. insufficient_evidence candidate must carry uncertainty / missing_evidence
    for e in evals:
        ev_status = e.get("evidence", {}).get("status")
        if ev_status in ("insufficient", "conflict"):
            has_note = any(u.get("candidate_id") == e.get("candidate_id")
                           for u in obj.get("uncertainties", []))
            if not has_note and not e.get("evidence", {}).get("missing_evidence"):
                errors.append(f"candidate '{e.get('candidate_id')}' evidence={ev_status} "
                              f"but no uncertainty/missing_evidence recorded")

    # 3. COMPLETE + primary => non-empty evidence_refs
    if status == "COMPLETE" and primary is not None:
        if not obj.get("evidence_refs"):
            errors.append("status=COMPLETE with primary but evidence_refs is empty")

    # 4. human_review_required must be true when uncertainties exist or no primary
    uncertainties = obj.get("uncertainties", []) or []
    if uncertainties and not obj.get("human_review_required"):
        errors.append("uncertainties present but human_review_required=false")
    if primary is None and status in ("COMPLETE",) and not obj.get("human_review_required"):
        errors.append("no primary recommendation but human_review_required=false")

    # 5. requirement_fit / risk_fit overall labels valid
    for e in evals:
        for key in ("requirement_fit", "risk_fit"):
            label = e.get(key, {}).get("overall")
            if label is not None and label not in FIT_LABELS:
                errors.append(f"candidate '{e.get('candidate_id')}' {key}.overall='{label}' invalid")

    return errors


def validate_output(obj, schema_path=None):
    """Full validation. Returns (ok: bool, errors: list[str])."""
    struct = validate_structure(obj, schema_path)
    cons = validate_consistency(obj)
    errors = struct + cons
    return (len(errors) == 0), errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", help="path to recommendation output JSON")
    ap.add_argument("--schema", default=None, help="path to output schema")
    args = ap.parse_args()
    with open(args.output, encoding="utf-8") as f:
        obj = json.load(f)
    ok, errors = validate_output(obj, args.schema)
    if ok:
        print("OUTPUT_VALID")
        sys.exit(0)
    else:
        print("OUTPUT_INVALID")
        for e in errors:
            print(" -", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
