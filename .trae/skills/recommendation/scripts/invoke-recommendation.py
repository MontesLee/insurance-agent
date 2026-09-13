"""CLI / importable entry point for Skill 5 Recommendation.

Usage:
    python invoke-recommendation.py --input input.json [--rules path] [--no-validate]
    echo '<json>' | python invoke-recommendation.py --stdin

The script runs the deterministic engine, validates the output, and prints the structured
recommendation to stdout. Exit code 0 = produced + valid; non-zero = error or invalid output.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from recommendation_engine import generate_recommendation, load_rules  # noqa: E402
from validate_output import validate_output  # noqa: E402


def run(input_dict, rules=None, do_validate=True):
    out = generate_recommendation(input_dict, rules)
    struct_ok, errors = (True, []) if not do_validate else validate_output(out)
    return out, struct_ok, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", help="path to recommendation input JSON")
    ap.add_argument("--stdin", action="store_true", help="read input JSON from stdin")
    ap.add_argument("--rules", default=None, help="path to recommendation.rules.json")
    ap.add_argument("--no-validate", action="store_true", help="skip output validation")
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
    out, ok, errors = run(data, rules, do_validate=not args.no_validate)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    if not ok:
        print("\nOUTPUT_INVALID:", file=sys.stderr)
        for e in errors:
            print(" -", e, file=sys.stderr)
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
