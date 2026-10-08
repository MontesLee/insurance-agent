# -*- coding: utf-8 -*-
"""FIX-3 Phase 2 production tests — B + D + baseline debt (OD-FIX3-1/2).

Covers the 18 required categories across four arms (C1 / B / D / B+D),
OFF-equivalence (flags off = pre-FIX-3 behavior), rollback, the loop
observation seam (no-op by default), and the shadow judge client's
error-collapse contract. Frozen corpora are referenced READ-ONLY.
"""
from __future__ import annotations

import copy
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from runtime.grounding import claim_support as cs      # noqa: E402
from runtime.grounding import gate as ggate            # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
V2 = os.path.join(REPO, "tests", "golden",
                  "k29c_fix3_benchmark_v2_frozen.jsonl")

EV = dict(source_name="t", document_name="t")


def rules(arm):
    """Real rules, claim support ON, lever flags per arm."""
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    r["claim_support"]["exemption_v2"] = {"enabled": arm in ("B", "BD")}
    r["claim_support"]["premise_scan"] = {"enabled": arm in ("D", "BD")}
    return r


def gate_ok(claim, evidence, arm):
    return cs.check(claim, evidence, rules(arm))["ok"]


def ev(content, **kw):
    d = dict(EV, content=content)
    d.update(kw)
    return d


P004 = ("P004重疾险条款：等待期为90天；投保年龄为出生满28天至60周岁；"
        "被保险人在等待期内确诊重大疾病的，不承担给付责任，仅退还保费。")
CI = ("重疾险属于给付型保险，达到合同约定的重大疾病状态后按约定保额"
      "一次性给付保险金，保险金可自由支配。")


# ---------------- 1-5 paraphrase / overgen / half / negation / contradiction
def test_t03_true_paraphrase_all_arms_rejected_by_deterministic():
    # F1-true: deterministic layer keeps rejecting in EVERY arm
    # (semantic upgrade is NOT part of B/D by design)
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("重疾险的赔付金额与实际医疗费用没有直接关系[E1]",
                       [ev(CI)], arm) is False


def test_t04_over_generalization_rejected_all_arms():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("所有重疾险产品的保险金都可以自由支配[E1]",
                       [ev(CI)], arm) is False


def test_t05_half_truth_rejected_all_arms():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok(
            "P004投保年龄为28天至60周岁，且等待期内确诊也可获赔[E1]",
            [ev(P004, product_id="P004")], arm) is False


def test_t06_negation_not_exempted_by_B():
    # F2-01 shape: exemption must never bypass negation
    assert gate_ok("消费型保险到期可以返还保费[E1]",
                   [ev("消费型保险合同期满后不返还保费。")], "B") is False


def test_t07_contradiction_all_arms():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("该产品等待期为30天[E1]",
                       [ev(P004, product_id="P004")], arm) is False
        assert gate_ok("该产品等待期为180天[E1]",
                       [ev("等待期为90天。", product_id="P004")], arm) is False


# ---------------- 6-11 recommendation+number / numbers / range / unit
def test_t08_recommendation_number_D_defense():
    # unsourced multiple recommendation: C1/B pass (F-1), D/BD block
    assert gate_ok("一般建议重疾保额覆盖3-5倍年收入",
                   [ev("保额应与家庭收入水平相匹配。")], "C1") is True
    assert gate_ok("一般建议重疾保额覆盖3-5倍年收入",
                   [ev("保额应与家庭收入水平相匹配。")], "B") is True
    assert gate_ok("一般建议重疾保额覆盖3-5倍年收入",
                   [ev("保额应与家庭收入水平相匹配。")], "D") is False
    assert gate_ok("一般建议重疾保额覆盖3-5倍年收入",
                   [ev("保额应与家庭收入水平相匹配。")], "BD") is False


def test_t09_unsupported_number_blocked_all_arms():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("重疾险等待期为90天[E1]",
                       [ev("重疾险属于给付型保险。")], arm) is False


def test_t08b_supported_number_recommendation_passes_D():
    # sourced premise: passes in every arm (D verifies, does not block)
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("建议为新生儿投保，因为重疾险出生满28天即可投保[E1]",
                       [ev(P004, product_id="P004")], arm) is True


