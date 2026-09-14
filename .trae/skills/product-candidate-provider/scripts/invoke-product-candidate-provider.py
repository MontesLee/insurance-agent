"""Step 2 entrypoint: product-candidate-provider.

Input  : {client_profile, coverage_gap_analysis, solution_plan, knowledge_evidence,
          requested_product_ids?}
Output : {candidates[], admissible_candidate_ids[], rejected[], ...}

This skill generates candidates. It does NOT recommend -- ranking and choosing is
`recommendation`'s job (Step 2 spec section 13).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from product_candidate_engine import (  # noqa: E402
    build_candidates, load_catalog, load_rules, lookup_product, run,
)

INPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "input.schema.json")
OUTPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "output.schema.json")
CATALOG_SCHEMA = os.path.join(SKILL_DIR, "schemas", "product-catalog.schema.json")


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


def resolve(name_or_id, rules=None, catalog=None):
    """Resolve a product id/name. Returns (status, product). Used by Negative Test 5."""
    rules = rules or load_rules()
    catalog = catalog or load_catalog(rules=rules)
    return lookup_product(catalog, name_or_id)


def main():
    ap = argparse.ArgumentParser(description="product-candidate-provider")
    ap.add_argument("--input", help="input JSON")
    ap.add_argument("--output", help="where to write the output JSON")
    ap.add_argument("--rules", help="override rules JSON")
    ap.add_argument("--catalog", help="override catalog JSON")
    ap.add_argument("--validate-catalog", action="store_true",
                    help="validate the product catalog against its schema and exit")
    ap.add_argument("--lookup", help="resolve a product id or name and exit")
    a = ap.parse_args()

    rules = load_rules(a.rules) if a.rules else load_rules()
    catalog = load_catalog(a.catalog, rules) if a.catalog else load_catalog(rules=rules)

    if a.validate_catalog:
        errs = _validate(catalog, CATALOG_SCHEMA, "catalog")
        print("CATALOG: %s" % ("VALID" if not errs else "INVALID"))
        for e in errs:
            print("  " + e)
        sys.exit(0 if not errs else 1)

    if a.lookup:
        status, product = resolve(a.lookup, rules, catalog)
        print(json.dumps({"query": a.lookup, "status": status,
                          "product": product}, ensure_ascii=False, indent=2))
        sys.exit(0 if status == "FOUND" else 1)

    if not a.input:
        ap.error("--input is required (or use --validate-catalog / --lookup)")

    data = _load(a.input)
    errs = _validate(data, INPUT_SCHEMA, "input")
    if errs:
        print(json.dumps({"_validation_errors": errs}, ensure_ascii=False, indent=2))
        sys.exit(1)

    out, ok, errors = run(data, rules, catalog)
    warn = _validate(out, OUTPUT_SCHEMA, "output")
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if a.output:
        with open(a.output, "w", encoding="utf-8") as f:
            f.write(text)
        print("written: %s" % a.output)
    else:
        print(text)
    for w in warn:
        print("[warn] %s" % w, file=sys.stderr)
    sys.exit(0 if (ok and not warn) else 1)


if __name__ == "__main__":
    main()
