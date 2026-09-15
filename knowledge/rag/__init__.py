"""rag: foundational knowledge-search / retrieval infrastructure for the insurance agent.

V0.1 is sparse-first (pure-Python trigram-BM25), uses RRF fusion, and a deterministic
weighted reranker. All thresholds/weights live in knowledge-search/resources/config/*.rules.json
so the engine only consumes, never decides.

Dense retrieval is a pluggable interface but NOT enabled in V0.1 (no embedding libs in this
environment). Swapping in sentence-transformers later requires no change to engine logic.
"""
from .models import Chunk, NormalizedQuery, Candidate, Evidence, RetrievalResult
from .store import KnowledgeStore, chunk_markdown
from .engine import (
    KnowledgeSearchEngine, SparseRetriever, DenseRetriever,
    BaseReranker, CrossEncoderReranker, DefaultReranker, rrf_fuse, normalize_query,
)

__all__ = [
    "Chunk", "NormalizedQuery", "Candidate", "Evidence", "RetrievalResult",
    "KnowledgeStore", "chunk_markdown",
    "KnowledgeSearchEngine", "SparseRetriever", "DenseRetriever",
    "BaseReranker", "CrossEncoderReranker", "DefaultReranker",
    "rrf_fuse", "normalize_query",
]
