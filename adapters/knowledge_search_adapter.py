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
    meta = ks_output.get("retrieval_metadata") or {}
    method = meta.get("retrieval_method") or "unknown"
    evidence = []
    for r in results:
        # Provenance must resolve Recommendation -> Evidence -> Document -> Chunk.
        # `evidence_id` alone is NOT enough: a consumer cannot tell a document id from a
        # chunk id, and Step 2 requires the Document/Chunk hop to be independently checkable.
        doc_id = r.get("document_id") or ""
        chunk_id = r.get("chunk_id") or ""
        prov = []
        if doc_id:
            prov.append({"source_type": "DOCUMENT", "source_id": doc_id, "confidence": None})
        if chunk_id:
            prov.append({"source_type": "CHUNK", "source_id": chunk_id, "confidence": None})
        if not prov:
            prov = [{"source_type": "UNRESOLVED", "source_id": "", "confidence": None}]
        evidence.append(
            {
                "evidence_id": chunk_id or doc_id or "",
                "content": r.get("content", ""),
                "source": r.get("document_name") or r.get("source_type") or "",
                "source_type": r.get("source_type", ""),
                "relevance": r.get("score"),
                "confidence": r.get("score"),
                "document_id": doc_id,
                "document_name": r.get("document_name") or "",
                "chunk_id": chunk_id,
                "section": r.get("section") or "",
                "source_level": r.get("source_level") or "",
                "retrieval_method": method,
                "provenance": prov,
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
