"""WeKnoraKnowledgeProvider — Stage 14.1 adapter SEAM only.

No HTTP, no MCP, no Docker, no network probing, no auto-start: the
provider talks to an INJECTED `transport` callable. In 14.1 that
callable exists only inside contract tests (a fake WeKnora response);
the real transport arrives in the 14.2 POC, where the documented
response contract below is validated against the live service.

STRUCTURAL ASK-ISOLATION (plan Rev 2 §5): this class exposes ONLY the
retrieval surface. WeKnora also offers an LLM "Ask"/ReAct answer mode —
that path is FORBIDDEN as an evidence source. There is no
ask/chat/agent/react/answer method here, and the adapter maps only
search results. The legal direction is:

    WeKnora retrieval → raw results → canonical KnowledgeSearchResult
    → Insurance Governance (14.4) → Evidence → Agent reasoning

Documented raw-response contract (ASSUMPTION to verify in 14.2 POC):

    {
      "results": [
        {
          "content":   str, non-empty          # the retrieved text
          "score":     number                   # provider relevance
          "metadata": {
            "document_id":   str, non-empty     # our registry document id
            "chunk_id":      str, non-empty     # stable chunk id
            "document_name": str, optional
            "section":       str, optional
            "source_type":   str, optional
            "source_level":  str, optional      # projection of OUR registry
            "version_id":    str, optional      # 14.3 version registry
          }
        }, ...
      ],
      "total": int, optional
    }

Anything else raises ProviderResponseInvalid — a malformed backend
response never becomes evidence.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from .base import (KnowledgeFilters, KnowledgeHit, KnowledgeSearchResult,
                   ProviderResponseInvalid, ProviderUnavailable)

# Canonical retrieval-method vocabulary (knowledge-evidence contract
# enum: sparse_rrf | hybrid_rrf | unknown). WeKnora's hybrid retrieval
# maps to hybrid_rrf; provider identity lives in
# retrieval_metadata.provider, never in the shared enum.
_RETRIEVAL_METHOD = "hybrid_rrf"


def map_weknora_response(raw: Any, query: str,
                         filters: Optional[KnowledgeFilters] = None
                         ) -> KnowledgeSearchResult:
    """Pure mapping: fake-or-real WeKnora response → canonical result.
    Strict validation, fail-closed on shape violations."""
    if not isinstance(raw, dict):
        raise ProviderResponseInvalid(
            "WeKnora response is not a JSON object")
    results = raw.get("results")
    if not isinstance(results, list):
        raise ProviderResponseInvalid(
            "WeKnora response missing 'results' list")
    hits = []
    for i, r in enumerate(results):
        if not isinstance(r, dict):
            raise ProviderResponseInvalid("result[%d] not an object" % i)
        content = r.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseInvalid(
                "result[%d] has no content" % i)
        score = r.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool):
            raise ProviderResponseInvalid(
                "result[%d] score is not numeric" % i)
        md = r.get("metadata") or {}
        if not isinstance(md, dict):
            raise ProviderResponseInvalid(
                "result[%d] metadata is not an object" % i)
        doc_id = md.get("document_id")
        chunk_id = md.get("chunk_id")
        if not isinstance(doc_id, str) or not doc_id:
            raise ProviderResponseInvalid(
                "result[%d] missing metadata.document_id" % i)
        if not isinstance(chunk_id, str) or not chunk_id:
            raise ProviderResponseInvalid(
                "result[%d] missing metadata.chunk_id" % i)
        hits.append(KnowledgeHit(
            chunk_id=chunk_id,
            document_id=doc_id,
            content=content,
            document_name=str(md.get("document_name") or ""),
            section=str(md.get("section") or ""),
            source_type=str(md.get("source_type") or ""),
            source_level=str(md.get("source_level") or ""),
            version_id=str(md.get("version_id") or ""),
            content_hash=KnowledgeHit.hash_content(content),
            score=float(score),
            final_score=float(score),
            metadata={"provider_raw_keys": sorted(r.keys())},
        ))
    status = "success" if hits else "insufficient_evidence"
    meta = {
        "provider": "weknora",
        "retrieval_method": _RETRIEVAL_METHOD,
        "candidate_count": len(results),
        "returned_count": len(hits),
    }
    if filters is not None:
        meta["filters"] = filters.to_dict()   # preserved for 14.4
    return KnowledgeSearchResult(
        status=status, query=query, results=hits,
        conflict=bool(raw.get("conflict", False)),
        reason=str(raw.get("reason") or ""),
        retrieval_metadata=meta,
    )


class WeKnoraKnowledgeProvider:
    """Adapter seam. `transport` is a callable (payload: dict) -> dict
    supplied by composition (14.2 wires the real client). Without a
    transport every search FAILS CLOSED — there is no fallback to the
    mock provider and no fabricated empty success."""

    name = "weknora"

    def __init__(self, transport: Optional[Callable[[dict], dict]] = None,
                 kb_id: Optional[str] = None):
        self._transport = transport
        self.kb_id = kb_id

    def search(self, query: str,
               filters: Optional[KnowledgeFilters] = None,
               top_k: Optional[int] = None) -> KnowledgeSearchResult:
        if self._transport is None:
            raise ProviderUnavailable(
                "WeKnora transport not configured — failing closed "
                "(no silent fallback to another provider)")
        payload = {
            "query": query,
            "top_k": top_k or 10,
            "kb_id": self.kb_id,
        }
        if filters is not None:
            payload["filters"] = filters.to_dict()
        raw = self._transport(payload)
        return map_weknora_response(raw, query, filters)
