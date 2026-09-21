"""Phase 24 — governance runtime additions (pure unit, no PG/network).

Covers the Phase 24 fail-closed rules that live in the GOVERNANCE and
PROVIDER layers regardless of backend:

  * R2  non-ACTIVE registration states (DISCOVERED/INGESTED/REGISTERED/
        VALIDATED/REJECTED/EXPIRED/SUPERSEDED/INVALID) never ground
        evidence — reason SOURCE_NOT_ACTIVE:<state> (uploaded != ACTIVE)
  * R2b concurrent ACTIVE versions of one source covering as_of →
        VERSION_AMBIGUOUS (never resolved by version-string order)
  * registry concurrent_versions + extended status validation
  * F-24 reanchor_hit: aligned window → canonical chunk content+hash;
        misaligned window → untouched (governance denies on hash);
        already-canonical → untouched
  * service strict-mode policy (HG-24-03): mock provider refused in
        CONTROLLED_PILOT/PRODUCTION; json registry backend refused
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


AS_OF = "2026-06-01"


def _sha(s):
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def _entry(**over):
    e = {
        "document_id": "doc-2026", "source_id": "src-1",
        "source_name": "Test Source", "source_type": "regulation",
        "authority_level": "A", "jurisdiction": "CN", "version": "2026",
        "effective_from": "2026-01-01", "effective_to": None,
        "status": "ACTIVE", "license_status": "ALLOWED",
        "content_hashes": {"c1": _sha("text")},   # matches _Hit default
    }
    e.update(over)
    return e


class _Hit:
    """Duck-typed KnowledgeHit (governance is provider-independent)."""

    def __init__(self, doc="doc-2026", chunk="c1", content="text",
                 source_level="A", version_id="src-1@2026",
                 content_hash=None):
        self.document_id = doc
        self.chunk_id = chunk
        self.content = content
        self.source_level = source_level
        self.version_id = version_id
        self.content_hash = content_hash if content_hash is not None \
            else _sha(content)
        self.score = 0.9
        self.metadata = {}


# --------------------------------------------------------------------- #
@section
def test_s1_not_active_states(c):
    """R2: every pre-activation / anomaly state denies."""
    from knowledge.governance.governance import validate_hit
    from knowledge.governance.model import QueryContext, RegistryError
    from knowledge.governance.registry import SourceRegistry

    ctx = QueryContext(as_of=AS_OF)
    for state in ("DISCOVERED", "INGESTED", "REGISTERED", "VALIDATED",
                  "REJECTED", "EXPIRED", "SUPERSEDED", "INVALID"):
        reg = SourceRegistry([_entry(status=state)])
        d = validate_hit(_Hit(), ctx, reg)
        c.chk("state %s denied" % state, not d.allowed)
        c.chk("state %s reason" % state,
              any(r.startswith("SOURCE_NOT_ACTIVE:%s" % state)
                  for r in d.reasons), d.reasons)
    # RETIRED keeps its established reason (backward compat)
    reg = SourceRegistry([_entry(status="RETIRED")])
    d = validate_hit(_Hit(), ctx, reg)
    c.chk("RETIRED denied", not d.allowed)
    c.chk("RETIRED reason", "SOURCE_RETIRED" in d.reasons, d.reasons)
    # bad status still refuses the WHOLE registry at load time
    try:
        SourceRegistry([_entry(status="WAT")])
        c.chk("bad status refused", False)
    except RegistryError:
        c.chk("bad status refused", True)
    # ACTIVE still allowed (no regression)
    reg = SourceRegistry([_entry()])
    d = validate_hit(_Hit(), ctx, reg)
    c.chk("ACTIVE allowed", d.allowed, d.reasons)


@section
def test_s2_version_ambiguity(c):
    """R2b: two ACTIVE versions of one source covering as_of → deny."""
    from knowledge.governance.governance import validate_hit
    from knowledge.governance.model import QueryContext
    from knowledge.governance.registry import SourceRegistry

    ctx = QueryContext(as_of=AS_OF)
    reg = SourceRegistry([
        _entry(document_id="doc-2024", version="2024",
               effective_from="2024-01-01"),
        _entry(document_id="doc-2026", version="2026",
               effective_from="2026-01-01"),
    ])
    c.chk("concurrent_versions sees 2",
          len(reg.concurrent_versions("src-1", AS_OF)) == 2)
    d = validate_hit(_Hit(doc="doc-2026", version_id="src-1@2026"), ctx,
                     reg)
    c.chk("ambiguous denied", not d.allowed, d.reasons)
    c.chk("VERSION_AMBIGUOUS reason", "VERSION_AMBIGUOUS" in d.reasons,
          d.reasons)
    # non-overlapping windows are NOT ambiguous
    reg2 = SourceRegistry([
        _entry(document_id="doc-2024", version="2024",
               effective_from="2024-01-01", effective_to="2025-12-31"),
        _entry(document_id="doc-2026", version="2026",
               effective_from="2026-01-01"),
    ])
    c.chk("sequential windows not ambiguous",
          len(reg2.concurrent_versions("src-1", AS_OF)) == 1)
    d2 = validate_hit(_Hit(doc="doc-2026", version_id="src-1@2026"), ctx,
                      reg2)
    c.chk("sequential windows allowed", d2.allowed, d2.reasons)
    # superseded old version denied by state, not by ambiguity
    reg3 = SourceRegistry([
        _entry(document_id="doc-2024", version="2024",
               effective_from="2024-01-01", status="SUPERSEDED"),
        _entry(document_id="doc-2026", version="2026",
               effective_from="2026-01-01"),
    ])
    d3 = validate_hit(_Hit(doc="doc-2024", version_id="src-1@2024"), ctx,
                      reg3)
    c.chk("superseded denied",
          not d3.allowed
          and "SOURCE_NOT_ACTIVE:SUPERSEDED" in d3.reasons, d3.reasons)


@section
def test_s3_reanchor_f24(c):
    """F-24 deterministic re-anchoring at the provider boundary."""
    from knowledge.provider.weknora import reanchor_hit

    canonical = "### 第五条 保险机构通过互联网……\n提供服务的规范要求。"
    window = canonical + "\n（后续 chunk 的内容也出现在窗口里）"

    # aligned window → re-anchored to canonical content + hash
    h = _Hit(doc="d", chunk="c1", content=window)
    reanchor_hit(h, canonical)
    c.chk("aligned re-anchored to canonical", h.content == canonical)
    c.chk("aligned hash = canonical hash",
          h.content_hash == _sha(canonical))
    c.chk("raw window preserved", h.metadata.get("search_window")
          == window)
    c.chk("window_aligned flag", h.metadata.get("window_aligned") is True)

    # whitespace-only divergence still aligns (documented rule)
    h2 = _Hit(doc="d", chunk="c1",
              content=canonical.replace("提供", "提 供") + "尾部")
    reanchor_hit(h2, canonical)
    c.chk("whitespace divergence aligned", h2.content == canonical)

    # misaligned window → UNTOUCHED (governance will deny hash)
    mis = "窗口从 chunk 中间开始的内容……" + canonical
    h3 = _Hit(doc="d", chunk="c1", content=mis)
    before = (h3.content, h3.content_hash)
    reanchor_hit(h3, canonical)
    c.chk("misaligned untouched",
          (h3.content, h3.content_hash) == before)
    c.chk("misaligned no metadata flags",
          "window_aligned" not in (h3.metadata or {}))

    # already canonical → untouched (no redundant metadata)
    h4 = _Hit(doc="d", chunk="c1", content=canonical)
    before4 = (h4.content, h4.content_hash)
    reanchor_hit(h4, canonical)
    c.chk("already-canonical untouched",
          (h4.content, h4.content_hash) == before4
          and not h4.metadata)

    # empty canonical → untouched (fail closed, no guessing)
    h5 = _Hit(doc="d", chunk="c1", content=window)
    reanchor_hit(h5, "")
    c.chk("empty canonical untouched", h5.content == window)

    # end-to-end: re-anchored hit passes governance hash rule where the
    # raw window would fail (multi-chunk F-24 case)
    from knowledge.governance.governance import validate_hit
    from knowledge.governance.model import QueryContext
    from knowledge.governance.registry import SourceRegistry
    reg = SourceRegistry([_entry(document_id="d", chunk="c1",
                                 content_hashes={"c1": _sha(canonical)},
                                 version="2026")])
    ctx = QueryContext(as_of=AS_OF)
    raw = _Hit(doc="d", chunk="c1", content=window,
               version_id="src-1@2026")
    d_raw = validate_hit(raw, ctx, reg)
    c.chk("raw window denied (F-24 original symptom)",
          "HASH_MISMATCH:c1" in d_raw.reasons, d_raw.reasons)
    reanchored = _Hit(doc="d", chunk="c1", content=window,
                      version_id="src-1@2026")
    from knowledge.provider.weknora import reanchor_hit as ra
    ra(reanchored, canonical)
    d_ra = validate_hit(reanchored, ctx, reg)
    c.chk("re-anchored window allowed", d_ra.allowed, d_ra.reasons)


@section
def test_s4_service_strict_policy(c):
    """HG-24-03 / HG-24-02: strict modes refuse mock knowledge and a
    non-PG registry."""
    from knowledge.service import (KnowledgeService,
                                   resolve_registry_backend,
                                   REGISTRY_BACKEND_ENV, REGISTRY_ENV)
    from knowledge.provider.base import ProviderConfigError

    mode_env = "INSURANCE_AGENT_MODE"
    saved = {k: os.environ.get(k) for k in
             (mode_env, REGISTRY_BACKEND_ENV, REGISTRY_ENV)}

    def set_env(mode=None, backend=None, regfile=None):
        os.environ.pop(REGISTRY_BACKEND_ENV, None)
        os.environ.pop(REGISTRY_ENV, None)
        if mode is None:
            os.environ.pop(mode_env, None)
        else:
            os.environ[mode_env] = mode
        if backend:
            os.environ[REGISTRY_BACKEND_ENV] = backend
        if regfile:
            os.environ[REGISTRY_ENV] = regfile

    try:
        # non-strict default: json backend, mock allowed
        set_env()
        c.chk("default backend json",
              resolve_registry_backend() == "json")
        set_env(mode="evaluation")
        c.chk("evaluation backend json",
              resolve_registry_backend() == "json")
        # strict: postgres required; json refused; file override refused
        set_env(mode="controlled_pilot")
        c.chk("strict backend postgres",
              resolve_registry_backend() == "postgres")
        set_env(mode="production")
        c.chk("production backend postgres",
              resolve_registry_backend() == "postgres")
        set_env(mode="production", backend="json")
        try:
            resolve_registry_backend()
            c.chk("strict json refused", False)
        except ProviderConfigError:
            c.chk("strict json refused", True)
        set_env(mode="controlled_pilot", regfile="whatever.json")
        try:
            resolve_registry_backend()
            c.chk("strict registry file refused", False)
        except ProviderConfigError:
            c.chk("strict registry file refused", True)
        # strict + mock provider → KnowledgeService refuses BEFORE any
        # registry/provider construction; message names HG-24-03
        set_env(mode="production")
        os.environ.pop("INSURANCE_AGENT_KNOWLEDGE_PROVIDER", None)
        try:
            KnowledgeService()
            c.chk("strict mock refused", False)
        except ProviderConfigError as e:
            c.chk("strict mock refused", "HG-24-03" in str(e))
        # strict + explicit mock env name → same refusal
        os.environ["INSURANCE_AGENT_KNOWLEDGE_PROVIDER"] = "mock"
        try:
            KnowledgeService()
            c.chk("strict explicit mock refused", False)
        except ProviderConfigError as e:
            c.chk("strict explicit mock refused", "HG-24-03" in str(e))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def main() -> int:
    from _common import REPO as _REPO
    os.chdir(_REPO)
    return run_sections(SECTIONS, "p24_governance_log.txt",
                        "PHASE 24 GOVERNANCE UNIT SUITE")


if __name__ == "__main__":
    sys.exit(main())