def test_t10_range_change_not_supported_by_shared_edge():
    # OD-FIX3-2A: "5-10倍" vs evidence "3-5倍" — shared edge 5 must NOT
    # support. C1/B keep the documented F-1 baseline (type exemption);
    # D/BD judge the premise and range containment fails.
    assert gate_ok("建议重疾保额覆盖5-10倍年收入",
                   [ev("一般而言，重疾保额建议覆盖3-5倍年收入。")],
                   "C1") is True
    assert gate_ok("建议重疾保额覆盖5-10倍年收入",
                   [ev("一般而言，重疾保额建议覆盖3-5倍年收入。")],
                   "D") is False
    assert gate_ok("建议重疾保额覆盖5-10倍年收入",
                   [ev("一般而言，重疾保额建议覆盖3-5倍年收入。")],
                   "BD") is False
    # judge-level range relation (C-FACT typed, non-CALC units):
    # contained range passes, expanded fails; in-range value passes,
    # outside fails; same-edge expansion fails
    evr = [ev("等待期范围为30-60天。")]
    assert gate_ok("等待期范围为30-60天[E1]", evr, "C1") is True
    assert gate_ok("等待期范围为60-90天[E1]", evr, "C1") is False
    assert gate_ok("等待期一般为45天[E1]", evr, "C1") is True
    assert gate_ok("等待期一般为90天[E1]", evr, "C1") is False
    assert gate_ok("重疾保额通常为4倍年收入[E1]",
                   [ev("重疾保额建议覆盖3-5倍年收入。")], "D") is True
    assert gate_ok("重疾保额通常为8倍年收入[E1]",
                   [ev("重疾保额建议覆盖3-5倍年收入。")], "D") is False


def test_t11_unit_mismatch_not_supported():
    # OD-FIX3-2B: same digits, different unit -> no support
    assert gate_ok("等待期一般为90万[E1]", [ev("等待期为90天。")],
                   "C1") is False
    assert gate_ok("保额通常为10倍年收入[E1]",
                   [ev("保额通常为10万。")], "D") is False
    assert gate_ok("保额通常为10万[E1]",
                   [ev("保额通常为10万。")], "C1") is True
    assert gate_ok("等待期为90天[E1]", [ev("等待期为90天。")],
                   "C1") is True


# ---------------- 12-13 product identity / date
def test_t12_product_identity_mismatch():
    # OD-FIX3-2C: claim names another product vs product-bound evidence
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("这款百万医疗险A等待期90天[E1]",
                       [ev(P004, product_id="P004")], arm) is False
        assert gate_ok("P001重疾险的等待期为90天[E1]",
                       [ev(P004, product_id="P004")], arm) is False
    # anaphora without a product NAME is unconstrained (no false block)
    assert gate_ok("该产品等待期为90天[E1]",
                   [ev(P004, product_id="P004")], "C1") is True
    # correct product name passes
    assert gate_ok("P004重疾险的等待期为90天[E1]",
                   [ev(P004, product_id="P004")], "C1") is True


def test_t13_date_year_swap_protected():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("该办法自2025年12月1日起施行[E1]",
                       [ev("该办法自2019年12月1日起施行。")], arm) is False
    assert gate_ok("该办法自2019年12月1日起施行[E1]",
                   [ev("该办法自2019年12月1日起施行。")], "C1") is True


# ---------------- 14-16 waiting / exclusion / benefit
def test_t14_waiting_period_variants():
    # verbatim-positive passes; inverted fails (every arm)
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok(
            "被保险人在等待期内确诊重大疾病的，不承担给付责任，仅退还保费[E1]",
            [ev(P004, product_id="P004")], arm) is True
        assert gate_ok("等待期内确诊重疾可获全额赔付[E1]",
                       [ev(P004, product_id="P004")], arm) is False
        assert gate_ok("该产品等待期为90天[E1]",
                       [ev(P004, product_id="P004")], arm) is True


def test_t15_exclusion():
    assert gate_ok("被保险人故意犯罪不承担给付责任[E1]",
                   [ev("P004重疾险责任免除：被保险人故意自伤、故意犯罪"
                       "不承担给付责任。", product_id="P004")],
                   "C1") is True
    assert gate_ok("P004对所有先天性畸形都不承担给付责任[E1]",
                   [ev("P004重疾险责任免除：遗传性疾病、先天性畸形"
                       "（合同另有约定的除外）不承担给付责任。",
                       product_id="P004")], "C1") is False


def test_t16_benefit_payment_promise():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("P004保证续保至终身[E1]",
                       [ev(P004, product_id="P004")], arm) is False


# ---------------- 17-18 R3 / R4 (regression shape)
def test_t17_r3_product_questions_unsupported_number():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("XX重疾险等待期为90天[E1]",
                       [ev(CI)], arm) is False


