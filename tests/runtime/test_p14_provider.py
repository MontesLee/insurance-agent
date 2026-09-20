"""Stage 14.1 — KnowledgeProvider Contract tests (C01–C11).

Covers: interface conformance, canonical result conversion (schema-
valid through the EXISTING adapter + contract), WeKnora mapping from a
FAKE response (no network), invalid-response fail-close, provider-
unavailable fail-close, NO silent fallback (weknora failure never
serves mock results), structural Ask/ReAct isolation, provenance
preservation (document/chunk/section/source_level/version slot/
content hash), provider interchangeability on the canonical contract,
determinism, and the composition-boundary/env fail-closed selection.
"""
from __future__ import annotations

import inspect
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from knowledge.provider import (  # noqa: E402
    KnowledgeFilters, KnowledgeHit, KnowledgeProvider,
    KnowledgeSearchResult, MockKnowledgeProvider,
    ProviderConfigError, ProviderError, ProviderResponseInvalid,
    ProviderUnavailable, WeKnoraKnowledgeProvider,
    build_named_provider, default_provider, map_weknora_response,
    reset_default_provider, set_default_provider, PROVIDER_ENV)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


QUERY = "百万医疗险的等待期一般是多少天"


def fresh_dir():
    return tempfile.mkdtemp(prefix="p14_", dir=os.path.join(REPO, "tmp"))


def to_canonical(result_dict):
    from adapters.knowledge_search_adapter import to_canonical as tc
    return tc(result_dict)


def validate_evidence(artifact):
    from knowledge.evidence.provider import validate, EVIDENCE_SCHEMA
    return validate(artifact, EVIDENCE_SCHEMA)


def fake_weknora_transport(payload: dict) -> dict:
    """FAKE WeKnora backend — pure function, no network (14.1 rule)."""
    n = min(int(payload.get("top_k") or 3), 3)
    return {
        "results": [
            {"content": "百万医疗险常见等待期为30天，等待期内出险一般不"
                        "予赔付（测试语料 %d）" % i,
             "score": 0.92 - 0.1 * i,
             "metadata": {
                 "document_id": "wk_doc_01",
                 "chunk_id": "wk_doc_01_%03d" % i,
                 "document_name": "wk-医疗基础知识",
                 "section": "等待期",
                 "source_type": "official",
                 "source_level": "A",
                 "version_id": "wk_doc_01@1.0"}}
            for i in range(n)],
        "total": n,
    }


# ------------------------------------------------------------------ #
# S1 — C01 interface · C02 canonical conversion · C10 determinism
# ------------------------------------------------------------------ #
@section
def test_s1_mock_contract_and_canonical(c: Checks):
    mock = MockKnowledgeProvider()
    c.chk("C01: Mock satisfies the KnowledgeProvider protocol",
          isinstance(mock, KnowledgeProvider))
    c.chk("C01: provider exposes exactly the business verb search",
          hasattr(mock, "search") and hasattr(mock, "name"))
    res = mock.search(QUERY)
    c.chk("C01: search returns the canonical result type",
          isinstance(res, KnowledgeSearchResult))
    c.chk("C02: result carries hits with provenance anchors",
          len(res.results) > 0 and all(
              h.chunk_id and h.document_id for h in res.results))
    d = res.to_dict()
    c.chk("C02: to_dict is engine-shaped for the existing adapter",
          {"status", "query", "results", "conflict",
           "retrieval_metadata"} <= set(d), sorted(d.keys()))
    artifact = to_canonical(d)
    ok, errs = validate_evidence(artifact)
    c.chk("C02: canonical artifact validates against the EXISTING "
          "knowledge-evidence contract", ok, errs[:3])
    ev = artifact["payload"]["evidence"]
    c.chk("C02: evidence items resolve DOCUMENT/CHUNK provenance",
          all(any(p["source_type"] == "DOCUMENT" for p in e["provenance"])
              and any(p["source_type"] == "CHUNK" for p in e["provenance"])
              for e in ev))
    res2 = MockKnowledgeProvider().search(QUERY)
    c.chk("C10: determinism — same query, identical canonical dict",
          json.dumps(res.to_dict(), sort_keys=True, ensure_ascii=False)
          == json.dumps(res2.to_dict(), sort_keys=True, ensure_ascii=False))
    c.chk("C10: content hashes are stable",
          res.to_dict()["results"][0]["content_hash"]
          == res2.to_dict()["results"][0]["content_hash"])
    f = KnowledgeFilters(as_of="2026-09-19", jurisdiction="national",
                         authority_min="B", domains=["medical"])
    res3 = mock.search(QUERY, filters=f)
    c.chk("S1: filters are PRESERVED in metadata (governance = 14.4)",
          res3.retrieval_metadata.get("filters", {}).get("jurisdiction")
          == "national")
    c.chk("S1: version slot reserved but empty until 14.3 registry",
          all(h.version_id == "" for h in res3.results))


