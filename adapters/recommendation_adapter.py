"""recommendation -> ProductRecommendation canonical artifact.

Wraps the legacy RecommendationOutput into the ProductRecommendation contract. The legacy
output shape is preserved. NOTE (Phase 5): the V2 input contract will change so this skill
consumes RequirementAnalysis + RiskAssessment + CoverageGapAnalysis + SolutionPlan +
KnowledgeEvidence instead of the phantom `candidate_solutions`. This adapter only relabels
the artifact; it does not alter the recommendation logic.
"""
from __future__ import annotations

from .base import make_envelope, build_provenance


def to_canonical(recommendation_output: dict, generated_at: str = None) -> dict:
    return make_envelope(
        artifact_type="product-recommendation",
        skill="product-recommendation",
        legacy_skill="recommendation",
        payload=recommendation_output,
        provenance=build_provenance(recommendation_output, default_source_id="recommendation"),
        generated_at=generated_at,
    )
