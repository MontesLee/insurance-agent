"""Unit tests for solution engine (V2 Phase 3) — architectural invariants.

These are NEGATIVE assertions that enforce the layer boundaries:
  * Solution != Product  -> no insurer / product brand term may appear (all text is
                            template-generated from rules, so this is structural).
  * Solution != Risk     -> no severity / likelihood / residual_risk recomputed or copied.
  * Solution != Gap      -> coverage_direction must equal the rules template composed from
                            the gap's (domain, coverage status); nothing may be invented.
  * Solution is traceable-> every solution references a gap_id.

Writes results to evals/cases/_solution_unit_log.txt and exits non-zero on failure.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
CASES_DIR = os.path.join(SKILL_DIR, "evals", "cases")
LOG_PATH = os.path.join(CASES_DIR, "_solution_unit_log.txt")

sys.path.insert(0, HERE)
from solution_engine import analyze, load_rules, extract_payload  # noqa: E402

# Risk-layer fields that MUST NOT appear in a SolutionPlan artifact.
FORBIDDEN_KEYS = {"severity", "likelihood", "residual_risk", "risk_priority", "gap_level"}


def _walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_strings(k)
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _walk_forbidden_keys(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                hits.append(f"{path}.{k}")
            hits.extend(_walk_forbidden_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_walk_forbidden_keys(v, f"{path}[{i}]"))
    return hits


def run():
    rules = load_rules()
    allowed_types = set(rules["domain_to_solution_type"].values()) | {"GENERAL"}
    prefixes = rules["coverage_status_prefix"]
    bodies = rules["domain_coverage_direction"]
    forbidden_terms = rules["forbidden_terms"]

    with open(os.path.join(CASES_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    lines = []
    all_ok = True

    for case in manifest["cases"]:
        with open(os.path.join(CASES_DIR, case["fixture"]), encoding="utf-8") as f:
            data = json.load(f)
        payload = analyze(
            data.get("coverage_gap_analysis"),
            data.get("requirement_analysis"),
            data.get("risk_assessment"),
            rules,
        )
        gap_art = extract_payload(data.get("coverage_gap_analysis")) or {}
        gaps_by_id = {g.get("gap_id"): g for g in (gap_art.get("gaps") or [])}

        fails = []

        # Invariant 1: no insurer / product brand term anywhere.
        for s in _walk_strings(payload):
            for term in forbidden_terms:
                if term in s:
                    fails.append(f"forbidden brand term '{term}' in text: {s}")

        # Invariant 2: no risk-layer / gap-layer key leakage.
        hits = _walk_forbidden_keys(payload)
        if hits:
            fails.append("forbidden risk/gap-layer keys present: " + ", ".join(hits))

        solutions = payload.get("solutions", [])
        for sol in solutions:
            sid = sol.get("solution_id")

            # Invariant 3: strategy class must come from the rules allowlist.
            if sol.get("solution_type") not in allowed_types:
                fails.append(f"{sid} solution_type '{sol.get('solution_type')}' not in allowed set")

            # Invariant 4: every solution traces back to a gap.
            if not sol.get("related_gap_ids"):
                fails.append(f"{sid} has no related_gap_ids")

            # Invariant 5: coverage_direction == rules template (nothing invented).
            gid = (sol.get("related_gap_ids") or [None])[0]
            gap = gaps_by_id.get(gid)
            if gap:
                domain = gap.get("domain", "general")
                cov_status = (gap.get("current_coverage") or {}).get("status", "UNKNOWN")
                expected = prefixes.get(cov_status, "") + bodies.get(domain, bodies["general"])
                if sol.get("coverage_direction") != expected:
                    fails.append(
                        f"{sid} coverage_direction != rules template (got '{sol.get('coverage_direction')}', expected '{expected}')"
                    )

            # Invariant 6: priority within the canonical enum.
            if sol.get("priority") not in ("P0", "P1", "P2", "P3"):
                fails.append(f"{sid} priority out of enum: {sol.get('priority')}")

            # Invariant 7: confidence within [0,1].
            c = sol.get("confidence")
            if c is not None and not (0 <= c <= 1):
                fails.append(f"{sid} confidence out of range: {c}")

        # Invariant 8: top-level trio is derived from solutions[0] (single source of truth).
        if solutions:
            p = solutions[0]
            for field in ("objective", "coverage_direction", "priority", "solution_type"):
                if payload.get(field) != p.get(field):
                    fails.append(f"top-level {field} != solutions[0].{field}")

        # Invariant 9: empty solution set still satisfies contract minLength (>=1 char).
        if not solutions:
            for field in ("objective", "coverage_direction", "priority"):
                if not (payload.get(field) or "").strip():
                    fails.append(f"empty {field} when no solutions (violates contract minLength)")

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
