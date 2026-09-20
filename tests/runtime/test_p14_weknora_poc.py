"""Stage 14.2 — WeKnora POC boundary validation (unit/contract level).

REAL WeKnora could NOT be deployed in this environment (no Docker, no
podman, WSL not installed, no remote endpoint) — see
docs/production/phase14-p2-weknora-poc-report.md. This suite therefore
validates the POC gates that do NOT require a live service, honestly
labeled fake-transport level:

  W1 Failure matrix (Cases A/C/D/E with a FAKE transport)
  W2 F-03: TOOL-LEVEL fail-closed behavior (ProviderError → _fail,
     never mock continuation) — the gap left by the 14.1 review
  W3 Ask/ReAct isolation evidence via REQUEST RECORDING (payload
     allowlist + verbatim passage passthrough + source inspection)
  W4 Provider equivalence on the canonical contract (mock vs fake)
  W5 Anti-fabrication: missing optional → empty, missing required →
     raise; NO "unknown"/score=1.0 style defaults

The live-service gates (G1 real retrieval, real response schema) are
covered by tests/runtime/test_p14_weknora_integration.py, which SKIPS
unless a WeKnora endpoint is configured.
"""
from __future__ import annotations

import inspect
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from knowledge.provider import (  # noqa: E402
    KnowledgeFilters, KnowledgeSearchResult, MockKnowledgeProvider,
    ProviderError, ProviderResponseInvalid, ProviderUnavailable,
    WeKnoraKnowledgeProvider, map_weknora_response, reset_default_provider,
    set_default_provider)

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


QUERY = "synthetic medical insurance waiting period"


def syn_doc(i):
    return ("DOC-%03d synthetic passage %d: the synthetic medical "
            "insurance product has a synthetic waiting period of %d0 "
            "days and a synthetic deductible of 10,000." % (i, i, i + 1))


def fake_transport_factory(record):
    def transport(payload):
        record.append(payload)
        n = min(int(payload.get("top_k") or 10), 10)
        return {"results": [
            {"content": syn_doc(i), "score": 0.95 - 0.05 * i,
             "metadata": {"document_id": "SYN-DOC-%03d" % i,
                          "chunk_id": "SYN-DOC-%03d_000" % i,
                          "document_name": "synthetic-%03d" % i,
                          "section": "synthetic",
                          "source_type": "internal",
                          "source_level": "B"}}
            for i in range(n)], "total": n}
    return transport


def to_canonical(d):
    from adapters.knowledge_search_adapter import to_canonical as tc
    return tc(d)


def validate_evidence(artifact):
    from knowledge.evidence.provider import validate, EVIDENCE_SCHEMA
    return validate(artifact, EVIDENCE_SCHEMA)


# ------------------------------------------------------------------ #
# W1 — Failure matrix with FAKE transport (real-service Case B without
#      transport is identical: no transport configured)
# ------------------------------------------------------------------ #
@section
def test_w1_failure_matrix(c: Checks):
    rec = []
    prov = WeKnoraKnowledgeProvider(transport=fake_transport_factory(rec))

    # Case A — normal retrieval → canonical, schema-valid
    res = prov.search(QUERY, top_k=3)
    c.chk("A: retrieval → canonical result",
          isinstance(res, KnowledgeSearchResult) and len(res.results) == 3)
    ok, errs = validate_evidence(to_canonical(res.to_dict()))
    c.chk("A: canonical artifact schema-valid downstream", ok, errs[:3])

    # Case C — invalid responses → fail closed
    for name, raw in {
        "not object": [],
        "missing results": {},
        "results not list": {"results": 1},
        "hit not object": {"results": [7]},
    }.items():
        raised = False
        try:
            map_weknora_response(raw, QUERY)
        except ProviderResponseInvalid:
            raised = True
        c.chk("C: invalid response (%s) → fail closed" % name, raised)

    # Case D — empty result is NOT a provider failure
    empty = map_weknora_response({"results": []}, QUERY)
    c.chk("D: zero hits → insufficient_evidence (not an error)",
          empty.status == "insufficient_evidence" and empty.results == [])

    # Case E — one malformed hit rejects the ENTIRE response
    one_bad = {"results": [
        {"content": syn_doc(0), "score": 0.9,
         "metadata": {"document_id": "SYN-DOC-000",
                      "chunk_id": "SYN-DOC-000_000"}},
        {"content": "x", "score": 0.8, "metadata": {"chunk_id": "c"}},
    ]}
    raised = False
    try:
        map_weknora_response(one_bad, QUERY)
    except ProviderResponseInvalid:
        raised = True
    c.chk("E: malformed hit rejects the whole response (no partial "
          "trust — documented semantics)", raised)