def test_t18_r4_personalized_amount_not_delivered():
    # personalized AMOUNT: C1/B keep the documented F-1 baseline (type
    # exemption delivers it today); D/BD close it. R4 ROUTE protection
    # remains OD-H3 (out of scope) — this locks the amount surface.
    assert gate_ok("建议您配置100万重疾险[E1]",
                   [ev("保额应与家庭收入水平相匹配。")], "C1") is True
    assert gate_ok("建议您配置100万重疾险[E1]",
                   [ev("保额应与家庭收入水平相匹配。")], "B") is True
    assert gate_ok("建议您配置100万重疾险[E1]",
                   [ev("保额应与家庭收入水平相匹配。")], "D") is False
    assert gate_ok("建议您配置100万重疾险[E1]",
                   [ev("保额应与家庭收入水平相匹配。")], "BD") is False
    assert gate_ok("建议结合家庭预算咨询专业规划[E1]", [], "B") is True


# ---------------- B positives/negatives (whitelist precision)
def test_b_positive_procedural_guidance():
    # REC-typed procedural guidance already passes under C1 (type
    # exemption — pre-existing); B keeps it
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("建议投保前通读保险条款并如实完成健康告知[E1]",
                       [], arm) is True
    # B's DIFFERENTIATING positive: C-FACT-typed honest evidence-absence
    # prose (no 建议 marker) — refused under C1/D, exempt under B
    assert gate_ok("现有证据未提及该产品的具体保费水平[E1]",
                   [ev("产品条款全文。")], "C1") is False
    assert gate_ok("现有证据未提及该产品的具体保费水平[E1]",
                   [ev("产品条款全文。")], "B") is True


def test_b_negative_wrapped_numbers_blocked():
    # the 因为-clause splits into a C-FACT numeric claim and is
    # blocked in EVERY arm (number inside a REC clause is the F-1
    # shape — covered by test_t18)
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok(
            "建议为家庭经济支柱优先配置保障，因为等待期只有90天[E1]",
            [ev("家庭保障宜先覆盖主要收入来源。")], arm) is False
    # B's OWN guard (C-FACT-typed meta prose with a number): exemption
    # must NOT apply — the numeric premise stays on the C-FACT path
    assert gate_ok("无法基于现有证据给出90天等待期的具体规定[E1]",
                   [ev("家庭保障宜先覆盖主要收入来源。")], "B") is False


# ---------------- D precision (plain recommendations unharmed)
def test_d_plain_recommendation_unharmed():
    for arm in ("C1", "B", "D", "BD"):
        assert gate_ok("建议优先为家庭经济支柱配置保障[E1]",
                       [ev("家庭保障宜先覆盖主要收入来源。")], arm) is True


# ---------------- OFF equivalence + rollback (Phase 10)
def test_off_equivalence_flags_off_is_c1():
    """Both levers OFF → no row carries the new markers (the new code
    paths are skipped entirely) and verdicts match C1."""
    claims = [
        ("一般建议重疾保额覆盖3-5倍年收入", [ev("保额应与家庭收入相匹配。")]),
        ("建议投保前通读条款[E1]", []),
        ("重疾险等待期为90天[E1]", [ev("等待期为90天。")]),
        ("该产品等待期为30天[E1]", [ev("等待期为90天。")]),
    ]
    for text, evs in claims:
        out = cs.check(text, evs, rules("C1"))
        for row in out["claims"]:
            assert "exempt" not in row
            assert not row["support_type"].endswith("+PREMISE")


def test_env_flag_override_wins():
    os.environ["EXEMPTION_V2_ENABLED"] = "1"
    try:
        r = copy.deepcopy(ggate.load_rules())
        r.setdefault("claim_support", {})["enabled"] = True
        assert cs.check("建议投保前通读条款[E1]", [], r)["ok"] is True
    finally:
        del os.environ["EXEMPTION_V2_ENABLED"]
    # rules-off again (env removed) — C1 baseline: REC-typed clause is
    # exempt by TYPE (pre-existing), C-FACT meta prose is refused
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    assert cs.check("建议投保前通读条款[E1]", [], r)["ok"] is True
    assert cs.check("现有证据未提及保费水平[E1]",
                    [{"content": "x", "source_name": "t"}], r)["ok"] is False


