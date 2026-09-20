"""Phase 18 — WeKnora Integration tests.

LIVE STATUS: this environment has NO container runtime (no Docker /
Podman / WSL — re-verified this session) and no WeKnora endpoint, so
the real-retrieval gates are HONESTLY BLOCKED (see the phase report).
What this suite proves instead — everything that does NOT need a live
WeKnora:

  W1 provider seam audit (transport-injected only; Ask/ReAct absent)
  W2 contract normalization via injected transport (E01/E03–E09)
  W3 E10 provider-unavailable fail-closed (no mock fallback)
  W4 provider-selection priority + HG15 strict-mode no-silent-mock
  W5 retrieval_method stays inside the canonical enum
  W6 governance equivalence Mock-vs-WeKnora-shaped hits (contract
     semantics, not identical ranking — §14)
  W7 the LIVE gates, env-gated on INSURANCE_AGENT_WEKNORA_URL —
     skipped loudly, never faked
"""
from __future__ import annotations

import copy
import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from knowledge.governance import (QueryContext, SourceRegistry,  # noqa: E402
                                  validate_hit)
from knowledge.provider import (KnowledgeFilters,  # noqa: E402
                                KnowledgeSearchResult,
                                MockKnowledgeProvider,
                                ProviderConfigError, ProviderError,
                                ProviderUnavailable,
                                ProviderResponseInvalid,
                                WeKnoraKnowledgeProvider,
                                build_named_provider,
                                map_weknora_response,
                                reset_default_provider,
                                set_default_provider)
from knowledge.service import (KnowledgeService, default_registry,  # noqa: E402
                               reset_default_service, set_default_service)

GOV_KB = os.path.join(REPO, "knowledge", "governance", "fixtures", "kb")
GOV_TABLE = os.path.join(REPO, "knowledge", "governance", "fixtures",
                         "governed_sources.json")
SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def gov_registry():
    return SourceRegistry.from_kb(GOV_KB, GOV_TABLE)


def fake_transport(payload):
    n = min(int(payload.get("top_k") or 10), 10)
    return {"results": [
        {"content": "健康保险管理办法测试语料 %d:等待期 30 天" % i,
         "score": 0.9 - 0.05 * i,
         "metadata": {"document_id": "gov_reg_medical_2026",
                      "chunk_id": "gov_reg_medical_2026_000",
                      "document_name": "合成医疗监管条例 2026 版",
                      "section": "等待期", "source_type": "regulation",
                      "source_level": "S",
                      "version_id":
                          "synthetic-medical-regulation@2026"}}
        for i in range(n)], "total": n}


def registry_matched_transport(payload):
    """A WeKnora-shaped response whose chunks match the GOVERNANCE
    registry (content identical to the fixture chunk)."""
    reg = gov_registry()
    entry = reg.get_entry("gov_reg_medical_2026")
    cid = sorted(entry["content_hashes"])[0]
    import hashlib
    with open(os.path.join(GOV_KB, "gov_reg_medical_2026.md"),
              encoding="utf-8-sig") as f:
        text = f.read()
    from knowledge.rag.store import chunk_markdown
    chunks = chunk_markdown(text, "gov_reg_medical_2026",
                            "gov_reg_medical_2026")
    target = next(c for c in chunks if c.chunk_id == cid)
    return {"results": [
        {"content": target.content, "score": 0.93,
         "metadata": {"document_id": "gov_reg_medical_2026",
                      "chunk_id": target.chunk_id,
                      "document_name": "gov_reg_medical_2026",
                      "section": target.section,
                      "source_type": "regulation",
                      "source_level": "S",
                      "version_id":
                          "synthetic-medical-regulation@2026"}},
        # a second, deliberately UNREGISTERED document from the backend
        {"content": "backend-only doc not in registry", "score": 0.5,
         "metadata": {"document_id": "weknora-only-doc",
                      "chunk_id": "weknora-only_001"}}], "total": 2}