# ------------------------------------------------------------------ #
# W2 — F-03: TOOL-LEVEL fail-closed behavior (behavioral, not grep)
# ------------------------------------------------------------------ #
@section
def test_w2_tool_level_fail_closed(c: Checks):
    from runtime.agent.tools import ToolContext, _knowledge_search
    ctx = ToolContext(state={}, workflow={}, run_id="p14_f03")
    set_default_provider(WeKnoraKnowledgeProvider())  # no transport
    try:
        out = _knowledge_search({"query": QUERY}, ctx)
        c.chk("F-03: tool returns failure on ProviderError",
              out.get("status") == "failed", out)
        c.chk("F-03: failure names fail-closed policy",
              "fail-closed" in out.get("summary", ""), out.get("summary"))
        c.chk("F-03: no evidence artifact written on failure",
              ctx.state.get("artifacts", {}) == {})
        c.chk("F-03: no fabricated knowledge in the failure payload",
              "evidence" not in json.dumps(out)[:400].lower())
    finally:
        reset_default_provider()
    # a generic ProviderError (not just WeKnora) hits the same seam
    class _Exploding:
        name = "exploding"
        def search(self, *a, **k):
            raise ProviderUnavailable("boom")
    set_default_provider(_Exploding())
    try:
        out2 = _knowledge_search({"query": QUERY}, ToolContext(
            state={}, workflow={}, run_id="p14_f03b"))
        c.chk("F-03: any ProviderError family member fails the tool "
              "closed (no mock continuation)",
              out2.get("status") == "failed")
    finally:
        reset_default_provider()
    c.chk("F-03: default restored to offline mock after the test",
          __import__("knowledge.provider", fromlist=["x"])
          .default_provider().name == "mock")


# ------------------------------------------------------------------ #
# W3 — Ask/ReAct isolation: request recording + verbatim passthrough
# ------------------------------------------------------------------ #
@section
def test_w3_ask_isolation_evidence(c: Checks):
    rec = []
    prov = WeKnoraKnowledgeProvider(
        transport=fake_transport_factory(rec), kb_id="syn-kb")
    prov.search(QUERY, top_k=2,
                filters=KnowledgeFilters(domains=["medical"]))
    c.chk("W3: exactly one backend request recorded", len(rec) == 1)
    payload = rec[0]
    c.chk("W3: request payload allowlist (retrieval fields only)",
          set(payload.keys()) <= {"query", "top_k", "kb_id", "filters"},
          sorted(payload.keys()))
    banned = ("ask", "chat", "react", "answer", "llm", "prompt", "model",
              "messages", "stream", "completion")
    blob = json.dumps(payload, ensure_ascii=False).lower()
    c.chk("W3: no LLM-answer concepts in any outbound request",
          not any(b in blob for b in banned), blob[:120])
    res = prov.search(QUERY, top_k=2)
    c.chk("W3: agent receives VERBATIM passages, not composed answers",
          all(h.content.startswith("DOC-") for h in res.results))
    src = inspect.getsource(sys.modules["knowledge.provider.weknora"])
    c.chk("W3: adapter source builds no ask/chat/react endpoint",
          "def ask" not in src and "def chat" not in src
          and "def react" not in src and "def answer" not in src)
    c.chk("W3: no network client in the adapter module",
          "import requests" not in src and "import httpx" not in src
          and "import urllib" not in src and "import mcp" not in src)


