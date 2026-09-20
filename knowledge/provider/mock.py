"""MockKnowledgeProvider — Stage 14.1.

NOT a new retrieval engine: a thin wrapper that adapts the EXISTING
deterministic engine (knowledge/rag: trigram-BM25 + rules-driven
rerank, built exactly the way the evidence provider builds it today)
to the KnowledgeProvider contract.

Role after Stage 14 (phase14-real-knowledge-plan.md Rev 2):

    Production retrieval → WeKnora (14.2+)
    Tests / offline regression → MockKnowledgeProvider → this engine

The engine itself is UNCHANGED (forbidden to delete/modify) — the mock
only translates its RetrievalResult into the canonical model, which is
byte-compatible downstream via to_dict().
"""
from __future__ import annotations

from typing import Any, Optional

from .base import (KnowledgeFilters, KnowledgeHit, KnowledgeSearchResult)


class MockKnowledgeProvider:
    """Deterministic, offline, network-free provider over the existing
    engine + fixtures KB (or any explicit kb_dir)."""

    name = "mock"

    def __init__(self, engine: Any = None, kb_dir: Optional[str] = None,
                 stamps: Optional[dict] = None):
        self._engine = engine
        self._kb_dir = kb_dir
        # Phase 14.3: optional metadata PROJECTION (the WeKnora upload
        # model): {document_id: {version_id, jurisdiction, ...}} from
        # SourceRegistry.provider_stamps(). Stamping is DATA, never
        # governance — the governance layer re-verifies every hit.
        self._stamps = stamps

    def _build(self):
        # Reuse the EXISTING construction path (rules + importlib of the
        # skill entry point) — do not re-implement engine construction.
        if self._engine is None:
            from knowledge.evidence.provider import build_engine
            self._engine = (build_engine(self._kb_dir)
                            if self._kb_dir else build_engine())
        return self._engine

    def search(self, query: str,
               filters: Optional[KnowledgeFilters] = None,
               top_k: Optional[int] = None) -> KnowledgeSearchResult:
        res = self._build().search(query, top_k=top_k) if top_k \
            else self._build().search(query)
        hits = []
        for ev in res.results:
            stamp = (self._stamps or {}).get(ev.document_id) or {}
            md = dict(ev.metadata or {})
            if stamp.get("jurisdiction"):
                md["jurisdiction"] = stamp["jurisdiction"]
            hits.append(KnowledgeHit(
                chunk_id=ev.chunk_id,
                document_id=ev.document_id,
                content=ev.content,
                document_name=ev.document_name,
                section=ev.section,
                source_type=ev.source_type,
                # registry projection overrides the KB's default ingest
                # level (the WeKnora upload model: metadata projected at
                # upload time; governance re-verifies it anyway)
                source_level=stamp.get("authority_level", ev.source_level),
                version_id=stamp.get("version_id", ""),
                content_hash=KnowledgeHit.hash_content(ev.content),
                score=ev.score,
                retrieval_score=ev.retrieval_score,
                rerank_score=ev.rerank_score,
                final_score=ev.final_score,
                metadata=md,
            ))
        meta = dict(res.retrieval_metadata or {})
        meta["provider"] = self.name
        if filters is not None:
            # PRESERVED for 14.4 governance — not enforced here (14.1
            # must not smuggle effective-date/authority filtering).
            meta["filters"] = filters.to_dict()
        return KnowledgeSearchResult(
            status=res.status, query=res.query,
            normalized_query=res.normalized_query, results=hits,
            conflict=res.conflict, reason=res.reason,
            retrieval_metadata=meta,
        )
