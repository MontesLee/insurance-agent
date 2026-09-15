"""Report Generation V2 dataset runner.

Executes every case in evals/cases/v2-dataset-manifest.json:
  1. validates the output against schemas/report-output.schema.json
  2. evaluates the per-case `expect` block

Case list is the single source of truth (evals/cases/v2-dataset-manifest.json).
Exit code 0 = all green.
"""
from __future__ import annotations

import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
# skills -> .trae -> insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(SKILL_DIR)))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from jsonschema import Draft7Validator  # noqa: E402
from report_generation_engine import generate_report, load_rules  # noqa: E402

MANIFEST = os.path.join(SKILL_DIR, "evals", "cases", "v2-dataset-manifest.json")
OUTPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "report-output.schema.json")
LOG = os.path.join(REPO_ROOT, "tests", "contracts", "_report_v2_dataset_log.txt")


def check_case(case, rules, schema):
    fails = []
    out = generate_report(case["input"], rules)

    for err in Draft7Validator(schema).iter_errors(out):
        fails.append("schema: " + err.message)

    exp = case.get("expect", {})
    sr = out.get("structured_report", {})
    rendered = out.get("rendered_report", "")
    meta = out.get("metadata", {})
    warnings = meta.get("warnings", [])

    if "status" in exp and out.get("status") != exp["status"]:
        fails.append("status: got %r want %r" % (out.get("status"), exp["status"]))

    if "coverage_gap_derivation" in exp:
        got = sr.get("coverage_gap_derivation")
        if got != exp["coverage_gap_derivation"]:
            fails.append("coverage_gap_derivation: got %r want %r" % (got, exp["coverage_gap_derivation"]))

    if "coverage_gaps_len" in exp:
        got = len(sr.get("coverage_gaps", []))
        if got != exp["coverage_gaps_len"]:
            fails.append("coverage_gaps_len: got %d want %d" % (got, exp["coverage_gaps_len"]))

    if exp.get("coverage_gaps_all_canonical"):
        bad = [g for g in sr.get("coverage_gaps", []) if g.get("derivation") != "canonical"]
        if bad:
            fails.append("coverage_gaps_all_canonical: %d non-canonical entries leaked" % len(bad))

    if exp.get("coverage_gaps_all_derived"):
        bad = [g for g in sr.get("coverage_gaps", []) if g.get("derivation") != "derived"]
        if bad:
            fails.append("coverage_gaps_all_derived: %d entries not tagged derived" % len(bad))

    if exp.get("solution_strategies_nonempty") and not sr.get("solution_strategies"):
        fails.append("solution_strategies: empty")

    if exp.get("evidence_summary_nonempty") and not sr.get("evidence_summary"):
        fails.append("evidence_summary: empty")

    if exp.get("evidence_has_conflict"):
        if not any(e.get("conflict") for e in sr.get("evidence_summary", [])):
            fails.append("evidence_summary: no entry carries conflict=True")

    if exp.get("provenance_nonempty") and not out.get("provenance"):
        fails.append("provenance: empty")

    for w in exp.get("metadata_warnings_contains", []):
        if not any(w in x for x in warnings):
            fails.append("metadata_warnings missing: %r (have %r)" % (w, warnings))

    if exp.get("metadata_conflicts_nonempty") and not meta.get("conflicts"):
        fails.append("metadata_conflicts: empty")

    for s in exp.get("rendered_forbids", []):
        if s in rendered:
            fails.append("rendered contains forbidden: %r" % s)

    for s in exp.get("rendered_contains", []):
        if s not in rendered:
            fails.append("rendered missing: %r" % s)

    if out.get("validation", {}).get("errors"):
        fails.extend("validation: " + e for e in out["validation"]["errors"])

    return out, fails


def main():
    rules = load_rules()
    schema = json.load(io.open(OUTPUT_SCHEMA, encoding="utf-8"))
    manifest = json.load(io.open(MANIFEST, encoding="utf-8"))

    lines = []
    all_ok = True
    for case in manifest["cases"]:
        out, fails = check_case(case, rules, schema)
        if fails:
            all_ok = False
            lines.append("[FAIL] %s" % case["name"])
            for f in fails:
                lines.append("       - %s" % f)
        else:
            lines.append("[PASS] %s" % case["name"])
    lines.append("")
    lines.append("REPORT V2 DATASET RESULT: %s" % ("ALL GREEN" if all_ok else "FAILURES PRESENT"))

    text = "\n".join(lines)
    print(text)
    io.open(LOG, "w", encoding="utf-8").write(text)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