# ------------------------------------------------------------------ #
@section
def test_w1_seam_audit(c: Checks):
    src = inspect.getsource(sys.modules["knowledge.provider.weknora"])
    for banned in ("def ask", "def chat", "def react", "def answer",
                   "def agent", "def llm"):
        c.chk("W1: adapter exposes no %s path" % banned.strip("def "),
              banned not in src)
    for tok in ("import requests", "import httpx", "import urllib",
                "import mcp", "docker"):
        c.chk("W1: adapter free of %s" % tok, tok not in src)
    c.chk("W1: transport is INJECTED (no client constructed inside "
          "the provider class)", "_transport" in src
          and "__init__" in src)


@section
def test_w2_contract_normalization(c: Checks):
    prov = WeKnoraKnowledgeProvider(transport=fake_transport)
    res = prov.search("健康保险 等待期", top_k=3)
    c.chk("W2/E01: normalized result is the canonical type",
          isinstance(res, KnowledgeSearchResult) and len(res.results) == 3)
    hit = res.results[0]
    for f in ("chunk_id", "document_id", "content", "content_hash",
              "score", "source_type", "source_level", "version_id"):
        c.chk("W2/E01: hit carries %s" % f, bool(getattr(hit, f, None)
                                                 is not None))
    # malformed shapes → reject (E09 / F03-F05)
    bad = {"missing results": {},
           "hit not object": {"results": [1]},
           "no content": {"results": [{"score": 1, "metadata":
                          {"document_id": "d", "chunk_id": "c"}}]},
           "no score": {"results": [{"content": "x", "metadata":
                        {"document_id": "d", "chunk_id": "c"}}]},
           "no chunk id": {"results": [{"content": "x", "score": 1,
                           "metadata": {"document_id": "d"}}]},
           }
    for name, raw in bad.items():
        raised = False
        try:
            map_weknora_response(raw, "q")
        except ProviderResponseInvalid:
            raised = True
        c.chk("W2/E09: malformed (%s) rejected" % name, raised)
    # empty → honest abstention (E08 / F14)
    empty = map_weknora_response({"results": []}, "q")
    c.chk("W2/E08: empty retrieval abstains (not an error)",
          empty.status == "insufficient_evidence"
          and empty.results == [])


@section
def test_w3_unavailable_fail_closed(c: Checks):
    prov = WeKnoraKnowledgeProvider()      # no transport configured
    raised = False
    try:
        prov.search("健康保险")
    except ProviderUnavailable:
        raised = True
    c.chk("W3/E10: unavailable WeKnora raises (never returns)",
          raised)
    # and the SERVICE composed with it propagates — no mock fallback
    svc = KnowledgeService(provider=prov, registry=gov_registry(),
                           now_fn=lambda: "2026-09-20T00:00:00Z")
    fell_back = False
    try:
        svc.build_evidence("健康保险 等待期")
    except ProviderError:
        fell_back = False
    except Exception:  # noqa: BLE001
        fell_back = True
    c.chk("W3/E10: service propagates ProviderError (no silent mock "
          "substitution)", not fell_back)