# ------------------------------------------------------------------ #
# S2 — C03 fake-response mapping · C04 invalid responses fail closed
# ------------------------------------------------------------------ #
@section
def test_s2_weknora_mapping(c: Checks):
    prov = WeKnoraKnowledgeProvider(transport=fake_weknora_transport)
    c.chk("C03: adapter with injected fake transport satisfies protocol",
          isinstance(prov, KnowledgeProvider))
    res = prov.search(QUERY, top_k=3)
    c.chk("C03: fake WeKnora response maps to canonical result",
          isinstance(res, KnowledgeSearchResult) and len(res.results) == 3)
    c.chk("C03: mapping preserves document/chunk/version ids",
          res.results[0].document_id == "wk_doc_01"
          and res.results[0].chunk_id == "wk_doc_01_000"
          and res.results[0].version_id == "wk_doc_01@1.0")
    d = res.to_dict()
    artifact = to_canonical(d)
    ok, errs = validate_evidence(artifact)
    c.chk("C03: mapped result validates against the SAME canonical "
          "contract", ok, errs[:3])
    c.chk("C03: provider recorded in metadata",
          res.retrieval_metadata.get("provider") == "weknora")

    bad_responses = {
        "not an object": ["list"],
        "missing results": {"foo": 1},
        "results not a list": {"results": "x"},
        "item not object": {"results": ["x"]},
        "no content": {"results": [{"score": 0.9, "metadata": {
            "document_id": "d", "chunk_id": "c"}}]},
        "empty content": {"results": [{"content": "  ", "score": 0.9,
            "metadata": {"document_id": "d", "chunk_id": "c"}}]},
        "non-numeric score": {"results": [{"content": "x", "score": "0.9",
            "metadata": {"document_id": "d", "chunk_id": "c"}}]},
        "missing document_id": {"results": [{"content": "x", "score": 0.9,
            "metadata": {"chunk_id": "c"}}]},
        "missing chunk_id": {"results": [{"content": "x", "score": 0.9,
            "metadata": {"document_id": "d"}}]},
    }
    for name, raw in bad_responses.items():
        raised = False
        try:
            map_weknora_response(raw, QUERY)
        except ProviderResponseInvalid:
            raised = True
        c.chk("C04: invalid response (%s) → ProviderResponseInvalid"
              % name, raised)
    raised = False
    try:
        map_weknora_response({"results": []}, QUERY)
    except ProviderResponseInvalid:
        raised = True
    c.chk("C04: empty result set is insufficient_evidence, not an error",
          not raised and map_weknora_response(
              {"results": []}, QUERY).status == "insufficient_evidence")


# ------------------------------------------------------------------ #
# S3 — C05 unavailable · C06 no silent fallback · config fail-closed
# ------------------------------------------------------------------ #
@section
def test_s3_fail_closed_and_fallback_policy(c: Checks):
    saved = os.environ.get(PROVIDER_ENV)
    try:
        prov = WeKnoraKnowledgeProvider()          # no transport
        raised = False
        try:
            prov.search(QUERY)
        except ProviderUnavailable:
            raised = True
        c.chk("C05: unconfigured WeKnora → ProviderUnavailable", raised)

        os.environ[PROVIDER_ENV] = "weknora"
        reset_default_provider()
        sel = default_provider()
        c.chk("C06: env selects weknora (no if/else in tools)",
              sel.name == "weknora")
        served_mock = None
        raised = False
        try:
            served_mock = sel.search(QUERY)
        except ProviderUnavailable:
            raised = True
        c.chk("C06: weknora failure raises — NEVER serves mock results",
              raised and served_mock is None)

        os.environ[PROVIDER_ENV] = "bogus_backend"
        reset_default_provider()
        raised = False
        try:
            default_provider()
        except ProviderConfigError:
            raised = True
        c.chk("C06: unknown provider name → ProviderConfigError "
              "(no fallback to mock)", raised)
        raised = False
        try:
            build_named_provider("")
        except ProviderConfigError:
            raised = True
        c.chk("C06: empty provider name fails closed, not defaulted", raised)

        # explicit injection (composition root) wins over env
        os.environ[PROVIDER_ENV] = "weknora"
        mock = MockKnowledgeProvider()
        set_default_provider(mock)
        c.chk("S3: explicit injection wins over env",
              default_provider() is mock)
        reset_default_provider()
        c.chk("S3: reset falls back to env selection",
              default_provider().name == "weknora")
    finally:
        reset_default_provider()
        if saved is None:
            os.environ.pop(PROVIDER_ENV, None)
        else:
            os.environ[PROVIDER_ENV] = saved
    c.chk("S3: default selection without env is the offline mock",
          default_provider().name == "mock")


