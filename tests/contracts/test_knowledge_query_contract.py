"""KnowledgeQuery contract test (Phase 4: built by the real Evidence Request builder).

Proves the shared Evidence Provider request shape is produced by a REAL caller: a SolutionPlan
entry from the solution engine is turned into a canonical KnowledgeQuery, and the request
carries (query, domain, purpose) plus traceability back to the requesting artifact.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SOLUTION_SCRIPTS = os.path.join(REPO, ".trae", "skills", "solution", "scripts")
if SOLUTION_SCRIPTS not in sys.path:
    sys.path.insert(0, SOLUTION_SCRIPTS)

from solution_engine import analyze, load_rules  # noqa: E402
from evidence.request import from_solution  # noqa: E402
from _common import validate  # noqa: E402

FIXTURE = os.path.join(
    REPO, ".trae", "skills", "solution", "evals", "cases",
    "fixtures", "unit", "solution", "case-01-multi-gap.json",
)


def run():
    import json

    with open(FIXTURE, encoding="utf-8") as f:
        data = json.load(f)
    payload = analyze(
        data.get("coverage_gap_analysis"),
        data.get("requirement_analysis"),
        data.get("risk_assessment"),
        load_rules(),
    )
    solutions = payload.get("solutions") or []
    if not solutions:
        return ("knowledge-query", False, "solution engine produced no strategies")

    artifact = from_solution(solutions[0])
    ok, msgs = validate(artifact, "knowledge-query.schema.json")
    if not ok:
        return ("knowledge-query", False, "; ".join(msgs))

    p = artifact["payload"]
    fails = []
    # domain must be derived from solution_type (MEDICAL -> medical)
    if p.get("domain") != "medical":
        fails.append(f"domain={p.get('domain')} != expected medical (from MEDICAL strategy)")
    if p.get("purpose") != "SOLUTION_VALIDATION":
        fails.append(f"purpose={p.get('purpose')} != expected SOLUTION_VALIDATION")
    # traceability back to the requesting artifact
    sid = solutions[0].get("solution_id")
    if sid not in (p.get("related_artifact_ids") or []):
        fails.append(f"related_artifact_ids missing requesting solution id {sid}")

    if fails:
        return ("knowledge-query", False, "; ".join(fails))
    return ("knowledge-query", True, f"valid; domain={p.get('domain')} purpose={p.get('purpose')} for {sid}")
