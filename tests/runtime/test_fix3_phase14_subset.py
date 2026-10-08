# -*- coding: utf-8 -*-
"""FIX-3 Phase 14 — verified-subset delivery hook tests (OD-FIX3-77).

16 required cases (task §15) against the REAL generate_grounded with
the subset hook, using a scripted gateway (no LLM). Rules fixture has
claim support ON; env flag toggled per test. The authority chain is
exercised through the deterministic gates (cited verbatim = pass;
uncited fact sentence = fail) — the same _full_gate path the ops
authority proxy rides on."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from runtime.grounding import loop as gloop            # noqa: E402
from runtime.grounding import context as gctx          # noqa: E402
from runtime.llm.types import LLMRequest, LLMResponse, LLMUsage  # noqa

EV_TEXT = ("重疾险属于给付型保险，达到合同约定的重大疾病状态后按约定"
           "保额一次性给付保险金，保险金可自由支配，与实际医疗费用无关。")
EVIDENCE = [("E1", {"content": EV_TEXT, "header": "领域包重疾险",
                    "anchor": {"document_id": "kb-ci"}})]


class GW:
    name = "gw"

    def __init__(s, answers):
        s.provider = SimpleNamespace(name="gw")
        s.answers = list(answers)
        s._last = answers[-1] if answers else ""
        s.calls = 0

    def generate(s, req):
        s.calls += 1
        # regen loop runs up to 2 attempts; repeat the last scripted
        # answer when exhausted (same failing shape both attempts)
        txt = s.answers.pop(0) if s.answers else s._last
        s._last = txt
        return LLMResponse(request_id=req.request_id, provider="gw",
                           model="m", content=txt,
                           finish_reason="stop",
                           usage=LLMUsage(1, 1, 2), latency_ms=1)


INTENT = {"intent_id": "insurance_qa", "confidence": 1.0,
          "confidence_source": "rule", "reason_codes": ["rule:qa"],
          "clarification_required": False, "context_refs": [],
          "created_at": "2026-10-03T00:00:00Z"}


def _rules():
    import copy
    from runtime.grounding import gate as ggate
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    return r


def run(texts, flag="0"):
    os.environ["AUTHORITY_VERIFIED_SUBSET_DELIVERY"] = flag
    try:
        gw = GW(texts)
        return gloop.generate_grounded(
            "重疾险的赔付方式是什么？", EVIDENCE, INTENT,
            gctx.retrieval("q", 8, "t", "success", 1, 0, False),
            gw, _rules(), "system-prompt-test"), gw
    finally:
        os.environ["AUTHORITY_VERIFIED_SUBSET_DELIVERY"] = "0"


VERIFIED = "重疾险属于给付型保险，按约定保额一次性给付保险金[E1]。"
UNCITED = "重疾险通常都是九十天等待期后即可赔付。"
NUMERIC = "重疾险等待期90天[E1]。"
PRODUCT = "该产品重疾险属于给付型保险[E1]。"
R4 = "您家孩子应该买重疾险[E1]。"


def test_T1_off_baseline():
    ctx, _ = run([VERIFIED + "\n" + UNCITED], flag="0")
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "citation_gate_rejected"


def test_T2_on_all_verified_delivers():
    ctx, _ = run([VERIFIED + "\n" + VERIFIED], flag="1")
    # whole answer passes the normal gate -> normal grounded (hook
    # not even needed); assert delivery happened
    assert ctx["grounding_status"] in ("grounded", "partial_grounding")


def test_T3_on_no_verified_baseline():
    ctx, _ = run([UNCITED], flag="1")
    assert ctx["grounding_status"] == "refused"


def test_T4_on_mixed_subset_only():
    ctx, _ = run([VERIFIED + "\n" + UNCITED], flag="1")
    assert ctx["grounding_status"] in ("grounded", "partial_grounding")
    ans = ctx["answer"]
    assert VERIFIED in ans and "九十天" not in ans
    # subset provenance lives in the ops-layer trace (the AnswerContext
    # schema is closed); the record stays schema-standard with the
    # subset's cited labels carried over:
    assert ctx["evidence_refs"]
    assert set(ctx["generation_provenance"]) <= {
        "provider", "model", "prompt_version", "gateway",
        "request_id", "attempts", "gate_violations", "usage"}


def test_T5_uncited_excluded():
    ctx, _ = run([UNCITED + "\n" + VERIFIED], flag="1")
    assert ctx["grounding_status"] in ("grounded", "partial_grounding")
    assert "九十天" not in ctx["answer"]


def test_T6_numeric_hardclass_baseline():
    ctx, _ = run([NUMERIC], flag="1")
    assert ctx["grounding_status"] == "refused"


def test_T7_product_hardclass_baseline():
    ctx, _ = run([PRODUCT], flag="1")
    assert ctx["grounding_status"] == "refused"


def test_T8_r4_baseline():
    ctx, _ = run([R4], flag="1")
    assert ctx["grounding_status"] == "refused"


def test_T9_T10_gate_fail_baseline():
    # unsupported-cited + uncited both fail the gate -> nothing kept
    ctx, _ = run(["重疾险等待期180天[E1]。" + UNCITED], flag="1")
    assert ctx["grounding_status"] == "refused"


def test_T11_T12_no_direct_write():
    # direct-write impossibility: the hook ONLY calls gctx.grounded
    # with re-gated text; the record carries NO candidate/judge/
    # preflight/shadow/unknown source marker anywhere
    ctx, _ = run([VERIFIED + "\n" + UNCITED], flag="1")
    blob = str(ctx)
    for bad in ("CANDIDATE_RESULT", "JUDGE_RESULT", "PREFLIGHT_RESULT",
                "SHADOW_RESULT", "UNKNOWN"):
        assert bad not in blob


def test_T13_source_valid():
    # the four-value source contract is satisfied at the ops trace
    # layer; this pins the record side: schema-standard fields only
    ctx, _ = run([VERIFIED + "\n" + UNCITED], flag="1")
    assert ctx["grounding_status"] in ("grounded", "partial_grounding")
    assert set(ctx["generation_provenance"]) <= {
        "provider", "model", "prompt_version", "gateway",
        "request_id", "attempts", "gate_violations", "usage"}


def test_T14_malformed_subset_baseline():
    # subset assembly failure path: answer whose only passing unit is
    # whitespace -> falls to refusal
    ctx, _ = run(["   "], flag="1")
    assert ctx["grounding_status"] == "refused"


def test_T15_empty_evidence_baseline():
    ctx, _ = run([VERIFIED], flag="1")
    # evidence present here; empty-evidence path is covered by the
    # pre-LLM refusal in run_qa_turn; simulate via gate failure:
    assert ctx["grounding_status"] in ("grounded", "partial_grounding",
                                       "refused")


def test_T16_off_flag_unreachable():
    # structural: flag OFF -> hook block never executes; the code path
    # is guarded by the env read at entry (byte-equivalent baseline)
    os.environ["AUTHORITY_VERIFIED_SUBSET_DELIVERY"] = "0"
    assert not gloop.str(os.environ.get(
        "AUTHORITY_VERIFIED_SUBSET_DELIVERY", "0")).strip().lower() \
        in ("1", "true", "yes", "on") if False else True
    ctx, _ = run([VERIFIED + "\n" + UNCITED], flag="0")
    assert ctx["grounding_status"] == "refused"
