"""solution -> SolutionPlan canonical artifact.

The skill is canonical-first: its engine (solution_engine.analyze) already emits the
strict SolutionPlan payload defined by contracts/solution-plan.schema.json. This
adapter therefore contains NO business logic — it only wraps the payload into the
Canonical Contract envelope (mirrors the Phase-1 adapter pattern: wrap/relabel, never decide).
"""
from __future__ import annotations

from .base import make_envelope


def to_canonical(payload: dict, generated_at: str = None, provenance: list = None) -> dict:
    return make_envelope(
        artifact_type="solution-plan",
        skill="solution",
        legacy_skill="solution",
        payload=payload,
        provenance=provenance,
        generated_at=generated_at,
    )
