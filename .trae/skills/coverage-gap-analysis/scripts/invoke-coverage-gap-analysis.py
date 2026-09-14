"""CLI / importable entry point for Skill 04 Coverage Gap Analysis.

Usage:
    python invoke-coverage-gap-analysis.py --input input.json [--rules path] [--no-validate]
    echo '<json>' | python invoke-coverage-gap-analysis.py --stdin

Input JSON (composite of three Canonical artifacts, each an envelope or raw dict):
    {
      "client_profile":       <ClientProfile>,
      "requirement_analysis": <RequirementAnalysis>,
      "risk_assessment":      <RiskAssessment>
    }

Runs the deterministic engine, wraps the strict CoverageGap payload into the Canonical
Contract envelope, validates, and writes the artifact (incl. payload) to stdout / --output.
Exit 0 = produced + valid; non-zero otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
# scripts -> coverage-gap-analysis -> skills -> .trae -> <repo root>
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from coverage_gap_engine import analyze, load_rules  # noqa: E402
from adapters.base import make_envelope  # noqa: E402

CONTRACT_SCHEMA = os.path.join(REPO_ROOT, "contracts", "coverage-gap-analysis.schema.json")


def build_artifact(input_dict: dict, rules: Optional[dict] = None) -> dict:
    payload = analyze(
        input_dict.get("client_profile"),
        input_dict.get("requirement_analysis"),
        input_dict.get("risk_assessment"),
        rules,
    )
    provenance = [
        {
            "source_type": "RISK",
            "source_id": g["related_risk_ids"][0],
            "confidence": g.get("confidence"),
        }
        for g in payload.get("gaps", [])
    ]
    return make_envelope(
        artifact_type="coverage-gap-analysis",
        skill="coverage-gap-analysis",
        legacy_skill="coverage-gap-analysis",
        payload=payload,
        provenance=provenance,
    )


def validate_output(artifact: dict) -> tuple[bool, list]:
    from jsonschema import Draft7Validator

    with open(CONTRACT_SCHEMA, encoding="utf-8") as f:
        schema = json.load(f)
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema)
    errors = sorted(validator.iter_errors(artifact), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(str(p) for p in e.path) or '<root>'}: {e.message}" for e in errors]
    return (len(msgs) == 0, msgs)


def run(input_dict, rules=None, do_validate=True):
    artifact = build_artifact(input_dict, rules)
    ok, errors = (True, []) if not do_validate else validate_output(artifact)
    return artifact, ok, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="path to composite input JSON")
    ap.add_argument("--stdin", action="store_true", help="read input JSON from stdin")
    ap.add_argument("--rules", default=None, help="path to coverage-mapping.rules.json")
    ap.add_argument("--output", default=None, help="path to write artifact JSON")
    ap.add_argument("--no-validate", action="store_true", help="skip contract validation")
    args = ap.parse_args()

    if args.stdin:
        data = json.load(sys.stdin)
    elif args.input:
        with open(args.input, encoding="utf-8") as f:
            data = json.load(f)
    else:
        print("ERROR: provide --input <file> or --stdin", file=sys.stderr)
        sys.exit(2)

    rules = load_rules(args.rules) if args.rules else load_rules()
    artifact, ok, errors = run(data, rules, do_validate=not args.no_validate)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(artifact, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(artifact, ensure_ascii=False, indent=2))

    if not ok:
        print("\nOUTPUT_INVALID:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
