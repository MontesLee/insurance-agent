"""Phase 28.C-1 — Insurance QA Agent minimal production loop tests.

Mandated scenarios (28.C-1 spec §4):
  A insurance knowledge question with evidence      -> grounded
  B insufficient evidence                            -> refused
  C WeKnora (knowledge service) unavailable          -> refused kb_unavailable
  D LLM unavailable                                  -> refused llm_unavailable
  E hallucinated citation                            -> gate reject -> (one
    regeneration) -> refuse

Plus: gate units, AnswerContext contract constraints, slice wiring e2e.
All offline: mock knowledge composition (fixtures KB + governance) and
the gateway's MockLLMProvider / scripted FakeLLMProvider — never a live
endpoint.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _common import make_client, wait_terminal  # noqa: E402

from jsonschema import Draft7Validator  # noqa: E402

from knowledge.provider.base import (  # noqa: E402
    KnowledgeHit, KnowledgeSearchResult, ProviderUnavailable)
from knowledge.service import (  # noqa: E402
    KnowledgeService, reset_default_service, set_default_service)
from runtime.agent import FakeLLMProvider  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.llm.mock import MockLLMProvider  # noqa: E402
from runtime.qa_agent import context as qa_ctx  # noqa: E402
from runtime.qa_agent import gate as qa_gate  # noqa: E402
from runtime.qa_agent import run_qa_turn  # noqa: E402

QA_MSG = "重疾险的等待期是什么"
GOOD_ANSWER = ("重大疾病保险常见等待期为90天[E1]。"
               "等待期内确诊重疾一般仅退还保费[E1]。")


def _ir():
    reset_default_service()
    return classify(QA_MSG)


def _gw(content=GOOD_ANSWER, fail_with=""):
    return LLMGateway(MockLLMProvider(content=content, fail_with=fail_with),
                      max_retries=0)


# --------------------------------------------------------------------------
# mandated scenario A — knowledge question WITH evidence -> grounded
# --------------------------------------------------------------------------

def test_scenario_a_grounded_answer():
    ctx = run_qa_turn(QA_MSG, _ir(), gateway=_gw())
    assert ctx["grounding_status"] == "grounded", ctx["failure_reason"]
    assert ctx["failure_reason"] is None
    assert ctx["evidence_refs"], "grounded must cite >=1 evidence"
    assert set(ctx["evidence_refs"]) <= set(ctx["evidence_map"])
    assert ctx["answer"] == GOOD_ANSWER
    assert not qa_ctx.validate(ctx)
    # provenance: through the gateway (ruling D2)
    g = ctx["generation_provenance"]
    assert g["gateway"] is True and g["attempts"] == 1 and g["request_id"]
    # retrieval block reflects governed reality
    r = ctx["retrieval"]
    assert r["allowed_count"] >= 1 and r["governed_status"] == "success"
    # evidence anchors carry the citation tuple
    a = ctx["evidence_map"][ctx["evidence_refs"][0]]
    assert a["chunk_id"] and a["source_name"] and a["content_hash"]


# --------------------------------------------------------------------------
# mandated scenario B — insufficient evidence -> honest refusal
# --------------------------------------------------------------------------

def test_scenario_b_insufficient_evidence():
    ctx = run_qa_turn("量子保险精算的布里渊区是什么", _ir(), gateway=_gw())
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "insufficient_evidence"
    assert ctx["evidence_refs"] == []
    assert not qa_ctx.validate(ctx)
    assert "暂无可靠依据" in ctx["answer"]       # honest-refusal template


# --------------------------------------------------------------------------
# mandated scenario C — knowledge service unavailable -> fail closed
# --------------------------------------------------------------------------

class _DeadProvider:
    name = "dead"

    def search(self, query, filters=None, top_k=None):
        raise ProviderUnavailable("knowledge backend down")


def test_scenario_c_kb_unavailable():
    ir = _ir()          # classify FIRST (also resets any stale injection)
    set_default_service(KnowledgeService(provider=_DeadProvider()))
    try:
        ctx = run_qa_turn(QA_MSG, ir, gateway=_gw())
    finally:
        reset_default_service()
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "kb_unavailable"
    assert not qa_ctx.validate(ctx)
    # no silent fallback: the answer is the refusal template, not a guess
    assert "不可用" in ctx["answer"]


# --------------------------------------------------------------------------
# mandated scenario D — LLM unavailable -> fail closed
# --------------------------------------------------------------------------

def test_scenario_d_llm_unavailable():
    for kind in ("timeout", "500", "429"):
        ctx = run_qa_turn(QA_MSG, _ir(),
                          gateway=_gw(fail_with=kind))
        assert ctx["grounding_status"] == "refused", (kind, ctx)
        assert ctx["failure_reason"] == "llm_unavailable", kind
        assert not qa_ctx.validate(ctx)


# --------------------------------------------------------------------------
# mandated scenario E — hallucinated citation -> gate ladder
# --------------------------------------------------------------------------

def test_scenario_e_hallucinated_citation_refuses():
    bad = "重疾险等待期一般是180天，确诊后马上赔付[E9]。"
    ctx = run_qa_turn(QA_MSG, _ir(), gateway=_gw(content=bad))
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "citation_gate_rejected"
    assert ctx["generation_provenance"]["attempts"] == 2   # 1 + 1 regen
    assert "citation:not_in_evidence:E9" in \
        ctx["generation_provenance"].get("gate_violations", [])
    assert ctx["evidence_refs"] == []
    assert not qa_ctx.validate(ctx)


def test_scenario_e_regeneration_recovers():
    # first attempt hallucinates, the ONE allowed regeneration fixes it
    class _TwoShot:
        name = "two-shot"

        def __init__(self):
            self.n = 0

        def generate(self, request):
            from runtime.llm.types import LLMResponse, LLMUsage
            self.n += 1
            text = ("重疾险等待期一般是180天[E9]。" if self.n == 1
                    else GOOD_ANSWER)
            return LLMResponse(request_id=request.request_id,
                               provider=self.name, model="m", content=text,
                               usage=LLMUsage(1, 1, 2))

    ctx = run_qa_turn(QA_MSG, _ir(), gateway=LLMGateway(_TwoShot(),
                                                        max_retries=0))
    assert ctx["grounding_status"] == "grounded", ctx
    assert ctx["generation_provenance"]["attempts"] == 2
    assert ctx["evidence_refs"] == ["E1"]


# --------------------------------------------------------------------------
# gate units (deterministic closure rules)
# --------------------------------------------------------------------------

def test_gate_fact_sentence_without_citation():
    v = qa_gate.check("重大疾病保险的等待期为90天。", {"E1": {}})
    assert not v["ok"] and any(x.startswith("fact_sentence:no_citation")
                               for x in v["violations"]), v


def test_gate_non_fact_sentence_needs_no_citation():
    v = qa_gate.check("希望这些信息对您有帮助。", {"E1": {}})
    assert v["ok"], v


def test_gate_unknown_label_rejected_known_accepted():
    v = qa_gate.check("等待期为90天[E2]。", {"E1": {}})
    assert not v["ok"] and "citation:not_in_evidence:E2" in v["violations"]
    v2 = qa_gate.check("等待期为90天[E1]。", {"E1": {}})
    assert v2["ok"] and v2["cited"] == ["E1"]


def test_gate_empty_answer_and_split():
    assert qa_gate.check("", {"E1": {}})["violations"] == ["answer:empty"]
    segs = qa_gate.split_sentences("第一句[E1]。第二句！第三句？")
    assert len(segs) == 3
    assert qa_gate.extract_citations("a[E1] b[E02]") == ["E1", "E2"]


def test_gate_rules_externalized_and_versioned():
    r = qa_gate.load_rules()
    assert r["version"] == 1
    assert os.path.exists(os.path.join(REPO, "config",
                                       "qa-grounding-rules.yaml"))
    assert r["gate"]["max_regenerations"] == 1


# --------------------------------------------------------------------------
# AnswerContext contract (closed schema, status/reason coupling)
# --------------------------------------------------------------------------

def _schema():
    with open(os.path.join(REPO, "schema", "qa-answer-context.schema.json"),
              encoding="utf-8") as fh:
        return Draft7Validator(json.load(fh))


def test_schema_rejects_structural_violations():
    v = _schema()
    base = json.loads(json.dumps(_grounded_fixture()))
    assert not [e.message for e in v.iter_errors(base)]
    # extra key (closed contract)
    bad = json.loads(json.dumps(base)); bad["agent"] = "insurance-qa-agent"
    assert [e.message for e in v.iter_errors(bad)]
    # grounded with a failure_reason
    bad = json.loads(json.dumps(base)); bad["failure_reason"] = "llm_unavailable"
    assert [e.message for e in v.iter_errors(bad)]
    # grounded with zero evidence_refs
    bad = json.loads(json.dumps(base)); bad["evidence_refs"] = []
    assert [e.message for e in v.iter_errors(bad)]
    # refused with null reason / with refs / bogus reason value
    bad = json.loads(json.dumps(base))
    bad["grounding_status"] = "refused"; bad["failure_reason"] = None
    assert [e.message for e in v.iter_errors(bad)]
    bad = json.loads(json.dumps(base))
    bad["grounding_status"] = "refused"; bad["failure_reason"] = "nope"
    assert [e.message for e in v.iter_errors(bad)]
    # non-label evidence_map key
    bad = json.loads(json.dumps(base))
    bad["evidence_map"] = {"X1": base["evidence_map"]["E1"]}
    assert [e.message for e in v.iter_errors(bad)]


def _grounded_fixture() -> dict:
    ctx = run_qa_turn(QA_MSG, _ir(), gateway=_gw())
    assert ctx["grounding_status"] == "grounded"
    return ctx


def test_invalid_intent_input_fails_closed():
    # product_qa / malformed intents never enter the QA loop
    pr = classify("P001是什么产品")
    assert pr["intent_id"] == "product_qa"
    ctx = run_qa_turn("P001是什么产品", pr, gateway=_gw())
    assert ctx["failure_reason"] == "invalid_input"
    ctx2 = run_qa_turn(QA_MSG, {"intent_id": "bogus"}, gateway=_gw())
    assert ctx2["failure_reason"] == "invalid_input"
    assert not qa_ctx.validate(ctx2)


def test_conflicting_sources_presented_not_averaged():
    from knowledge.governance import SourceRegistry
    import hashlib

    def hit(doc, chunk, content, version_id):
        return KnowledgeHit(chunk_id=chunk, document_id=doc, content=content,
                            document_name=doc, source_type="regulation",
                            source_level="B", version_id=version_id,
                            content_hash=KnowledgeHit.hash_content(content),
                            score=0.9)

    h1 = hit("doc_a", "doc_a_001", "某产品等待期为90天。", "s-doc_a@1")
    h2 = hit("doc_b", "doc_b_001", "同类产品等待期为180天。", "s-doc_b@1")

    def entry(doc):
        return {"document_id": doc, "source_id": "s-" + doc,
                "source_name": "源-" + doc, "version": "1",
                "authority_level": "B", "jurisdiction": "CN",
                "effective_from": "2024-01-01", "effective_to": None,
                "status": "ACTIVE", "license_status": "ALLOWED",
                "content_hashes": {}}

    e1, e2 = entry("doc_a"), entry("doc_b")
    e1["content_hashes"] = {"doc_a_001": h1.content_hash}
    e2["content_hashes"] = {"doc_b_001": h2.content_hash}

    class _ConflictProvider:
        name = "conflict-mock"

        def search(self, query, filters=None, top_k=None):
            return KnowledgeSearchResult(
                status="success", query=query, results=[h1, h2],
                conflict=True,
                retrieval_metadata={"governance": {"allowed": 2}})

    svc = KnowledgeService(provider=_ConflictProvider(),
                           registry=SourceRegistry([e1, e2]))
    ctx = run_qa_turn("等待期是多久", _ir(), service=svc, gateway=_gw())
    assert ctx["retrieval"]["conflict"] is True
    if ctx["grounding_status"] == "grounded":
        # deterministic both-sides template: BOTH docs cited, nothing averaged
        assert {"E1", "E2"} <= set(ctx["evidence_refs"])
        assert "90" in ctx["answer"] and "180" in ctx["answer"]
        assert not qa_ctx.validate(ctx)
    else:
        assert ctx["failure_reason"] in ("citation_gate_rejected",)


# --------------------------------------------------------------------------
# slice wiring e2e (D4: first Intent->Agent production slice)
# --------------------------------------------------------------------------

def test_qa_slice_e2e_via_server():
    client, mgr, _bus = make_client()
    mgr.agent_provider = FakeLLMProvider([GOOD_ANSWER])
    rid = client.post("/api/chats/chat_qa/messages",
                      json={"text": QA_MSG}).json()["run_id"]
    run = wait_terminal(client, rid)
    assert run["status"] == "completed", run
    assert run["result_status"] == "QA_ANSWERED", run
    # chat carries the grounded answer
    view = client.get("/api/chats/chat_qa").json()
    msgs = view["messages"]
    assert msgs[-1]["role"] == "assistant" and msgs[-1]["content"] == GOOD_ANSWER
    # the audit record is a schema-valid AnswerContext in the run dir
    rec_path = os.path.join(mgr.run_root, rid, "qa-answer-context.json")
    with open(rec_path, encoding="utf-8") as fh:
        rec = json.load(fh)
    assert rec["grounding_status"] == "grounded"
    assert not qa_ctx.validate(rec)
    # shadow record tells the truth about execution
    from runtime.intent import shadow as sh
    recs = [r for r in sh.iter_records() if r.get("run_id") == rid]
    assert recs and recs[0]["actual_execution"] == "insurance-qa-agent"


def test_qa_slice_kill_switch_and_non_qa_paths():
    # env kill-switch: slice off -> the existing agent path answers
    os.environ["INSURANCE_AGENT_QA_SLICE"] = "0"
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider([GOOD_ANSWER])
        rid = client.post("/api/chats/chat_off/messages",
                          json={"text": QA_MSG}).json()["run_id"]
        run = wait_terminal(client, rid)
        assert run["status"] == "completed"
        assert run["result_status"] != "QA_ANSWERED"   # existing path
        from runtime.intent import shadow as sh
        recs = [r for r in sh.iter_records() if r.get("run_id") == rid]
        assert recs and recs[0]["actual_execution"] == "existing-agent"
    finally:
        del os.environ["INSURANCE_AGENT_QA_SLICE"]
    # non-QA intent never enters the slice (plan message -> agent path)
    client2, mgr2, _bus2 = make_client()
    mgr2.agent_provider = FakeLLMProvider([
        ("agent_decide", {"action": "finish", "message": "分析完成。"})])
    rid2 = client2.post("/api/chats/chat_plan/messages",
                        json={"text": "帮我规划保险"}).json()["run_id"]
    run2 = wait_terminal(client2, rid2)
    assert run2["status"] == "completed" and \
        run2["result_status"] != "QA_ANSWERED"


if __name__ == "__main__":
    failures = 0
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s :: %s" % (fn.__name__, exc))
    print("\n%d test(s), %d failure(s)" % (len(fns), failures))
    sys.exit(1 if failures else 0)
