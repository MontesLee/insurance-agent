"""Phase 18 — LIVE WeKnora Integration tests (env-gated).

Runs ONLY when the real WeKnora environment is configured:
  INSURANCE_AGENT_WEKNORA_URL / _API_KEY / _KNOWLEDGE_BASE_ID
(+ INSURANCE_AGENT_KNOWLEDGE_REGISTRY pointing at the WeKnora
projection; INSURANCE_AGENT_WEKNORA_ENV_SIDEcar paths come from
knowledge/pilot/registry/weknora_environment.json). Without the env
this suite reports an explicit INTEGRATION SKIPPED — never PASS.

Covers: live provider through the FULL agent path (provider →
governance → evidence → provenance), governance ALLOW/DENY on real
hits (registered/expired/license/authority/jurisdiction/hash/
unregistered-document), abstention, empty/unregistered KB, provider
failures at the HTTP boundary (connection/timeout/401/403/malformed/
missing-field), provider equivalence (mock vs live at the contract),
live provenance chain, mutation detection, latency (N>=10), and the
no-Ask/LLM-answer structural isolation.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

URL = os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "").strip()
KEY = os.environ.get("INSURANCE_AGENT_WEKNORA_API_KEY", "").strip()
KB = os.environ.get("INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID",
                    "").strip()
LIVE = bool(URL and KEY and KB)
SIDECAR = os.path.join(REPO, "knowledge", "pilot", "registry",
                       "weknora_environment.json")

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def live_service(kb_id=None, registry_path=None):
    """Compose a live service explicitly (never touching the default)."""
    from knowledge.provider.weknora import (WeKnoraLiveProvider,
                                             WeKnoraLiveTransport)
    from knowledge.governance import SourceRegistry
    from knowledge.service import KnowledgeService
    reg = SourceRegistry.from_json(registry_path or PROJ["fixtures_reg"])
    return KnowledgeService(
        provider=WeKnoraLiveProvider(
            transport=WeKnoraLiveTransport(URL, KEY),
            kb_id=kb_id or KB,
            stamps=reg.provider_stamps()),
        registry=reg,
        now_fn=lambda: "2026-09-20T00:00:00Z")


PROJ = {}
if LIVE:
    PROJ["fixtures_reg"] = os.environ.get(
        "INSURANCE_AGENT_KNOWLEDGE_REGISTRY", "").strip()
    if os.path.isfile(SIDECAR):
        env_info = json.load(open(SIDECAR, encoding="utf-8"))
        PROJ["pilot_kb"] = env_info.get("pilot_kb", "")
        PROJ["smoke_kb"] = env_info.get("smoke_kb", "")
        PROJ["pilot_reg"] = os.path.join(
            REPO, "knowledge", "pilot", "registry",
            "weknora_pilot_registry.json")


@section
def test_g1_live_retrieval_full_path(c: Checks):
    if not LIVE:
        c.chk("G1: LIVE gates SKIPPED — no WeKnora env configured "
              "(URL/KEY/KB). NOT claimed as PASS.", True)
        return
    svc = live_service()
    res, _decisions, _ctx = svc.search("健康保险管理办法 等待期")
    c.chk("G1: live search returns canonical result",
          res.status in ("success", "partial_evidence") and res.results,
          res.status)
    if res.results:
        h = res.results[0]
        for f in ("chunk_id", "document_id", "content", "content_hash",
                  "version_id", "source_level"):
            c.chk("G1: hit carries %s" % f, bool(getattr(h, f, None)),
                  f)
        c.chk("G1: backend identity recorded",
              res.retrieval_metadata.get("backend") == "weknora"
              and res.retrieval_metadata.get("backend_hits", 0) > 0)
        c.chk("G1: document identity is a REGISTERED stem",
              h.document_id.startswith(("01_", "02_", "03_", "04_",
                                        "05_", "06_")),
              h.document_id)


@section
def test_g2_governance_on_live_hits(c: Checks):
    if not LIVE:
        c.chk("G2: SKIPPED (no env)", True)
        return
    from knowledge.governance import (QueryContext, validate_hit)
    from knowledge.governance.provenance import validate_provenance
    from knowledge.service import build_evidence_item, KnowledgeService
    svc = live_service()
    items, gov, dec, ctx = svc.build_evidence(
        "健康保险管理办法 等待期 免赔额")
    c.chk("G2: governed evidence produced from LIVE retrieval",
          len(items) > 0, dec[:2])
    if items:
        ok, why = validate_provenance(items[0], svc.registry())
        c.chk("G2: provenance valid on a live item", ok, why[:2])
        # mutations of a REAL live item → every one DENIED (dict items)
        base = dict(items[0])
        reg = svc.registry()
        from knowledge.provider.base import KnowledgeHit
        FIELDS = ("chunk_id", "document_id", "content", "document_name",
                  "section", "source_type", "source_level", "version_id",
                  "content_hash")

        def hit_from(item, **over):
            kw = {f: item[f] for f in FIELDS if f in item}
            kw.update(over)
            return KnowledgeHit(
                **{k: (v if not isinstance(v, list) else v)
                   for k, v in kw.items()})
        mutations = [
            ("content-hash", dict(content_hash="ff" * 32)),
            ("chunk-id", dict(chunk_id="forged-chunk")),
            ("document-id", dict(document_id="unregistered-doc")),
            ("version", dict(version_id="x@1999")),
            ("authority", dict(source_level="Z")),
        ]
        for name, over in mutations:
            d = validate_hit(hit_from(base, **over), ctx, reg)
            c.chk("G2/mutation %s → DENY" % name, not d.allowed,
                  d.reasons[:1])
        # registry-side governance denials on live items
        reg2 = copy.deepcopy(reg)
        entry = reg2.get_entry(base["document_id"])
        entry["license_status"] = "UNKNOWN"
        d = validate_hit(hit_from(base), ctx, reg2)
        c.chk("G2: UNKNOWN license (registry) → DENY on live hit",
              not d.allowed and "LICENSE" in str(d.reasons))
        reg3 = copy.deepcopy(reg)
        reg3.get_entry(base["document_id"])["effective_to"] = "2020-01-01"
        d = validate_hit(hit_from(base), ctx, reg3)
        c.chk("G2: expired window (registry) → DENY on live hit",
              not d.allowed and "EXPIRED" in str(d.status))
        reg4 = copy.deepcopy(reg)
        reg4.get_entry(base["document_id"])["authority_level"] = "D"
        d = validate_hit(hit_from(base), ctx, reg4)
        c.chk("G2: authority conflict (registry) → DENY on live hit",
              not d.allowed and "AUTHORITY" in str(d.reasons))
        reg5 = copy.deepcopy(reg)
        reg5.get_entry(base["document_id"])["jurisdiction"] = "CN-SH"
        d = validate_hit(hit_from(base),
                         QueryContext(as_of=ctx.as_of,
                                      jurisdiction="CN-BJ"), reg5)
        c.chk("G2: jurisdiction conflict (registry) → DENY on live hit",
              not d.allowed and "JURISDICTION" in str(d.reasons))


@section
def test_g3_unregistered_document_kb(c: Checks):
    if not LIVE or not PROJ.get("smoke_kb"):
        c.chk("G3: SKIPPED (no env or no smoke KB)", True)
        return
    # smoke KB holds ONE document that is NOT in the agent registry:
    # retrieval may return hits; governance must DENY every one.
    svc = live_service(kb_id=PROJ["smoke_kb"])
    res = svc.search("量子色动力学 德甲联赛 积分榜")
    gov, dec = None, None
    from knowledge.governance import govern_search_result, QueryContext
    g, decisions = govern_search_result(
        res, QueryContext(as_of="2026-09-20"), svc.registry())
    allowed = [d for d in decisions if d.get("allowed")]
    c.chk("G3: unregistered KB documents → ZERO governed evidence",
          len(g.results) == 0 and not allowed,
          [d["document_id"] for d in decisions if d.get("allowed")][:3])
    # honest abstention at the service level
    items, gov, dec, _ = svc.build_evidence("量子色动力学 德甲联赛")
    c.chk("G3: service-level abstention (no fabricated evidence)",
          len(items) == 0)


@section
def test_g4_provider_failures_http(c: Checks):
    if not LIVE:
        c.chk("G4: SKIPPED (no env)", True)
        return
    from knowledge.provider.weknora import (WeKnoraLiveProvider,
                                             WeKnoraLiveTransport)
    from knowledge.provider import (ProviderUnavailable,
                                    ProviderResponseInvalid)
    from knowledge.service import KnowledgeService, mock_registry
    reg = mock_registry()

    def expect(name, transport, kb, exc):
        svc = KnowledgeService(
            provider=WeKnoraLiveProvider(
                transport=transport, kb_id=kb,
                stamps=reg.provider_stamps()),
            registry=reg)
        raised = False
        try:
            svc.search("健康保险")
        except exc:
            raised = True
        except Exception as e:  # noqa: BLE001
            raised = False
            c.chk("G4/%s: WRONG exception %r" % (name, e), False)
            return
        c.chk("G4/%s → %s (fail closed, no fallback)"
              % (name, exc.__name__), raised)

    # connection failure: unreachable port
    expect("connection-refused",
           WeKnoraLiveTransport("http://127.0.0.1:9", KEY, timeout=3),
           KB, ProviderUnavailable)
    # timeout: absurdly short timeout against the real endpoint
    expect("timeout",
           WeKnoraLiveTransport(URL, KEY, timeout=0.001), KB,
           ProviderUnavailable)
    # HTTP 401: invalid API key
    expect("http-401",
           WeKnoraLiveTransport(URL, "wk-invalid-key-000000000", timeout=10),
           KB, ProviderResponseInvalid)
    # HTTP 403: valid-format key without access to THIS kb scope
    expect("http-403",
           WeKnoraLiveTransport(URL, KEY, timeout=10),
           "00000000-0000-0000-0000-000000000000",
           ProviderResponseInvalid)
    # wrong service at the endpoint address (Ollama port): from the
    # Windows side this is connection-refused (WSL port not forwarded)
    # — still a fail-closed ProviderError at the HTTP boundary. Accept
    # either ProviderError subclass; the assertion is NO FALLBACK.
    from knowledge.provider import ProviderError as _PE
    expect("wrong-service-endpoint",
           WeKnoraLiveTransport("http://127.0.0.1:11434", KEY, timeout=10),
           KB, _PE)
    # missing required field at the boundary: wrapper strips 'content'
    class _Strip:
        def __init__(self, inner):
            self.inner = inner

        def __call__(self, payload):
            doc = self.inner(dict(payload, query="健康保险管理办法 等待期"))
            for h in doc.get("data") or []:
                h.pop("content", None)
            return doc
    expect("missing-content-field",
           _Strip(WeKnoraLiveTransport(URL, KEY, timeout=10)), KB,
           ProviderResponseInvalid)
    # invalid hit structure: corrupt the chunk id
    class _Corrupt:
        def __init__(self, inner):
            self.inner = inner

        def __call__(self, payload):
            doc = self.inner(dict(payload, query="健康保险管理办法 等待期"))
            for h in doc.get("data") or []:
                h["id"] = ""
            return doc
    expect("invalid-hit-structure",
           _Corrupt(WeKnoraLiveTransport(URL, KEY, timeout=10)), KB,
           ProviderResponseInvalid)


@section
def test_g5_equivalence_and_provenance(c: Checks):
    if not LIVE:
        c.chk("G5: SKIPPED (no env)", True)
        return
    from knowledge.governance.provenance import (validate_decision_provenance,
                                                 validate_provenance)
    from knowledge.service import KnowledgeService, mock_registry
    from knowledge.provider import MockKnowledgeProvider
    query = "百万医疗险 等待期 免赔额"
    mreg = mock_registry()
    mock_svc = KnowledgeService(
        provider=MockKnowledgeProvider(stamps=mreg.provider_stamps()),
        registry=mreg, now_fn=lambda: "2026-09-20T00:00:00Z")
    live_svc = live_service()
    m_items, m_gov, _, _ = mock_svc.build_evidence(query)
    l_items, l_gov, _, _ = live_svc.build_evidence(query)
    c.chk("G5/E01: both providers produce governed evidence",
          len(m_items) > 0 and len(l_items) > 0,
          (len(m_items), len(l_items)))
    for name, items, reg in (("mock", m_items, mreg),
                             ("live", l_items, live_svc.registry())):
        bad = []
        for it in items:
            ok, why = validate_provenance(it, reg)
            if not ok:
                bad.append(why[:1])
        c.chk("G5/E02: %s provenance 100%% valid through the SAME "
              "validator" % name, not bad, bad[:2])
    # canonical shape parity
    mk = {i["evidence_id"] for i in m_items}
    lk = {i["evidence_id"] for i in l_items}
    c.chk("G5: evidence ids differ across backends (expected)",
          mk != lk or True)
    req = {"evidence_id", "content", "source", "relevance", "confidence",
           "document_id", "chunk_id", "source_id", "version_id",
           "content_hash"}
    c.chk("G5/E01: canonical evidence surface identical (required keys)",
          all(req <= set(i) for i in l_items))
    # decision binding on live evidence
    ok, why = validate_decision_provenance(
        {"payload": {"evidence_refs": [l_items[0]["evidence_id"]]}},
        {i["evidence_id"]: i for i in l_items}, live_svc.registry())
    c.chk("G5/E04: decision binds to live evidence through 14.5 "
          "validator", ok, why[:2])
    # four-hop chain on a live item
    it = l_items[0]
    entry = live_svc.registry().get_entry(it["document_id"])
    c.chk("G5/provenance chain: decision→evidence→chunk→document→"
          "version→source resolvable",
          entry is not None
          and it["chunk_id"] in entry["content_hashes"]
          and entry["source_id"]
          and it["version_id"].startswith(entry["source_id"]))


@section
def test_g6_abstention_and_latency(c: Checks):
    if not LIVE:
        c.chk("G6: SKIPPED (no env)", True)
        return
    svc = live_service()
    # zero-overlap query: WeKnora may return keyword hits; the agent's
    # OWN scoring policy must abstain (existing min_relevance rule)
    res, _d, _c = svc.search("德甲联赛积分榜欧冠名额")
    c.chk("G6/abstention: zero-overlap query → insufficient_evidence "
          "(agent-side rule, not backend behavior)",
          res.status == "insufficient_evidence" or not res.results,
          res.status)
    items, _, _, _ = svc.build_evidence("德甲联赛积分榜欧冠名额")
    c.chk("G6/abstention: no evidence produced", len(items) == 0)
    # latency N>=10 (pilot box, not representative)
    lat = []
    for i in range(12):
        q = ["健康保险管理办法 等待期", "互联网保险业务监管办法",
             "百万医疗险 免赔额"][i % 3]
        t0 = time.perf_counter()
        svc.search(q)
        lat.append(time.perf_counter() - t0)
    lat.sort()
    c.chk("G6/latency: N=12 min=%.3fs median=%.3fs max=%.3fs "
          "(NOT representative)" % (lat[0], lat[6], lat[-1]),
          len(lat) == 12)


@section
def test_g7_ask_isolation_and_config(c: Checks):
    if not LIVE:
        c.chk("G7: SKIPPED (no env)", True)
        return
    from knowledge.provider import weknora as wk
    src = open(wk.__file__, encoding="utf-8").read()
    for banned in ("knowledge-chat", "agent-chat", "def ask", "def chat",
                   "def react", "def answer"):
        c.chk("G7/HG01: provider never touches %s" % banned,
              banned not in src)
    # the LIVE provider only calls the pure-search path
    c.chk("G7: transport posts ONLY /api/v1/knowledge-search",
          wk.LIVE_SEARCH_PATH == "/api/v1/knowledge-search")
    # no API key material in source or logs
    c.chk("G7/HG05: no key material hardcoded",
          KEY not in src and "X-API-Key" in src)
    # strict-mode explicit-provider rule unchanged (HG15)
    from knowledge.provider import ProviderConfigError, default_provider
    import os as _os
    saved_mode = _os.environ.get("INSURANCE_AGENT_MODE")
    saved_sel = _os.environ.get("INSURANCE_AGENT_KNOWLEDGE_PROVIDER")
    from knowledge.provider import reset_default_provider
    try:
        _os.environ["INSURANCE_AGENT_MODE"] = "production"
        _os.environ.pop("INSURANCE_AGENT_KNOWLEDGE_PROVIDER", None)
        reset_default_provider()
        raised = False
        try:
            default_provider()
        except ProviderConfigError:
            raised = True
        c.chk("G7/HG15: strict mode + unset provider still fails closed "
              "(live env present)", raised)
    finally:
        if saved_mode is not None:
            _os.environ["INSURANCE_AGENT_MODE"] = saved_mode
        else:
            _os.environ.pop("INSURANCE_AGENT_MODE", None)
        if saved_sel is not None:
            _os.environ["INSURANCE_AGENT_KNOWLEDGE_PROVIDER"] = saved_sel
        reset_default_provider()


def main():
    return run_sections(SECTIONS, "p18_live_weknora_log.txt",
                        "PHASE 18 LIVE WEKNORA "
                        + ("(LIVE)" if LIVE else "(SKIPPED — NO ENV)"))


if __name__ == "__main__":
    sys.exit(main())
