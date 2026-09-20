"""KnowledgeProvider contract — Stage 14.1.

The stable boundary between the Insurance Agent and ANY knowledge
infrastructure (phase14-real-knowledge-plan.md Rev 2 §0/§3):

    Agent / Knowledge Tool
      ↓
    KnowledgeProvider            ← this module defines the contract
      ├── MockKnowledgeProvider  (wraps the EXISTING deterministic engine)
      └── WeKnoraKnowledgeProvider (adapter seam; no network in 14.1)

Design rules (enforced by tests/runtime/test_p14_provider.py):

  * BUSINESS-CAPABILITY interface, not a database interface: search()
    only on the runtime-facing Protocol. Ingestion verbs belong to the
    separate operator-side KnowledgeIngestionPort (14.3).
  * Canonical, provider-agnostic results: whatever a backend returns is
    normalized into KnowledgeSearchResult before ANY agent sees it, and
    to_dict() is shape-compatible with the existing engine's
    RetrievalResult.to_dict() so adapters/knowledge_search_adapter and
    the knowledge-evidence contract keep working unchanged.
  * Fail-closed everywhere: unavailable / misconfigured / invalid
    responses raise ProviderError subclasses. There is NO fallback
    provider — a failing production provider must never silently serve
    mock results (C05/C06).
  * Metadata PRESERVATION, not governance: hits carry version_id (empty
    until the 14.3 registry exists) and content_hash so 14.4/14.5 can
    govern later; 14.1 implements no effective-date/authority/license
    filtering (plan §17 — do not smuggle 14.4 into 14.1).

Deliberately NOT on the Protocol yet (no current caller — added when
their consumers exist, per the audit's no-interface-completeness rule):
  get_source / get_document / get_version   → 14.3 (source registry)
  resolve_evidence                          → 14.5 (provenance integrity)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Protocol, runtime_checkable

import hashlib


# ---- fail-closed error taxonomy -------------------------------------------- #
class ProviderError(Exception):
    """Base class — every provider failure is LOUD, never a fake success."""


class ProviderConfigError(ProviderError):
    """The provider selection/configuration itself is invalid (unknown
    name, malformed settings). Never falls back to another provider."""


class ProviderUnavailable(ProviderError):
    """The provider cannot be reached / has no transport configured.
    Production must surface this as FAIL — silent Mock fallback is
    forbidden."""


class ProviderResponseInvalid(ProviderError):
    """The backend response does not satisfy the documented response
    contract (missing ids, non-numeric scores, wrong types). The hit is
    dropped or the search fails — malformed data never becomes
    evidence."""


# ---- canonical result model ------------------------------------------------- #
@dataclass
class KnowledgeFilters:
    """Retrieval hints. Providers MAY pre-filter with them for
    efficiency; the Insurance Governance layer (14.4) re-verifies every
    hit regardless — provider-side filtering is never trusted as
    business validity."""
    as_of: Optional[str] = None            # ISO date; default = now
    allow_history: bool = False            # as_of queries tag historical
    jurisdiction: Optional[str] = None     # national | beijing | other_local
    authority_min: Optional[str] = None    # S/A/B/C/D floor
    source_types: Optional[list] = None
    domains: Optional[list] = None         # knowledge-query domain enum

    def to_dict(self) -> dict:
        out = asdict(self)
        return {k: v for k, v in out.items() if v not in (None, [], False)}


@dataclass
class KnowledgeHit:
    """One retrievable knowledge unit, provider-agnostic.

    Provenance anchors (chunk_id/document_id/section/source_level) are
    REQUIRED shape; version_id is reserved for the 14.3 version
    registry (empty until then — preserved, never fabricated);
    content_hash is a deterministic sha256 of the content so 14.5 can
    re-verify what an external roundtrip returned."""
    chunk_id: str
    document_id: str
    content: str
    document_name: str = ""
    section: str = ""
    source_type: str = ""
    source_level: str = ""
    version_id: str = ""                   # 14.3 registry (empty in 14.1)
    content_hash: str = ""
    score: float = 0.0
    retrieval_score: float = 0.0
    rerank_score: float = 0.0
    final_score: float = 0.0
    metadata: dict = field(default_factory=dict)

    @staticmethod
    def hash_content(content: str) -> str:
        return hashlib.sha256((content or "").encode("utf-8")).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        # keep the engine-compatible flat keys the canonical adapter
        # reads today; provider-metadata rides inside metadata{}
        return d


@dataclass
class KnowledgeSearchResult:
    """Canonical search outcome. `to_dict()` is shape-compatible with
    knowledge/rag/models.RetrievalResult.to_dict() — the downstream
    canonical adapter (adapters/knowledge_search_adapter.to_canonical)
    consumes either unchanged."""
    status: str                    # success|partial_evidence|insufficient_evidence|retrieval_error
    query: str
    normalized_query: str = ""
    results: list = field(default_factory=list)   # list[KnowledgeHit]
    conflict: bool = False
    reason: str = ""
    retrieval_metadata: dict = field(default_factory=dict)

    @property
    def hits(self) -> list:
        """Brief-facing alias; same objects as .results."""
        return self.results

    def to_dict(self) -> dict:
        d = asdict(self)
        d["results"] = [r.to_dict() if isinstance(r, KnowledgeHit) else r
                        for r in self.results]
        return d


@runtime_checkable
class KnowledgeProvider(Protocol):
    """The ONLY thing agents may talk to. Read-only business
    capabilities; no persistence verbs, no LLM-answer verbs."""

    name: str

    def search(self, query: str,
               filters: Optional[KnowledgeFilters] = None,
               top_k: Optional[int] = None) -> KnowledgeSearchResult:
        ...  # pragma: no cover — Protocol
