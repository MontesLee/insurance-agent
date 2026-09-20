"""KnowledgeService — the single runtime knowledge path (Phase 14.4).

Closes F-01/F-07: EVERY online knowledge retrieval now flows through
ONE composition — provider (retrieval) → governance (eligibility) →
evidence builder — with no second production path to the deterministic
engine:

    Tool ───────────┐
    Orchestrator ───┼──► KnowledgeService ──► KnowledgeProvider
    Evidence loop ──┘         │                     (mock today,
                              ▼                      weknora later)
                       Governance (knowledge/
                       governance — the ONLY implementation)
                              ▼
                       evidence items (full citation tuple)

Composition rules:

  * Provider selection happens HERE + knowledge/provider (composition
    boundary), never in the tool/orchestrator/loop (§13). The env
    INSURANCE_AGENT_KNOWLEDGE_PROVIDER keeps its 14.1 semantics
    (unknown → ProviderConfigError; weknora without transport →
    ProviderUnavailable — fail closed, no fallback: INVARIANT-K003).
  * The default governed stack stamps the mock provider with registry
    metadata (the WeKnora upload-projection model); stamping is DATA,
    governance still re-verifies every hit.
  * The default registry covers the two project-owned synthetic KBs.
    A custom kb_dir whose documents are unregistered → every hit
    rejected (fail-closed governance, by design).
  * as_of defaults to the system date AT THIS SEAM ONLY (single
    place); tests inject explicitly. jurisdiction defaults to CN.

Invariants enforced by tests/runtime/test_p14_governance_runtime.py:
K001 all runtime retrieval through KnowledgeProvider; K002 no evidence
from a hit that failed governance; K003 no provider fallback; K004
tool & orchestrator share this one abstraction.
"""
from __future__ import annotations

import os
import time
from typing import Optional

from knowledge.governance import (GovernanceDecision, QueryContext,
                                  SourceRegistry, build_evidence_item,
                                  govern_search_result)
from knowledge.provider import (DEFAULT_PROVIDER_NAME, PROVIDER_ENV,
                                ProviderConfigError, MockKnowledgeProvider,
                                build_named_provider)

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOV_FIXTURES = os.path.join(_HERE, "governance", "fixtures")
_FIXTURES_TABLE = os.path.join(_GOV_FIXTURES, "fixtures_sources.json")
_GOV_TABLE = os.path.join(_GOV_FIXTURES, "governed_sources.json")


def _skill_fixtures_kb() -> str:
    return os.path.join(_HERE, "..", ".trae", "skills", "knowledge-search",
                        "evals", "fixtures", "kb")


def default_registry() -> SourceRegistry:
    """Registry over the project-owned synthetic KBs (fixtures + gov
    fixtures). Deterministic; hashes computed with the existing
    chunker so they always match what retrieval returns."""
    a = SourceRegistry.from_kb(_skill_fixtures_kb(), _FIXTURES_TABLE)
    b = SourceRegistry.from_kb(os.path.join(_GOV_FIXTURES, "kb"),
                               _GOV_TABLE)
    return SourceRegistry(a.entries + b.entries)


_KB_REGISTRY_CACHE: dict = {}


def registry_for(kb_dir: str) -> SourceRegistry:
    """A knowledge deployment is a KB **paired with its registry**:
    the domain pack and the skill fixtures share filename stems but
    are DIFFERENT corpora, so one global registry cannot serve both.
    Known KB dirs map to their table; an EMPTY KB governs to an empty
    registry (honest abstention); an UNKNOWN non-empty KB raises —
    fail closed, never auto-registered."""
    from knowledge.governance import RegistryError
    kb = os.path.normpath(os.path.abspath(kb_dir))
    if kb in _KB_REGISTRY_CACHE:
        return _KB_REGISTRY_CACHE[kb]
    try:
        files = [f for f in os.listdir(kb)
                 if f.lower().endswith((".md", ".txt"))]
    except OSError:
        raise RegistryError("knowledge KB not found: %s" % kb)
    if not files:
        _KB_REGISTRY_CACHE[kb] = SourceRegistry([])
        return _KB_REGISTRY_CACHE[kb]
    domain_kb = os.path.normpath(os.path.abspath(os.path.join(
        _HERE, "..", "domain", "insurance", "references")))
    tables = {
        os.path.normpath(os.path.abspath(_skill_fixtures_kb())):
            (_skill_fixtures_kb(), _FIXTURES_TABLE),
        os.path.normpath(os.path.abspath(
            os.path.join(_GOV_FIXTURES, "kb"))):
            (os.path.join(_GOV_FIXTURES, "kb"), _GOV_TABLE),
        domain_kb: (domain_kb, os.path.join(_GOV_FIXTURES,
                                            "domain_sources.json")),
    }
    if kb not in tables:
        raise RegistryError(
            "no source registry for KB %s — refusing to auto-register "
            "(fail closed)" % kb)
    d, t = tables[kb]
    _KB_REGISTRY_CACHE[kb] = SourceRegistry.from_kb(d, t)
    return _KB_REGISTRY_CACHE[kb]


