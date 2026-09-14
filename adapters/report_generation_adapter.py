"""report-generation -> InsuranceReport canonical artifact.

Wraps the legacy ReportGenerationResult. Report Generation owns NO business judgment —
it only collects / normalizes / renders / validates upstream artifacts. The adapter preserves
the full structured_report + rendered_report + validation + provenance.
"""
from __future__ import annotations

from .base import make_envelope


def to_canonical(report_output: dict, generated_at: str = None) -> dict:
    provenance = [
        {"source_type": "REPORT_PROVENANCE", "source_id": "report-generation", "confidence": None}
    ]
    return make_envelope(
        artifact_type="insurance-report",
        skill="report-generation",
        legacy_skill="report-generation",
        payload=report_output,
        provenance=provenance,
        generated_at=generated_at,
    )
