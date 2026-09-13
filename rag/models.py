"""Data models for Knowledge Search (V0.1, pure stdlib, no numpy)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict


@dataclass
class Chunk:
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    section: str = ""
    source_type: str = "internal"      # official/regulation/product_document/internal/faq/case
    source_level: str = "B"            # S/A/B/C/D
    product_type: str = ""             # medical/critical/accident/life/health/claims/general
    topic: str = ""
    created_at: str = ""
    effective_date: str = ""
    version: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NormalizedQuery:
    original: str
    normalized: str
    concepts: list = field(default_factory=list)


@dataclass
class Candidate:
    chunk: Chunk
    sparse_score: float = 0.0
    dense_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    # diagnostic sub-scores (set by reranker, not serialized)
    semantic_score: float = 0.0
    keyword_score: float = 0.0
    domain_score: float = 0.0
    source_score: float = 0.0
    specificity_score: float = 0.0


@dataclass
class Evidence:
    chunk_id: str
    document_id: str
    document_name: str
    source_type: str
    source_level: str
    section: str
    content: str
    score: float
    retrieval_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RetrievalResult:
    status: str            # success | partial_evidence | insufficient_evidence | retrieval_error
    query: str
    normalized_query: str
    results: list = field(default_factory=list)   # list[Evidence]
    conflict: bool = False
    reason: str = ""
    retrieval_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["results"] = [r.to_dict() if isinstance(r, Evidence) else r for r in self.results]
        return d