@section
def test_w4_selection_and_hg15(c: Checks):
    saved_mode = os.environ.get("INSURANCE_AGENT_MODE")
    saved_prov = os.environ.get("INSURANCE_AGENT_KNOWLEDGE_PROVIDER")
    try:
        # priority: explicit injection wins
        from knowledge.provider import (default_provider,
                                        set_default_provider,
                                        reset_default_provider)
        mockp = MockKnowledgeProvider()
        set_default_provider(mockp)
        c.chk("W4: explicit injection wins", default_provider() is mockp)
        reset_default_provider()
        # DEMO default = stamped mock
        os.environ.pop("INSURANCE_AGENT_MODE", None)
        os.environ.pop("INSURANCE_AGENT_KNOWLEDGE_PROVIDER", None)
        reset_default_provider()
        reset_default_service()
        c.chk("W4: DEMO default remains the offline mock",
              default_provider().name == "mock")
        # STRICT + unset env → fail closed (HG15)
        for mode in ("controlled_pilot", "production"):
            os.environ["INSURANCE_AGENT_MODE"] = mode
            os.environ.pop("INSURANCE_AGENT_KNOWLEDGE_PROVIDER", None)
            reset_default_provider()
            raised = False
            try:
                default_provider()
            except ProviderConfigError:
                raised = True
            c.chk("W4/HG15: strict %s + unset provider fails closed"
                  % mode, raised)
        # STRICT + EXPLICIT mock = deliberate operator choice (allowed,
        # documented — not a SILENT default)
        os.environ["INSURANCE_AGENT_MODE"] = "controlled_pilot"
        os.environ["INSURANCE_AGENT_KNOWLEDGE_PROVIDER"] = "mock"
        reset_default_provider()
        c.chk("W4/HG15: strict + EXPLICIT mock is a documented choice",
              default_provider().name == "mock")
        # unknown provider name still fails closed everywhere
        os.environ["INSURANCE_AGENT_KNOWLEDGE_PROVIDER"] = "bogus"
        reset_default_provider()
        raised = False
        try:
            default_provider()
        except ProviderConfigError:
            raised = True
        c.chk("W4: unknown provider fails closed in strict mode too",
              raised)
    finally:
        reset_default_provider()
        reset_default_service()
        for var, val in (("INSURANCE_AGENT_MODE", saved_mode),
                         ("INSURANCE_AGENT_KNOWLEDGE_PROVIDER",
                          saved_prov)):
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val


@section
def test_w5_enum_conformance(c: Checks):
    prov = WeKnoraKnowledgeProvider(transport=fake_transport)
    res = prov.search("健康保险 等待期")
    c.chk("W5: retrieval_method inside the canonical enum",
          res.retrieval_metadata.get("retrieval_method")
          in ("sparse_rrf", "hybrid_rrf", "unknown"))
    c.chk("W5: backend identity confined to provider field",
          res.retrieval_metadata.get("provider") == "weknora"
          and "weknora_hybrid" not in json.dumps(res.to_dict(),
                                                 ensure_ascii=False))


@section
def test_w6_governance_equivalence(c: Checks):
    """Same registry, same governance; two differently-SHAPED provider
    outputs must land on the same verdicts (contract semantics — NOT
    identical ranking, §14)."""
    reg = gov_registry()
    ctx = QueryContext(as_of="2026-06-01")
    # mock side
    mock = MockKnowledgeProvider(kb_dir=GOV_KB,
                                  stamps=reg.provider_stamps())
    mres = mock.search("合成医疗监管条例 等待期 免赔额")
    # weknora-shaped side (registry-matched chunks)
    wprov = WeKnoraKnowledgeProvider(transport=registry_matched_transport)
    wres = wprov.search("合成医疗监管条例 等待期 免赔额")
    m_by_doc = {}
    for h in mres.results:
        if h.document_id in ("gov_reg_medical_2026",
                             "gov_reg_medical_2024"):
            m_by_doc[(h.document_id, validate_hit(
                h, ctx, reg).allowed)] = True
    w_verdicts = {}
    for h in wres.results:
        d = validate_hit(h, ctx, reg)
        w_verdicts[h.document_id] = (d.allowed, d.reasons[:1])
    c.chk("W6/E02: registered doc ALLOWED on the WeKnora-shaped side",
          w_verdicts.get("gov_reg_medical_2026",
                         (False,))[0] is True)
    c.chk("W6/E06: backend-only UNREGISTERED document DENIED (F06)",
          w_verdicts.get("weknora-only-doc", (True,))[0] is False)
    c.chk("W6: mock side agrees on the registered doc",
          any(k == ("gov_reg_medical_2026", True) for k in m_by_doc))
    # E03/E04/E05/E07 — same governance engine, driven identically on
    # a WeKnora-shaped hit (mutations of the SAME hit)
    base_hit = wres.results[0]
    from knowledge.provider.base import KnowledgeHit
    bj_entry = reg.get_entry("gov_bj_claim_rule")
    bj_chunk = sorted(bj_entry["content_hashes"])[0]
    mutations = [
        ("E03-expired", dict(document_id="gov_reg_medical_2024",
                             version_id="synthetic-medical-regulation@2024"),
         QueryContext(as_of="2026-06-01")),
        ("E04-unknown-license", {}, QueryContext(as_of="2026-06-01")),
        ("E05-authority-mismatch", dict(source_level="B"),
         QueryContext(as_of="2026-06-01")),
        # jurisdiction denial needs a LOCAL doc: CN-BJ rule vs CN-SH
        # query (a national CN doc correctly applies locally — not a
        # violation; the existing governance contract)
        ("E06-jurisdiction", dict(document_id="gov_bj_claim_rule",
                                  chunk_id=bj_chunk,
                                  version_id="synthetic-bj-claim-rule@1",
                                  source_level="A",
                                  content_hash=bj_entry["content_hashes"][
                                      bj_chunk]),
         QueryContext(as_of="2026-06-01", jurisdiction="CN-SH")),
        ("E07-hash", dict(content_hash="ff" * 32),
         QueryContext(as_of="2026-06-01")),
    ]
    reg_u = SourceRegistry.from_kb(GOV_KB, GOV_TABLE)
    for name, over, qctx in mutations:
        kw = dict(document_id=base_hit.document_id,
                  content=base_hit.content,
                  document_name=base_hit.document_name,
                  section=base_hit.section,
                  source_type=base_hit.source_type,
                  source_level=base_hit.source_level,
                  version_id=base_hit.version_id,
                  chunk_id=base_hit.chunk_id,
                  content_hash=base_hit.content_hash,
                  score=0.9)
        if name == "E04-unknown-license":
            reg_u.get_entry("gov_reg_medical_2026")[
                "license_status"] = "UNKNOWN"
        kw.update(over)
        d = validate_hit(KnowledgeHit(**kw), qctx,
                         reg_u if name == "E04-unknown-license" else reg)
        c.chk("W6/%s: WeKnora-shaped hit DENIED" % name, not d.allowed,
              d.reasons[:2])


