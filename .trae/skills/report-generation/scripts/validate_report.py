"""Deterministic output validator for Skill 6 Report Generation.

Two layers (mirrors AGENTS.md §5 "code does deterministic validation" + Skill 5):
  1. Structural: jsonschema Draft7 validation of ReportGenerationResult.
  2. Consistency: business invariants a schema cannot express, e.g.
     - output.status must be a valid enum
     - structured_report must carry all 8 fixed sections
     - status=success requires non-empty provenance
     - validation.passed must be true and validation.errors must be empty

Run: python validate_report.py <output.json> [--schema <path>]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from jsonschema import Draft7Validator
except ImportError:  # pragma: no cover
    Draft7Validator = None

SCHEMA_PATH = os.path.join(HERE, "..", "schemas", "report-output.schema.json")

SECTIONS = ["client_profile", "financial_profile", "risk_exposure", "coverage_gaps",
            "requirement_priorities", "recommended_directions", "information_gaps", "next_actions"]


def _money_tokens(text, pattern):
    out = []
    for m in re.findall(pattern, text):
        out.append(m if isinstance(m, str) else "".join(m))
    return out


def _collect_leaf_strings(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_leaf_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_leaf_strings(v, acc)
    elif isinstance(obj, str):
        acc.append(obj)


def _load_schema(path=None):
    with open(path or SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate_structure(obj, schema_path=None):
    """Return list of structural error strings (empty == OK)."""
    if Draft7Validator is None:
        return ["jsonschema not available"]
    validator = Draft7Validator(_load_schema(schema_path))
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in validator.iter_errors(obj)]


def validate_consistency(obj):
    errors = []
    if not isinstance(obj, dict):
        return ["output is not an object"]
    status = obj.get("status")
    if status not in ("success", "INSUFFICIENT_INPUT"):
        errors.append(f"status '{status}' invalid")
    sr = obj.get("structured_report") or {}
    for s in SECTIONS:
        if s not in sr:
            errors.append(f"structured_report missing section '{s}'")
    if status == "success" and not obj.get("provenance"):
        errors.append("status=success but provenance is empty")
    v = obj.get("validation") or {}
    if v.get("passed") is not True:
        errors.append("validation.passed is not true")
    if v.get("errors"):
        errors.append(f"validation.errors not empty: {v['errors']}")
    return errors


def validate_output(obj, schema_path=None):
    struct = validate_structure(obj, schema_path)
    cons = validate_consistency(obj)
    errors = struct + cons
    return (len(errors) == 0), errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", help="path to report-generation output JSON")
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
