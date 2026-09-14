"""Shared adapter helpers: envelope construction + provenance extraction."""
from __future__ import annotations

import datetime
from typing import Any, Optional

SCHEMA_VERSION = "1.0"


def make_envelope(
    artifact_type: str,
    skill: str,
    legacy_skill: str,
    payload: Any,
    provenance: Optional[list] = None,
    generated_at: Optional[str] = None,
) -> dict:
    """Wrap a legacy skill output into a Canonical Contract artifact."""
    return {
        "artifact_type": artifact_type,
        "skill": skill,
        "legacy_skill": legacy_skill,
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at
        or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "payload": payload,
        "provenance": provenance if provenance is not None else [],
    }


def build_provenance(legacy_output: dict, default_source_id: str) -> list:
    """Build a minimal provenance array from common evidence-reference fields.

    Falls back to a single source entry when no structured refs are present.
    Phase 1 keeps this lightweight; deep traceability is refined in later phases.
    """
    refs = []
    for key in ("evidence_refs", "reasoning_evidence_refs"):
        for r in (legacy_output.get(key) or []):
            if isinstance(r, str):
                refs.append({"source_type": "EVIDENCE_REF", "source_id": r, "confidence": None})
    if not refs:
        return [{"source_type": "SKILL_OUTPUT", "source_id": default_source_id, "confidence": 1.0}]
    return refs
