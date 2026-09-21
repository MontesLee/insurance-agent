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


# ============================================================================ #
# LIVE implementation — Phase 18 (real WeKnora v0.8.0 backend)
# ============================================================================ #
# Verified real contract (environment preparation, 2026-09-20):
#   POST {base}/api/v1/knowledge-search          PURE retrieval ("不使用
#   LLM总结"; the LLM answer path is NEVER used)
#   headers: X-API-Key: <retrieve-capability key>   (or JWT Bearer)
#   body:    {"query": str, "knowledge_base_id": str}
#   resp:    {"success": bool, "data": [ {hit} ]}
#   hit:     id(chunk) knowledge_id(document) knowledge_filename
#            knowledge_base_id content matched_content match_type
#            score(float) chunk_type chunk_index seq metadata ...
# WeKnora provides NO governance fields (version/effective/authority/
# license/jurisdiction) — the Agent Governance Registry supplies them via
# the stamps PROJECTION (same mechanism as the mock provider); the
# provider never invents or heuristically derives them.
import json as _json
import os as _os
import urllib.error as _urlerr
import urllib.request as _urlreq

LIVE_SEARCH_PATH = "/api/v1/knowledge-search"
_LIVE_RULES_DIR = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(
        __file__)))), ".trae", "skills", "knowledge-search",
    "resources", "config")


def _load_live_rules():
    """The SAME externalized retrieval/ranking rules the deterministic
    engine uses (retrieval.rules.json + ranking.rules.json)."""
    rules = {}
    for fn in ("retrieval.rules.json", "ranking.rules.json"):
        p = _os.path.join(_LIVE_RULES_DIR, fn)
        if _os.path.isfile(p):
            with open(p, encoding="utf-8-sig") as f:
                rules.update(_json.load(f))
    return rules