# ------------------------------------------------------------------ #
# S4 — C09 provenance preservation · C11 interchangeability (§十六)
# ------------------------------------------------------------------ #
@section
def test_s4_provenance_and_interchangeability(c: Checks):
    mock_res = MockKnowledgeProvider().search(QUERY)
    wk_res = WeKnoraKnowledgeProvider(
        transport=fake_weknora_transport).search(QUERY)
    for name, res in (("mock", mock_res), ("weknora-fake", wk_res)):
        d = res.to_dict()
        c.chk("C09: %s preserves chunk/document/section/source_level"
              % name, all(
                  r.get("chunk_id") and r.get("document_id")
                  and "section" in r and "source_level" in r
                  for r in d["results"]))
        c.chk("C09: %s carries content_hash + version slot" % name, all(
            r.get("content_hash") and "version_id" in r
            for r in d["results"]))
        artifact = to_canonical(d)
        ok, errs = validate_evidence(artifact)
        c.chk("C11: %s canonical artifact schema-valid" % name, ok, errs[:3])
    # downstream must not depend on provider-specific values — only on
    # the shared canonical STRUCTURE
    m, w = mock_res.to_dict(), wk_res.to_dict()
    c.chk("C11: same top-level canonical keys",
          set(m.keys()) == set(w.keys()))
    c.chk("C11: same evidence-item key sets downstream",
          {k for k in to_canonical(m)["payload"]["evidence"][0]}
          == {k for k in to_canonical(w)["payload"]["evidence"][0]})
    c.chk("C11: provider identity confined to retrieval_metadata",
          m["retrieval_metadata"]["provider"] == "mock"
          and w["retrieval_metadata"]["provider"] == "weknora"
          and "provider" not in m["results"][0]
          and "provider" not in w["results"][0])
    # content hashes verify against the content actually returned
    c.chk("C09: content_hash verifies (sha256 of content)",
          all(h.content_hash == KnowledgeHit.hash_content(h.content)
              for h in wk_res.results))


# ------------------------------------------------------------------ #
# S5 — C07 Ask isolation · boundary structure · tool wiring
# ------------------------------------------------------------------ #
@section
def test_s5_ask_isolation_and_boundaries(c: Checks):
    banned_methods = [n for n in dir(WeKnoraKnowledgeProvider)
                      if n.split("_")[0].lower() in
                      ("ask", "chat", "react", "answer", "agent", "llm")]
    c.chk("C07: no ask/chat/react/answer method on the adapter",
          banned_methods == [], banned_methods)
    src = inspect.getsource(sys.modules["knowledge.provider.weknora"])
    c.chk("C07: adapter source defines no LLM-answer entry point",
          "def ask" not in src and "def chat" not in src
          and "def react" not in src and "def answer" not in src)
    c.chk("C07: adapter performs no network I/O in 14.1 (no client "
          "imports)",
          "import requests" not in src and "import httpx" not in src
          and "import urllib" not in src and "import mcp" not in src
          and "from mcp" not in src
          and "from requests" not in src and "from httpx" not in src)

    # boundary direction: the provider package never imports runtime
    import knowledge.provider as pkg
    pkg_dir = os.path.dirname(pkg.__file__)
    offenders = []
    for fn in os.listdir(pkg_dir):
        if not fn.endswith(".py"):
            continue
        with open(os.path.join(pkg_dir, fn), encoding="utf-8") as f:
            body = f.read()
        if "from runtime" in body or "import runtime" in body:
            offenders.append(fn)
    c.chk("S5: provider package imports no runtime module", offenders == [],
          offenders)

    # tool wiring: the tool talks to the boundary, not to an engine
    # (Phase 14.4: the boundary is the KnowledgeService — provider +
    # governance composition; the no-direct-engine invariant holds)
    with open(os.path.join(REPO, "runtime", "agent", "tools.py"),
              encoding="utf-8") as f:
        tool_src = f.read()
    c.chk("S5: knowledge tool uses the service boundary (no engine "
          "import)", ("default_service" in tool_src
                      or "default_provider" in tool_src)
          and "from knowledge.evidence.provider import build_engine"
          not in tool_src)
    c.chk("S5: tool fail-closes on ProviderError (no silent fallback)",
          "ProviderError" in tool_src and "_fail" in tool_src)

    # the orchestrator's evidence-service path is untouched (14.5 item)
    import knowledge.evidence.provider as evp
    c.chk("S5: evidence-provider seam unchanged (build_engine intact)",
          hasattr(evp, "build_engine")
          and hasattr(evp, "provide_evidence"))

    # ProviderError taxonomy is one family (catchable at the seam)
    c.chk("S5: error taxonomy shares the ProviderError base",
          issubclass(ProviderUnavailable, ProviderError)
          and issubclass(ProviderConfigError, ProviderError)
          and issubclass(ProviderResponseInvalid, ProviderError))


def main():
    return run_sections(SECTIONS, "p14_provider_contract_log.txt",
                        "STAGE 14.1 PROVIDER CONTRACT")


if __name__ == "__main__":
    sys.exit(main())
