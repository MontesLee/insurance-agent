"""Unit tests for coverage-gap-analysis engine (V2 Phase 2).

Architectural invariants that must hold for ANY output (the "Risk != Coverage Gap"
boundary). These are negative assertions: the engine must NOT recompute or copy
risk-layer quantities (severity / likelihood / residual_risk / priority) into the
CoverageGap artifact.

Writes results to tests/contracts/_coverage_gap_unit_log.txt and exits non-zero on failure.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CASES_DIR = os.path.join(SKILL_DIR, "evals", "cases")
LOG_PATH = os.path.join(SKILL_DIR, "evals", "cases", "_unit_log.txt")

sys.path.insert(0, HERE)
from coverage_gap_engine import analyze, load_rules  # noqa: E402

# Risk-layer fields that MUST NOT appear in a CoverageGap artifact.
FORBIDDEN_KEYS = {"severity", "likelihood", "residual_risk", "risk_priority"}


def _walk_forbidden(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                hits.append(f"{path}.{k}")
            hits.extend(_walk_forbidden(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_walk_forbidden(v, f"{path}[{i}]"))
    return hits


def run():
    rules = load_rules()
    manifest_path = os.path.join(CASES_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    lines = []
    all_ok = True

    for case in manifest["cases"]:
        fixture_path = os.path.join(CASES_DIR, case["fixture"])
        with open(fixture_path, encoding="utf-8") as f:
            data = json.load(f)
        payload = analyze(data.get("client_profile"), data.get("requirement_analysis"), data.get("risk_assessment"), rules)

        fails = []

        # Invariant 1: no risk-layer fields leak into the artifact.
        hits = _walk_forbidden(payload)
        if hits:
            fails.append("forbidden risk-layer keys present: " + ", ".join(hits))

        # Invariant 2: every gap references at least one risk.
        for g in payload.get("gaps", []):
            if not g.get("related_risk_ids"):
                fails.append(f"{g.get('gap_id')} has no related_risk_ids")

        # Invariant 3: confidence within [0,1].
        for g in payload.get("gaps", []):
            c = g.get("confidence")
            if c is not None and not (0 <= c <= 1):
                fails.append(f"{g.get('gap_id')} confidence out of range: {c}")

        # Invariant 4: SUFFICIENT coverage must never produce a gap.
        for g in payload.get("gaps", []):
            if g["current_coverage"]["status"] == "SUFFICIENT":
                fails.append(f"{g.get('gap_id')} produced a gap for SUFFICIENT coverage")

        tag = "PASS" if not fails else "FAIL"
        if fails:
            all_ok = False
        lines.append(f"[{tag}] {case['case_id']}")
        for d in fails:
            lines.append(f"    - {d}")

    lines.append("")
    lines.append("RESULT: " + ("ALL GREEN" if all_ok else "FAILURES PRESENT"))
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run())