# ------------------------------------------------------------------ #
# W4 — Provider equivalence on the canonical contract (§十三)
# ------------------------------------------------------------------ #
@section
def test_w4_provider_equivalence(c: Checks):
    # Chinese query — the mock's CJK trigram index retrieves nothing for
    # English text; equivalence compares canonical SHAPE, not content.
    zh_query = "百万医疗险的等待期一般是多少天"
    mock_res = MockKnowledgeProvider().search(zh_query)
    wk_res = WeKnoraKnowledgeProvider(
        transport=fake_transport_factory([])).search(QUERY)
    m, w = mock_res.to_dict(), wk_res.to_dict()
    c.chk("W4: precondition — both providers returned hits for the "
          "comparison", len(m["results"]) > 0 and len(w["results"]) > 0)
    c.chk("W4: same canonical top-level keys",
          set(m) == set(w), (sorted(m), sorted(w)))
    c.chk("W4: same hit field sets",
          set(m["results"][0]) == set(w["results"][0]))
    c.chk("W4: source identifiers present on both",
          all(r["document_id"] and r["chunk_id"]
              for r in m["results"] + w["results"]))
    c.chk("W4: retrieval_method within the SHARED contract enum",
          m["retrieval_metadata"]["retrieval_method"]
          in ("sparse_rrf", "hybrid_rrf", "unknown")
          and w["retrieval_metadata"]["retrieval_method"]
          in ("sparse_rrf", "hybrid_rrf", "unknown"))
    c.chk("W4: score semantics compatible (numeric, present on both)",
          all(isinstance(r["score"], (int, float))
              for r in m["results"] + w["results"]))
    c.chk("W4: metadata slots are free-form dicts on both",
          isinstance(m["results"][0]["metadata"], dict)
          and isinstance(w["results"][0]["metadata"], dict))
    okm, _ = validate_evidence(to_canonical(m))
    okw, _ = validate_evidence(to_canonical(w))
    c.chk("W4: ONE downstream consumer serves both providers",
          okm and okw)


# ------------------------------------------------------------------ #
# W5 — Anti-fabrication: no guessed defaults anywhere in the mapping
# ------------------------------------------------------------------ #
@section
def test_w5_no_fabricated_defaults(c: Checks):
    no_version = map_weknora_response({"results": [
        {"content": "passage", "score": 0.5,
         "metadata": {"document_id": "d", "chunk_id": "c"}}]}, QUERY)
    h = no_version.results[0]
    c.chk("W5: absent optional version_id → empty string (never "
          "'unknown')", h.version_id == "")
    c.chk("W5: absent optional names → empty strings, not fabricated",
          h.document_name == "" and h.section == "")
    raised = False
    try:
        map_weknora_response({"results": [
            {"content": "passage",
             "metadata": {"document_id": "d", "chunk_id": "c"}}]}, QUERY)
    except ProviderResponseInvalid:
        raised = True
    c.chk("W5: missing required score → raise (never score=1.0)",
          raised)
    ok = map_weknora_response({"results": [
        {"content": "passage", "score": 0,
         "metadata": {"document_id": "d", "chunk_id": "c"}}]}, QUERY)
    c.chk("W5: score 0 is a legitimate value (not treated as missing)",
          ok.results[0].score == 0.0)
    c.chk("W5: content hash always recomputed from the actual content",
          ok.results[0].content_hash
          == ok.results[0].hash_content("passage"))


def main():
    return run_sections(SECTIONS, "p14_weknora_poc_log.txt",
                        "STAGE 14.2 WEKNORA POC (FAKE-TRANSPORT LEVEL)")


if __name__ == "__main__":
    sys.exit(main())
