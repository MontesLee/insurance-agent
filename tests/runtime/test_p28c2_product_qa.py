"""Phase 28.C-2 — Product QA Agent minimal production loop tests.

Mandated scenarios (28.C-2 spec Step 4):
  A product exists            -> grounded (catalog record + qualifying
    governed evidence; spec example name "健康满分" does not exist in the
    demo catalog — the same question shape runs against the real P001)
  B product does not exist    -> refused insufficient_evidence
  C WeKnora unavailable       -> refused kb_unavailable
  D LLM unavailable           -> refused llm_unavailable
  E uncited generation        -> citation gate reject (one regeneration)
  F product questions never enter the plan workflow

Plus: D6 parameter fail-closed, context resolution, slice flag (default
OFF), shared-grounding shims, schema product_ref contract, classifier
catalog-name signal, corpus regression. All offline.
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

from knowledge.provider.base import ProviderUnavailable  # noqa: E402
from knowledge.service import (  # noqa: E402
    KnowledgeService, reset_default_service, set_default_service)
from runtime.agent import FakeLLMProvider  # noqa: E402
from runtime.grounding import context as gctx  # noqa: E402
from runtime.grounding import gate as ggate  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.llm.mock import MockLLMProvider  # noqa: E402
from runtime.product_qa_agent import (  # noqa: E402
    product_qa_slice_enabled, run_product_qa_turn)

P001_MSG = "demo-百万医疗险A的等待期多久"
GOOD_A = ("目录未列出该产品专项等待期[E1]；关联资料显示百万医疗险常见等待期"
          "为30天，等待期内出险一般不予赔付[E2]。")


def _ir(msg=P001_MSG):
    reset_default_service()
    ir = classify(msg)
    assert ir["intent_id"] == "product_qa", ir
    return ir


def _gw(content=GOOD_A, fail_with=""):
    return LLMGateway(MockLLMProvider(content=content, fail_with=fail_with),
                      max_retries=0)


# --------------------------------------------------------------------------
# mandated scenario A — product exists -> grounded (catalog + evidence)
# --------------------------------------------------------------------------

def test_scenario_a_product_exists_grounded():
    ctx = run_product_qa_turn(P001_MSG, _ir(), gateway=_gw())
    assert ctx["grounding_status"] == "grounded", ctx["failure_reason"]
    assert ctx["failure_reason"] is None and ctx["evidence_refs"]
    assert not gctx.validate(ctx)
    # E1 is the deterministic version-pinned catalog record
    e1 = ctx["evidence_map"]["E1"]
    assert e1["source_type"] == "catalog" and e1["document_id"] == "P001"
    assert e1["version_id"].startswith("catalog:")
    # E2 is governed evidence qualifying for P001 (linked doc)
    assert "E2" in ctx["evidence_map"]
    assert ctx["evidence_map"]["E2"]["document_id"] != "P001"
    assert ctx["evidence_map"]["E2"].get("chunk_id") != "catalog-record"
    # product resolution recorded
    assert ctx["product_ref"] == {
        "resolved": True, "product_id": "P001",
        "product_name": "demo-百万医疗险A（标准版）",
        "matched_by": "product_name"}
    # the catalog record content is the rendered product facts
    ev1_content = ctx["answer"]  # sanity: answer exists
    assert ev1_content


def test_catalog_parameter_relay_grounded():
    # a parameter the catalog DOES have (deductible 10000元 in constraints)
    msg = "demo-百万医疗险A的免赔额是多少"
    good = "该产品的免赔额为10000元[E1]。"
    ctx = run_product_qa_turn(msg, _ir(msg), gateway=_gw(content=good))
    assert ctx["grounding_status"] == "grounded", ctx["failure_reason"]
    assert ctx["evidence_refs"] == ["E1"]      # catalog record suffices
    assert not gctx.validate(ctx)


def test_d6_parameter_missing_fails_closed():
    # P009 accident product: constraints empty, linked doc has no 等待期
    msg = "demo-综合意外险A的等待期多久"
    ctx = run_product_qa_turn(msg, _ir(msg), gateway=_gw())
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "catalog_missing_fact"
    assert ctx["product_ref"]["product_id"] == "P009"
    assert not gctx.validate(ctx)
    assert "目录暂无该数据" in ctx["answer"]


def test_context_resolution_for_demonstrative_followups():
    ir = _ir(P001_MSG)
    ctx = run_product_qa_turn(
        "那款等待期多久", ir,
        conversation_context=["我想了解demo-重疾险B（终身）"],
        gateway=_gw(content="该重疾险等待期参见关联资料[E1]。"))
    assert ctx["product_ref"]["product_id"] == "P005"
    assert ctx["product_ref"]["matched_by"] == "context_product_name"


# --------------------------------------------------------------------------
# mandated scenario B — product does not exist
# --------------------------------------------------------------------------

def test_scenario_b_product_missing_insufficient():
    msg = "长生不老保XYZ这个产品怎么样"
    ctx = run_product_qa_turn(msg, _ir(msg), gateway=_gw())
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "insufficient_evidence"
    assert ctx["product_ref"]["resolved"] is False
    assert not gctx.validate(ctx)


# --------------------------------------------------------------------------
# mandated scenario C — WeKnora (knowledge service) unavailable
# --------------------------------------------------------------------------

class _DeadProvider:
    name = "dead"

    def search(self, query, filters=None, top_k=None):
        raise ProviderUnavailable("knowledge backend down")


def test_scenario_c_kb_unavailable_even_with_catalog():
    ir = _ir()          # classify FIRST (resets stale injections)
    set_default_service(KnowledgeService(provider=_DeadProvider()))
    try:
        ctx = run_product_qa_turn(P001_MSG, ir, gateway=_gw())
    finally:
        reset_default_service()
    # the catalog anchor alone is NOT served around a dead KB (K003)
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "kb_unavailable"
    assert ctx["product_ref"]["resolved"] is True
    assert not gctx.validate(ctx)


# --------------------------------------------------------------------------
# mandated scenario D — LLM unavailable
# --------------------------------------------------------------------------

def test_scenario_d_llm_unavailable():
    for kind in ("timeout", "500", "429"):
        ctx = run_product_qa_turn(P001_MSG, _ir(),
                                  gateway=_gw(fail_with=kind))
        assert ctx["grounding_status"] == "refused", (kind, ctx)
        assert ctx["failure_reason"] == "llm_unavailable", kind


# --------------------------------------------------------------------------
# mandated scenario E — uncited generation -> gate ladder
# --------------------------------------------------------------------------

def test_scenario_e_uncited_generation_rejected():
    bad = "这款产品等待期三十天，非常值得购买。"   # facts, zero citations
    ctx = run_product_qa_turn(P001_MSG, _ir(), gateway=_gw(content=bad))
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "citation_gate_rejected"
    assert ctx["generation_provenance"]["attempts"] == 2
    assert any(v.startswith("fact_sentence:no_citation")
               for v in ctx["generation_provenance"]["gate_violations"])
    assert not gctx.validate(ctx)


def test_scenario_e_regeneration_recovers():
    class _TwoShot:
        name = "two-shot"

        def __init__(self):
            self.n = 0

        def generate(self, request):
            from runtime.llm.types import LLMResponse, LLMUsage
            self.n += 1
            return LLMResponse(
                request_id=request.request_id, provider=self.name,
                model="m",
                content=("等待期是三十天。" if self.n == 1 else GOOD_A),
                usage=LLMUsage(1, 1, 2))

    ctx = run_product_qa_turn(P001_MSG, _ir(),
                              gateway=LLMGateway(_TwoShot(), max_retries=0))
    assert ctx["grounding_status"] == "grounded", ctx
    assert ctx["generation_provenance"]["attempts"] == 2


# --------------------------------------------------------------------------
# mandated scenario F — product questions never enter the plan workflow
# --------------------------------------------------------------------------

def test_f_product_questions_classify_product_qa_not_plan():
    for msg in ("demo-重疾险B多少钱", "P001是什么产品", "这款产品的等待期多久"):
        assert classify(msg)["intent_id"] == "product_qa", msg
    # and plan requests still classify plan (unaffected)
    assert classify("帮我规划保险")["intent_id"] == "insurance_plan"


def test_f_server_slice_never_touches_workflow():
    os.environ["INSURANCE_AGENT_PRODUCT_QA_SLICE"] = "1"
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider([GOOD_A])
        rid = client.post("/api/chats/chat_pq/messages",
                          json={"text": P001_MSG}).json()["run_id"]
        run = wait_terminal(client, rid)
        assert run["status"] == "completed"
        assert run["result_status"] == "QA_ANSWERED", run
        evs = client.get("/api/runs/%s/events" % rid).json()["events"]
        types = [e["event_type"] for e in evs]
        # NO workflow entry: no stages, no planner, no agent tool loop
        for banned in ("stage_started", "planner_started",
                       "agent_step_started", "tool_started"):
            assert banned not in types, (banned, types)
        qa = [e for e in evs if e["event_type"] == "qa_answered"]
        assert qa and qa[0]["data"]["slice"] == "product-qa"
        assert qa[0]["data"]["grounding_status"] == "grounded"
        rec = json.load(open(os.path.join(mgr.run_root, rid,
                                          "qa-answer-context.json"),
                             encoding="utf-8"))
        assert rec["product_ref"]["product_id"] == "P001"
        assert not gctx.validate(rec)
    finally:
        del os.environ["INSURANCE_AGENT_PRODUCT_QA_SLICE"]
    # default OFF: same message runs the EXISTING agent path
    client2, mgr2, _b2 = make_client()
    mgr2.agent_provider = FakeLLMProvider([GOOD_A])
    rid2 = client2.post("/api/chats/chat_pq_off/messages",
                        json={"text": P001_MSG}).json()["run_id"]
    run2 = wait_terminal(client2, rid2)
    assert run2["result_status"] != "QA_ANSWERED"
    evs2 = client2.get("/api/runs/%s/events" % rid2).json()["events"]
    assert not [e for e in evs2 if e["event_type"] == "qa_answered"]
    from runtime.intent import shadow as sh
    recs = [r for r in sh.iter_records() if r.get("run_id") == rid2]
    assert recs and recs[0]["actual_execution"] == "existing-agent"


def test_slice_flag_default_off():
    assert product_qa_slice_enabled({}) is False
    assert product_qa_slice_enabled(
        {"INSURANCE_AGENT_PRODUCT_QA_SLICE": "1"}) is True


# --------------------------------------------------------------------------
# shared-grounding extraction + classifier signal + schema contract
# --------------------------------------------------------------------------

def test_qa_agent_shims_still_expose_shared_surface():
    from runtime.qa_agent import context as old_ctx, gate as old_gate
    assert old_gate.load_rules is ggate.load_rules
    assert old_ctx.validate is gctx.validate
    assert old_ctx.refused is gctx.refused


def test_classifier_catalog_name_signal_and_corpus_regression():
    r = classify(P001_MSG)
    assert r["intent_id"] == "product_qa"
    assert "rule:product_qa_catalog_name:P001" in r["reason_codes"]
    assert classify("P012是什么产品")["intent_id"] == "product_qa"
    # no false positive: category words are not product names
    assert classify("百万医疗险是什么")["intent_id"] == "insurance_qa"
    from runtime.intent.report import CORPUS
    for msg, expected, _ in CORPUS:
        assert classify(msg)["intent_id"] == expected, (msg, expected)


def test_schema_product_ref_contract():
    with open(os.path.join(REPO, "schema", "qa-answer-context.schema.json"),
              encoding="utf-8") as fh:
        v = Draft7Validator(json.load(fh))
    ctx = run_product_qa_turn(P001_MSG, _ir(), gateway=_gw())
    assert not [e.message for e in v.iter_errors(ctx)]
    bad = json.loads(json.dumps(ctx))
    bad["product_ref"]["matched_by"] = "telepathy"
    assert [e.message for e in v.iter_errors(bad)]
    # knowledge-QA records still valid WITHOUT product_ref (optional)
    from runtime.qa_agent import run_qa_turn
    kctx = run_qa_turn("重疾险的等待期是什么", classify("重疾险的等待期是什么"),
                       gateway=_gw(content="重大疾病保险常见等待期为90天[E1]。"))
    assert "product_ref" not in kctx
    assert not [e.message for e in v.iter_errors(kctx)]


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