class WeKnoraLiveTransport:
    """Real HTTP transport for the pure-search endpoint. Fail-closed at
    the HTTP boundary: connection/timeout -> ProviderUnavailable;
    HTTP 4xx/5xx, non-JSON, or success!=true -> ProviderResponseInvalid."""

    def __init__(self, base_url, api_key, timeout=15.0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def __call__(self, payload: dict) -> dict:
        body = _json.dumps({"query": payload.get("query", ""),
                            "knowledge_base_id": payload.get("kb_id", "")},
                           ensure_ascii=False).encode("utf-8")
        req = _urlreq.Request(
            self.base_url + LIVE_SEARCH_PATH, data=body,
            headers={"Content-Type": "application/json",
                     "X-API-Key": self.api_key}, method="POST")
        try:
            with _urlreq.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except _urlerr.HTTPError as e:
            raise ProviderResponseInvalid(
                "WeKnora HTTP %d at %s" % (e.code, LIVE_SEARCH_PATH))
        except (_urlerr.URLError, TimeoutError, OSError) as e:
            raise ProviderUnavailable(
                "WeKnora unreachable: %s" % str(e)[:120])
        try:
            doc = _json.loads(raw)
        except _json.JSONDecodeError:
            raise ProviderResponseInvalid(
                "WeKnora returned non-JSON body (%d chars)" % len(raw))
        if not isinstance(doc, dict) or doc.get("success") is not True:
            reason = (doc.get("error") or {}).get("message", "") \
                if isinstance(doc, dict) else ""
            raise ProviderResponseInvalid(
                "WeKnora success!=true: %s" % str(reason)[:120])
        return doc


def map_live_response(raw, query, stamps=None):
    """Real response -> candidate KnowledgeHits (pre-scoring). Document
    identity = knowledge_filename STEM, which maps 1:1 onto the Agent
    registry document_id for both the fixtures corpus and the Phase-14.7
    pilot corpus. Governance fields come from the registry stamps."""
    stamps = stamps or {}
    hits = raw.get("data")
    if not isinstance(hits, list):
        raise ProviderResponseInvalid("WeKnora data is not a list")
    out = []
    for i, h in enumerate(hits):
        if not isinstance(h, dict):
            raise ProviderResponseInvalid("live hit[%d] not an object" % i)
        content = h.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderResponseInvalid(
                "live hit[%d] has no content" % i)
        cid = h.get("id")
        if not isinstance(cid, str) or not cid:
            raise ProviderResponseInvalid(
                "live hit[%d] missing chunk id" % i)
        fname = h.get("knowledge_filename") or ""
        doc_id = _os.path.splitext(_os.path.basename(fname))[0] \
            or str(h.get("knowledge_id") or "")
        if not doc_id:
            raise ProviderResponseInvalid(
                "live hit[%d] missing document identity" % i)
        stamp = stamps.get(doc_id) or {}
        try:
            score = float(h.get("score") or 0.0)
        except (TypeError, ValueError):
            raise ProviderResponseInvalid(
                "live hit[%d] score not numeric" % i)
        out.append(KnowledgeHit(
            chunk_id=cid, document_id=doc_id, content=content,
            document_name=doc_id,
            section=str(h.get("chunk_type") or ""),
            source_type="weknora",
            source_level=stamp.get("authority_level",
                                   h.get("source_level") or ""),
            version_id=stamp.get("version_id", ""),
            content_hash=KnowledgeHit.hash_content(content),
            score=score,
            metadata={"match_type": h.get("match_type"),
                      "knowledge_id": h.get("knowledge_id"),
                      "knowledge_base_id": h.get("knowledge_base_id"),
                      "weknora_score": score},
        ))
    return out


from knowledge.rag.models import Candidate  # noqa: E402 — scoring pool


class _ScoringChunk:
    """Reranker-facing view of a live hit: the deterministic reranker
    reads .product_type/.topic/.source_level/.content — live hits carry
    the same data under their own names; missing routing fields default
    to empty (no fabricated domain signal)."""

    def __init__(self, hit):
        self._hit = hit
        self.content = hit.content
        self.source_level = hit.source_level
        self.product_type = ""
        self.topic = ""

    def __getattr__(self, name):
        return getattr(self._hit, name)


class WeKnoraLiveProvider:
    """Live WeKnora retrieval under the EXISTING agent retrieval policy.

    Pipeline (all existing components, unchanged rules): WeKnora
    over-retrieval -> candidate hits -> the agent's SparseRetriever +
    DefaultReranker + min_relevance/partial thresholds from the SAME
    externalized rules file the deterministic engine uses -> statuses.
    Abstention therefore behaves exactly like the mock engine: a
    candidate with zero trigram overlap scores 0 and is dropped ->
    insufficient_evidence (agent-side abstention)."""

    name = "weknora"

    def __init__(self, transport, kb_id, stamps=None, rules=None):
        self._transport = transport
        self._kb_id = kb_id
        self._stamps = stamps or {}
        self._rules = rules if rules is not None else _load_live_rules()

    def search(self, query, filters=None, top_k=None):
        from knowledge.rag.engine import SparseRetriever, DefaultReranker
        from knowledge.provider.base import KnowledgeSearchResult
        raw = self._transport({"query": query, "kb_id": self._kb_id,
                               "top_k": top_k or 20})
        candidates = map_live_response(raw, query, self._stamps)
        meta = {"provider": self.name, "retrieval_method": "sparse_rrf",
                "backend": "weknora", "backend_hits": len(candidates)}
        if not candidates:
            return KnowledgeSearchResult(
                status="insufficient_evidence", query=query, results=[],
                conflict=False, reason="WeKnora returned no hits",
                retrieval_metadata=dict(meta, returned_count=0))
        # the agent's deterministic scoring policy over the backend pool
        shims = [_ScoringChunk(c) for c in candidates]
        sparse = SparseRetriever()
        sparse.index(shims)
        scored = sparse.search(query, top_k=len(shims))
        by_id = {c.chunk_id: c for c in candidates}
        cands = [Candidate(shim, sparse_score=s) for shim, s in scored]
        reranker = DefaultReranker(self._rules)
        reranked = reranker.rerank(query, cands)
        top_k = top_k or self._rules.get("final_k", 5)
        min_rel = self._rules.get("min_relevance_score", 0.55)
        partial = self._rules.get("partial_threshold", 0.70)
        passed = [c for c in reranked if c.final_score >= min_rel]
        if not passed:
            status, reason = "insufficient_evidence", \
                "No sufficiently relevant knowledge was retrieved."
        elif passed[0].final_score < partial:
            status, reason = "partial_evidence", \
                "Retrieved some relevant knowledge but confidence below " \
                "full-evidence threshold."
        else:
            status, reason = "success", ""
        evs = passed[:top_k]
        return KnowledgeSearchResult(
            status=status, query=query,
            results=[by_id.get(c.chunk.chunk_id, c.chunk._hit)
                     for c in evs],
            conflict=False, reason=reason,
            retrieval_metadata=dict(
                meta, candidate_count=len(reranked),
                returned_count=len(evs)))