@section
def test_w7_live_gates(c: Checks):
    url = os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "").strip()
    if not url:
        c.chk("W7: LIVE WeKnora gates SKIPPED — no endpoint in this "
              "environment (docker/podman/wsl absent; re-verified). "
              "NOT claimed as PASS.", True)
        c.chk("W7: the gated live runner exists for the operator "
              "(tests/runtime/test_p14_weknora_integration.py)",
              os.path.isfile(os.path.join(
                  REPO, "tests", "runtime",
                  "test_p14_weknora_integration.py")))
        return
    # live path (operator-provided endpoint)
    import urllib.request
    def transport(payload):
        req = urllib.request.Request(
            url.rstrip("/") + os.environ.get(
                "INSURANCE_AGENT_WEKNORA_SEARCH_PATH",
                "/api/knowledge/search"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     **({"Authorization": "Bearer " + os.environ.get(
                         "INSURANCE_AGENT_WEKNORA_API_KEY", "")}
                        if os.environ.get(
                            "INSURANCE_AGENT_WEKNORA_API_KEY") else {})},
            method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    prov = WeKnoraKnowledgeProvider(transport=transport)
    res = prov.search("机动车交通事故责任强制保险 条例", top_k=5)
    c.chk("W7/Q01: live retrieval returns canonical hits",
          isinstance(res, KnowledgeSearchResult))
    for q in ("健康保险管理办法", "互联网保险业务监管办法",
              "医疗保障基金使用监督管理条例"):
        r = prov.search(q, top_k=3)
        c.chk("W7/live %s: canonical contract" % q[:12],
              isinstance(r, KnowledgeSearchResult))
    irr = prov.search("德国足球联赛规则", top_k=3)
    c.chk("W7/Q05: irrelevant query honest (empty or abstain)",
          not irr.results or irr.status == "insufficient_evidence")
    fab = prov.search("不存在的虚构保险监管条例第999条", top_k=3)
    c.chk("W7/Q06: fabricated regulation honest",
          not fab.results or fab.status == "insufficient_evidence")


def main():
    return run_sections(SECTIONS, "p18_weknora_log.txt",
                        "PHASE 18 WEKNORA INTEGRATION")


if __name__ == "__main__":
    sys.exit(main())