class KnowledgeService:
    """Provider + registry + governance + evidence builder — ONE
    implementation shared by the tool, the orchestrator and the
    evidence loop."""

    def __init__(self, provider=None, registry: Optional[SourceRegistry]
                 = None, now_fn=None):
        # Phase 14.5: deterministic-clock injection for tests (never
        # depend on the real wall clock in a lineage test). Default is
        # the UTC ISO stamp used everywhere else in the runtime.
        self._now_fn = now_fn or (lambda: time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        from knowledge.provider import injected_provider
        self._registry = registry
        if provider is not None:
            self.provider = provider
        elif injected_provider() is not None:
            # an explicit composition injection (set_default_provider)
            # ALWAYS wins — the injection seam must reach the runtime
            self.provider = injected_provider()
        else:
            # composition boundary: env-selected provider; the default
            # mock receives the registry projection stamps
            name = os.environ.get(PROVIDER_ENV, DEFAULT_PROVIDER_NAME)
            if name == DEFAULT_PROVIDER_NAME:
                self.provider = MockKnowledgeProvider(
                    stamps=self.registry().provider_stamps())
            else:
                # weknora (or future): stamps come from the backend's
                # own metadata; unknown names fail closed HERE
                self.provider = build_named_provider(name)

    # ---- registry ---------------------------------------------------- #
    def registry(self) -> SourceRegistry:
        if self._registry is None:
            self._registry = default_registry()
        return self._registry

    # ---- the one search path ------------------------------------------ #
    def search(self, query: str, top_k: Optional[int] = None,
               as_of: Optional[str] = None,
               jurisdiction: str = "CN"):
        """Provider retrieval + mandatory governance. Returns
        (governed_result, decisions, ctx). Every rejected hit carries
        machine-readable rule ids; nothing ungoverned escapes."""
        ctx = QueryContext(as_of=as_of or time.strftime("%Y-%m-%d"),
                           jurisdiction=jurisdiction)
        raw = self.provider.search(query, top_k=top_k)
        governed, decisions = govern_search_result(raw, ctx,
                                                   self.registry())
        return governed, decisions, ctx

    def build_evidence(self, query: str, top_k: Optional[int] = None,
                       as_of: Optional[str] = None,
                       jurisdiction: str = "CN"):
        """Governed retrieval + evidence construction. Returns
        (items, governed, decisions, ctx): items are evidence dicts
        for the ALLOWED hits only (K002) carrying the full citation
        tuple; the governed result's dict feeds the canonical adapter
        unchanged."""
        governed, decisions, ctx = self.search(query, top_k=top_k,
                                               as_of=as_of,
                                               jurisdiction=jurisdiction)
        from knowledge.governance import validate_hit
        now = self._now_fn()
        items = []
        for h in governed.results:      # kept hits only (K002)
            d = validate_hit(h, ctx, self.registry())
            items.append(build_evidence_item(h, d, ctx, now=now))
        return items, governed, decisions, ctx

    def governed_output(self, query: str, top_k: Optional[int] = None,
                        as_of: Optional[str] = None,
                        jurisdiction: str = "CN") -> dict:
        """Engine-compatible ks_output dict whose results are the
        GOVERNED evidence items — what the canonical adapter consumes
        (both the tool path and the evidence-loop path use this, so
        they are consistent by construction)."""
        items, governed, decisions, ctx = self.build_evidence(
            query, top_k=top_k, as_of=as_of, jurisdiction=jurisdiction)
        out = governed.to_dict()
        out["results"] = items
        return out


def wrap_test_engine(engine):
    """Normalize a (possibly dict-shaped) TEST engine so the mock
    provider can consume it (attribute surface). Test-injection seam
    only — production providers never go through this."""
    from types import SimpleNamespace

    class _Normalized:
        def search(self, q, top_k=None):
            res = (engine.search(q, top_k=top_k) if top_k
                   else engine.search(q))
            if hasattr(res, "results"):
                return res
            d = res.to_dict() if hasattr(res, "to_dict") else res
            hits = []
            for r in d.get("results", []):
                ns = SimpleNamespace(
                    metadata={}, retrieval_score=0.0, rerank_score=0.0,
                    final_score=r.get("score", 0.0), **r)
                hits.append(ns)
            return SimpleNamespace(
                status=d.get("status", "success"),
                query=d.get("query", q),
                normalized_query=d.get("normalized_query", ""),
                results=hits,
                conflict=d.get("conflict", False),
                reason=d.get("reason", ""),
                retrieval_metadata=d.get("retrieval_metadata", {}))
    return _Normalized()


_default_service = None
_default_service_explicit = False
_service_built_with_injected = object()   # sentinel: provider identity


def default_service() -> KnowledgeService:
    """The composition root used by the tool and the evidence loop.
    An explicit set_default_service wins; otherwise the service is
    rebuilt whenever the provider injection identity changes (a stale
    cache must never shadow the injection seam)."""
    global _default_service, _service_built_with_injected
    if _default_service_explicit:
        return _default_service
    from knowledge.provider import injected_provider
    cur = injected_provider()
    if (_default_service is None
            or _service_built_with_injected is not cur):
        _default_service = KnowledgeService()
        _service_built_with_injected = cur
    return _default_service


def set_default_service(service) -> None:
    """Test/composition injection point (wins over everything)."""
    global _default_service, _default_service_explicit
    _default_service = service
    _default_service_explicit = True


def reset_default_service() -> None:
    global _default_service, _default_service_explicit
    _default_service = None
    _default_service_explicit = False
