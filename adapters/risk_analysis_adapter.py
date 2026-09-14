"""risk-analysis -> RiskAssessment canonical artifact.

Wraps the legacy RiskAnalysisOutput. The legacy `coverage_assessment` (protected /
unprotected amounts) is preserved as an auxiliary risk-level coverage judgment; it is NOT
the final CoverageGap Artifact. The final gap conclusion is owned by coverage-gap-analysis.
"""
from __future__ import annotations

from .base import make_envelope, build_provenance


def to_canonical(risk_output: dict, generated_at: str = None) -> dict:
    return make_envelope(
        artifact_type="risk-assessment",
        skill="risk-analysis",
        legacy_skill="risk-analysis",
        payload=risk_output,
        provenance=build_provenance(risk_output, default_source_id="risk-analysis"),
        generated_at=generated_at,
    )
