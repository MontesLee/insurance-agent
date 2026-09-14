"""requirement_analysis -> RequirementAnalysis canonical artifact.

Wraps the legacy RequirementAnalysisOutput. The legacy `coverage_gaps` field is preserved
as a requirement-level gap hint; it is NOT the final CoverageGap Artifact (owned by
coverage-gap-analysis in a later phase).
"""
from __future__ import annotations

from .base import make_envelope, build_provenance


def to_canonical(requirement_output: dict, generated_at: str = None) -> dict:
    return make_envelope(
        artifact_type="requirement-analysis",
        skill="requirement-analysis",
        legacy_skill="requirement_analysis",
        payload=requirement_output,
        provenance=build_provenance(requirement_output, default_source_id="requirement_analysis"),
        generated_at=generated_at,
    )
