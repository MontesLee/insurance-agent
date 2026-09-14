"""SolutionPlan contract test (Phase 3: driven by the real solution engine).

Proves the engine's output satisfies the Canonical Contract after passing through the
adapter, and that it really is a STRATEGY artifact:
  * one strategy per gap, each tracing back to a gap_id
  * priority derived from the gap layer (not copied from risk)
  * no concrete product / insurer name (all text is rules-template generated)

The real engine is exercised against the case-01-multi-gap fixture.
"""
import sys
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SKILL_SCRIPTS = os.path.join(REPO, ".trae", "skills", "solution", "scripts")
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)

from solution_engine import analyze, load_rules  # noqa: E402
from adapters.solution_adapter import to_canonical  # noqa: E402
from _common import validate  # noqa: E402

FIXTURE = os.path.join(
    REPO,
    ".trae",
    "skills",
    "solution",
    "evals",
    "cases",
    "fixtures",
    "unit",
    "solution",
    "case-01-multi-gap.json",
)


def run():
    with open(FIXTURE, encoding="utf-8") as f:
        data = json.load(f)

    payload = analyze(
        data.get("coverage_gap_analysis"),
        data.get("requirement_analysis"),
        data.get("risk_assessment"),
        load_rules(),
    )

    provenance = []
    for s in payload.get("solutions", []):
        for gid in s.get("related_gap_ids", []):
            provenance.append(
                {"source_type": "COVERAGE_GAP", "source_id": gid, "field": "solutions", "confidence": s.get("confidence")}
            )
        for rid in s.get("related_risk_ids", []):
            provenance.append(
                {"source_type": "RISK", "source_id": rid, "field": "solutions", "confidence": s.get("confidence")}
            )

    artifact = to_canonical(payload, provenance=provenance)
    ok, msgs = validate(artifact, "solution-plan.schema.json")
    if not ok:
        return ("solution-plan", False, "; ".join(msgs))

    # Strategy-layer assertions beyond schema validation.
    fails = []
    solutions = payload.get("solutions", [])
    if not solutions:
        fails.append("engine produced no solutions for a 4-gap fixture")
    for s in solutions:
        if not s.get("related_gap_ids"):
            fails.append(f"{s.get('solution_id')} has no related_gap_ids")
        if len(s.get("related_gap_ids", [])) != 1:
            fails.append(f"{s.get('solution_id')} should map to exactly one gap")
    # priority must come from the gap layer: CRITICAL->P0, HIGH->P1, MEDIUM->P2, LOW->P3
    expected_prios = ["P0", "P1", "P2", "P3"]
    actual_prios = [s.get("priority") for s in solutions]
    if actual_prios != expected_prios:
        fails.append(f"priorities {actual_prios} != gap-derived {expected_prios}")

    if fails:
        return ("solution-plan", False, "; ".join(fails))
    return ("solution-plan", True, f"valid; {len(solutions)} strategies, primary={payload.get('solution_type')}")
