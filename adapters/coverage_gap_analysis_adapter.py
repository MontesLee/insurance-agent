"""coverage-gap-analysis -> CoverageGapAnalysis canonical artifact.

The skill is canonical-first: its engine (coverage_gap_engine.analyze) already emits the
strict CoverageGap payload defined by contracts/coverage-gap-analysis.schema.json. This
adapter therefore contains NO business logic — it only wraps the payload into the Canonical
Contract envelope (mirrors the Phase-1 adapter pattern: wrap/relabel, never decide).
"""
from __future__ import annotations

from .base import make_envelope


def to_canonical(payload: dict, generated_at: str = None, provenance: list = None) -> dict:
    return make_envelope(
        artifact_type="coverage-gap-analysis",
        skill="coverage-gap-analysis",
        legacy_skill="coverage-gap-analysis",
        payload=payload,
        provenance=provenance,
        generated_at=generated_at,
    )