def test_rollback_env_off_beats_rules_on():
    r = rules("BD")
    os.environ["EXEMPTION_V2_ENABLED"] = "0"
    os.environ["PREMISE_SCAN_ENABLED"] = "0"
    try:
        out = cs.check("一般建议重疾保额覆盖3-5倍年收入",
                       [ev("保额应与家庭收入相匹配。")], r)
        assert out["ok"] is True   # C1 behavior (type exemption passes)
    finally:
        del os.environ["EXEMPTION_V2_ENABLED"]
        del os.environ["PREMISE_SCAN_ENABLED"]


# ---------------- loop seam (no-op unless attached; never affects answer)
def test_seam_default_none_and_raising_observer_no_effect():
    from runtime.grounding import loop as gloop
    from runtime.llm.types import LLMRequest
    from runtime.qa_agent import run_qa_turn
    from runtime.intent.classifier import classify

    class Prov:
        name = "p"
        model = "m"
        def generate(self, messages, tools):
            return SimpleNamespace(
                text="等待期一般为90天[E1]。",
                usage={"input_tokens": 1, "output_tokens": 1},
                latency_ms=1)

    class StubSvc:
        name = "s"
        provider = SimpleNamespace(name="s")
        def build_evidence(self, query, top_k=None, as_of=None,
                           jurisdiction="CN"):
            item = {"content": "%s：等待期一般为90天。" % query,
                    "source_name": "s", "document_id": "d1",
                    "document_name": "d", "version": "v1"}
            gov = SimpleNamespace(
                status="success", conflict=False, results=[item],
                retrieval_metadata={"governance": {"allowed": 1,
                                                   "rejected": 0}})
            return [item], gov, [], None

    assert gloop.shadow_observer is None
    ir = classify("重疾险等待期一般为多少天？")

    from runtime.llm.types import LLMResponse, LLMUsage

    class GW:
        name = "gw"
        provider = SimpleNamespace(name="gw")
        def generate(self, req):
            r = Prov().generate(req.messages, [])
            return LLMResponse(request_id=req.request_id, provider="gw",
                               model="m", content=r.text,
                               finish_reason="stop",
                               usage=LLMUsage(1, 1, 2), latency_ms=1)

    ctx = run_qa_turn("重疾险等待期一般为多少天？", ir,
                      service=StubSvc(), gateway=GW())
    base_answer = ctx["answer"]

    def boom(event, data):
        raise RuntimeError("observer must never break the answer")

    gloop.shadow_observer = boom
    try:
        ctx2 = run_qa_turn("重疾险等待期一般为多少天？", classify(
            "重疾险等待期一般为多少天？"), service=StubSvc(), gateway=GW())
        assert ctx2["answer"] == base_answer
    finally:
        gloop.shadow_observer = None


# ---------------- shadow judge client error collapse (Phase 7 contract)
def test_judge_error_collapse():
    from runtime.grounding import shadow_judge as sj

    class Dead:
        name = "dead"
        def generate(self, messages, tools):
            raise RuntimeError("provider down")

    c = sj.SemanticJudgeClient(Dead())
    r = c.judge_claim("重疾险等待期为90天", ["等待期为90天。"])
    assert r["decision"] == sj.KEEP_BASELINE
    assert r["decision_reason"].startswith("error:provider")

    class Malformed:
        name = "m"
        def generate(self, messages, tools):
            return SimpleNamespace(text="not json at all", usage={},
                                   latency_ms=1)

    c2 = sj.SemanticJudgeClient(Malformed())
    assert c2.judge_claim("x", ["y"])["decision"] == sj.KEEP_BASELINE

    class LowConf:
        name = "lc"
        def generate(self, messages, tools):
            return SimpleNamespace(text=json.dumps({
                "entailment": "yes", "contradiction": False,
                "exempt": False, "confidence": 0.2, "reason": "r"}),
                usage={}, latency_ms=1)

    r3 = sj.SemanticJudgeClient(LowConf()).judge_claim("x", ["y"])
    assert r3["decision"] == sj.UNCERTAIN

    class Contradict:
        name = "ct"
        def generate(self, messages, tools):
            return SimpleNamespace(text=json.dumps({
                "entailment": "yes", "contradiction": True,
                "exempt": False, "confidence": 0.99, "reason": "r"}),
                usage={}, latency_ms=1)

    r4 = sj.SemanticJudgeClient(Contradict()).judge_claim("x", ["y"])
    assert r4["decision"] == sj.KEEP_BASELINE   # never upgrade on contradiction
    assert r4["decision_reason"] == "contradiction"
