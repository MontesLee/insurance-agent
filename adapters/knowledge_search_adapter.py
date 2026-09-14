"""knowledge-search -> KnowledgeEvidence canonical artifact.

Knowledge Search is the shared Evidence Provider (not a fixed workflow step). This adapter
transforms a KnowledgeSearchOutput into the KnowledgeEvidence contract: each retrieval result
becomes an evidence item. Knowledge Search never carries a final decision here.
"""
from __future__ import annotations

from typing import Any, Optional

from .base import make_envelope


def to_canonical(ks_output: dict, generated_at: str = None) -> dict:
    results = ks_output.get("results") or []
    evidence = []
    for r in results:
        evidence.append(
            {
                "evidence_id": r.get("chunk_id") or r.get("document_id") or "",
                "content": r.get("content", ""),
                "source": r.get("document_name") or r.get("source_type") or "",
                "source_type": r.get("source_type", ""),
                "relevance": r.get("score"),
                "confidence": r.get("score"),
                "provenance": [],
                "conflict": bool(ks_output.get("conflict", False)),
            }
        )
    payload = {
        "status": ks_output.get("status"),
        "query": ks_output.get("query"),
        "evidence": evidence,
        "conflict": bool(ks_output.get("conflict", False)),
    }
    provenance = [{"source_type": "KNOWLEDGE_SEARCH", "source_id": "knowledge-search", "confidence": None}]
    return make_envelope(
        artifact_type="knowledge-evidence",
        skill="knowledge-search",
        legacy_skill="knowledge-search",
        payload=payload,
        provenance=provenance,
        generated_at=generated_at,
    )
