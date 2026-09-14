"""ProductRecommendation contract test (Phase 5): real V2 pipeline -> canonical contract.

Phase 1 version wrapped a static legacy output. Phase 5 replaces it with the real chain:

    SolutionPlan + CoverageGapAnalysis + RiskAssessment + RequirementAnalysis
      + KnowledgeEvidence
        -> solution_to_candidates (derive candidates; candidate_solutions is NOT an input)
        -> recommendation_engine
        -> adapters.recommendation_adapter
        -> contracts/product-recommendation.schema.json

This is the machine-checkable proof that the Phase-0 P1 break is closed: the V2 input
carries no `candidate_solutions`, and a valid ProductRecommendation still comes out.
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SCRIPTS = os.path.join(REPO, ".trae", "skills", "recommendation", "scripts")
MANIFEST = os.path.join(REPO, ".trae", "skills", "recommendation", "evals", "cases",
                        "product-recommendation-manifest.json")

from _common import validate  # noqa: E402

LEGACY = {
    "requirement_analysis": ("requirement-analysis", "requirement_analysis"),
    "risk_assessment": ("risk-assessment", "risk-analysis"),
    "coverage_gap_analysis": ("coverage-gap-analysis", "coverage-gap-analysis"),
    "solution_plan": ("solution-plan", "solution"),
    "knowledge_evidence": ("knowledge-evidence", "knowledge-search"),
}


def _envelope(key, payload):
    at, legacy = LEGACY[key]
    return {
        "artifact_type": at,
        "skill": at,
        "legacy_skill": legacy,
        "schema_version": "1.0",
        "generated_at": "2026-09-13T00:00:00+00:00",
        "payload": payload,
        "provenance": [],
    }


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location(
        "invoke_product_recommendation",
        os.path.join(SCRIPTS, "invoke-product-recommendation.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run():
    with open(MANIFEST, encoding="utf-8") as f:
        manifest = json.load(f)
    case = manifest["cases"][0]

    v2_input = {}
    for k, payload in case["input"].items():
        v2_input[k] = _envelope(k, payload) if k in LEGACY else payload

    # The P1 invariant, asserted at the contract level too.
    assert "candidate_solutions" not in v2_input, "V2 input must not carry candidate_solutions"

    ipr = _load_entrypoint()
    artifact, warnings = ipr.run(v2_input)
    if warnings:
        return ("product-recommendation", False, "; ".join(warnings))

    ok, msgs = validate(artifact, "product-recommendation.schema.json")
    extra = "candidates derived from solution_plan"
    return ("product-recommendation", ok, (extra if ok else "; ".join(msgs)))
