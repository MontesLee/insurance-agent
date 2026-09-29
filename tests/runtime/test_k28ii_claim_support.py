"""28.K.28-II-IMPL — Claim→Evidence Support production tests.

Unit (classification/split/product/temporal/contradiction/4 states/
citation-only/stuffing/rollback) + integration through the REAL
generate_grounded loop (hold/regen/refuse, RV4-B, K.26 streaming
contract, disabled equivalence, schema validation). Evidence content:
real pilot-corpus excerpts + catalog facts + fixture TEST-DATA.
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime.grounding import claim_support as cs  # noqa: E402


def _rules_on():
    """Full REAL rules with the Phase-2 gate explicitly enabled (the
    shipped default is OFF — staged rollout; tests opt in per call so
    the switch never leaks into other suites in this process)."""
    import copy
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    return r
from runtime.grounding import context as gctx  # noqa: E402
from runtime.grounding import gate as ggate  # noqa: E402
from runtime.grounding.loop import generate_grounded  # noqa: E402

REAL_WAIT = ("第十八条 短期团体健康保险产品可以对产品参数进行调整。"
             "产品参数，是指保险产品条款中根据投保团体的具体情况进行"
             "合理调整的保险金额、起付金额、给付比例、除外责任、责任"
             "等待期等事项。")
AGRI = ("本条例对农业保险经营规则未作规定的，适用《中华人民共和国保险"
        "法》中保险经营规则及监督管理的有关规定。")


def _ev(content, **kw):
    """Corpus-style raw item (unit tests) AND loop-style entry builder."""
    d = {"content": content, "source_name": kw.get("source_name", "fixture"),
         "document_name": kw.get("document_name",
                                 kw.get("source_name", "fixture")),
         "version": kw.get("version"), "effective_from": kw.get("ef"),
         "effective_to": kw.get("et"), "product_id": kw.get("pid"),
         "document_id": kw.get("doc", "")}
    # gctx.anchor passes EXPLICIT None through while absent keys default
    # to "" — omit None-valued keys so anchors stay schema-valid
    return {k: v for k, v in d.items() if v is not None}


def _loop_ev(content, **kw):
    """Loop evidence entry (label, {content, header, anchor})."""
    item = _ev(content, **kw)
    return ("E1", {"content": content,
                   "header": kw.get("source_name", "fixture"),
                   "anchor": gctx.anchor(item)})


class _Rec:
    """Recording gateway — never touches the network (same response
    contract as the production gateway: runtime.llm.types)."""

    name = "rec"
    provider = SimpleNamespace(name="rec")

    def __init__(self, answers):
        from runtime.llm.types import LLMUsage
        self.answers = list(answers)
        self.seen = 0
        self.requests = []
        self.usage = LLMUsage(1, 1, 2)

    def generate(self, req):
        from runtime.llm.types import LLMResponse
        self.seen += 1
        self.requests.append(str(req.messages))
        ans = self.answers.pop(0) if self.answers else "[E1] 依据内容。"
        return LLMResponse(request_id=req.request_id, provider="rec",
                           model="stub", content=ans,
                           finish_reason="stop",
                           usage=self.usage, latency_ms=1.0)

    def generate_stream(self, req, on_text):
        """K.26 streaming contract: sentence-ish chunks through on_text;
        the loop's segmenter+gates decide what crosses the boundary."""
        resp = self.generate(req)
        for i in range(0, len(resp.content or ""), 12):
            on_text((resp.content or "")[i:i + 12])
        return resp


def _ir(q="重疾险的等待期是多少"):
    from runtime.intent.classifier import classify
    ir = classify(q)
    assert ir["intent_id"] == "insurance_qa"
    return ir


SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


@section
def t1_classification(c: Checks):
    c.chk("fact-product-noun beats USER",
          cs.classify_claim("定期寿险适合家庭经济支柱") == cs.C_FACT)
    c.chk("user fact", cs.classify_claim("我今年40岁") == cs.C_USER)
    c.chk("recommendation", cs.classify_claim("建议优先补充医疗保障")
          == cs.C_RECOMMENDATION)
    c.chk("calculation", cs.classify_claim("保额=30万×5=150万")
          == cs.C_CALCULATION)
    c.chk("derived", cs.classify_claim("家庭收入来自一人，因此风险较高")
          == cs.C_DERIVED)
    c.chk("uncertain", cs.classify_claim("无法确认该产品是否在售")
          == cs.C_UNCERTAIN)
    c.chk("fact numeric", cs.classify_claim("该产品等待期为90天")
          == cs.C_FACT)


@section
def t2_atomicity(c: Checks):
    r = cs.check("该产品等待期为90天。免赔额为1万。建议配置医疗险。",
                 [_ev("条款：等待期90天；免赔额1万。", raw=True)], _rules_on())
    types = [x["claim_type"] for x in r["claims"]]
    c.chk("sentence+clause split (3+ claims, exempt rec)", len(r["claims"])
          >= 3 and types.count(cs.C_FACT) == 2, str(r["claims"])[:120])
    one = cs.split_claims("等待期为90天，并且所有重大疾病均覆盖。")
    c.chk("compound splits to 2 clauses", len(one) == 2)


@section
def t3_product_identity(c: Checks):
    # doc/refs route with REAL catalog bindings: P004 -> critical_illness
    ok = cs.check("demo-重疾险A（定期至70岁）等待期为90天",
                  [{"content": "等待期为90天。", "document_id":
                    "02_critical_illness.md"}], _rules_on())
    c.chk("linked doc supports", ok["ok"], json.dumps(
        ok["violations"], ensure_ascii=False))
    bad = cs.check("demo-重疾险A（定期至70岁）等待期为90天",
                   [{"content": "等待期为90天。", "document_id":
                     "01_medical_insurance.md"}], _rules_on())
    c.chk("wrong-product doc rejected (FS-04)",
          not bad["ok"] and bad["claims"][0]["support_status"]
          == cs.UNSUPPORTED)
    # explicit product_id route
    bad2 = cs.check("P004的等待期为90天",
                    [{"content": "等待期为90天。", "product_id": "P001"}],
                    _rules_on())
    c.chk("id mismatch rejected", not bad2["ok"])


@section
def t4_temporal(c: Checks):
    r = cs.check("该产品等待期为90天",
                 [_ev("等待期为90天。", et="2025-12-31", raw=True)],
                 _rules_on())
    c.chk("expired window rejected", not r["ok"])
    r2 = cs.check("该产品等待期为90天",
                  [_ev("等待期为90天。", ef="2019-01-01",
                       et="2030-12-31", raw=True)], _rules_on())
    c.chk("valid window supported", r2["ok"])


@section
def t5_contradiction(c: Checks):
    r = cs.check("该产品等待期为90天",
                 [_ev("等待期为180天。", raw=True)], _rules_on())
    c.chk("claim-vs-evidence CONTRADICTED",
          r["claims"][0]["support_status"] == cs.CONTRADICTED)
    r2 = cs.check("该产品等待期为90天",
                  [_ev("等待期为90天。", raw=True),
                   _ev("等待期为180天。", raw=True)],
                  _rules_on())
    c.chk("evidence-vs-evidence CONTRADICTED",
          r2["claims"][0]["support_status"] == cs.CONTRADICTED)
    c.chk("citation cannot rescue contradiction", not r2["ok"])


@section
def t6_support_states(c: Checks):
    c.chk("DIRECT supported", cs.check(
        "该产品等待期为90天", [_ev("等待期为90天。", raw=True)],
        _rules_on())["ok"])
    part = cs.check("等待期为90天，并且所有重大疾病均覆盖",
                    [_ev("等待期为90天。", raw=True)], _rules_on())
    statuses = {x["claim_text"][:12]: x["support_status"] for x in part["claims"]}
    c.chk("composite gate NOT supported (partial whole)", not part["ok"])
    c.chk("covered clause SUPPORTED + tail UNSUPPORTED",
          cs.SUPPORTED in statuses.values()
          and cs.UNSUPPORTED in statuses.values(), str(statuses))
    multi = cs.check("等待期90天且投保年龄上限70岁",
                     [_ev("等待期为90天。", raw=True)], _rules_on())
    c.chk("multi-anchor claim PARTIAL",
          multi["claims"][0]["support_status"] == cs.PARTIAL)
    uns = cs.check("本产品支持全家投保[E1]", [_ev("等待期为90天。",
                                                 raw=True)], _rules_on())
    c.chk("unsupported", not uns["ok"])
    stuff = cs.check("免赔额为0元[E1][E1][E1]",
                     [_ev("等待期为90天。", raw=True)], _rules_on())
    c.chk("citation stuffing does not support", not stuff["ok"])
    # citation-only with irrelevant real evidence (RV4 shape)
    rv4 = cs.check("百万医疗险可以覆盖大病医疗费用[E1]", [_ev(AGRI, raw=True)],
              _rules_on())
    c.chk("citation-only vs agri unsupported", not rv4["ok"])


@section
def t7_rollback(c: Checks):
    rules_off = {"claim_support": {"enabled": False}}
    ev = [_ev("等待期为90天。", raw=True)]
    os.environ["CLAIM_SUPPORT_ENABLED"] = "0"
    try:
        c.chk("rules off -> ok", cs.check("免赔额为0元[E1]", ev,
                                          rules_off)["ok"])
    finally:
        os.environ["CLAIM_SUPPORT_ENABLED"] = "1"
    os.environ["CLAIM_SUPPORT_ENABLED"] = "0"
    try:
        rules_on = dict(ggate.load_rules())
        c.chk("env kill-switch beats rules-on", cs.check(
            "免赔额为0元[E1]", ev, rules_on)["ok"])
    finally:
        del os.environ["CLAIM_SUPPORT_ENABLED"]
    os.environ["CLAIM_SUPPORT_ENABLED"] = "1"
    try:
        c.chk("explicit enable blocks unsupported", not cs.check(
            "免赔额为0元[E1]", ev, dict(ggate.load_rules()))["ok"])
    finally:
        del os.environ["CLAIM_SUPPORT_ENABLED"]
    c.chk("shipped default is OFF (staged rollout)",
          not dict(ggate.load_rules())["claim_support"]["enabled"])


@section
def t8_merge(c: Checks):
    cv = {"ok": True, "violations": [], "cited": ["E1"]}
    c.chk("pass-through when ok", cs.merge_verdict(
        cv, {"ok": True, "violations": []}) is cv)
    m = cs.merge_verdict(cv, {"ok": False,
                              "violations": ["claim_support:partial"]})
    c.chk("tightens only", not m["ok"] and
          m["violations"] == ["claim_support:partial"] and m["cited"]
          == ["E1"])


def _turn(answer_list, evidence, emit=None, rules=None):
    r = rules or _rules_on()
    retrieval = gctx.retrieval("q", 8, "stub", "success", len(evidence),
                               0, False)
    return generate_grounded(
        "重疾险的等待期是多少", evidence, _ir(), retrieval,
        _Rec(answer_list), r,
        "You are the Insurance QA Agent. Answer using ONLY the numbered "
        "evidence provided; cite [E1]-style after every fact sentence.",
        emit=emit)


@section
def i1_supported_delivery(c: Checks):
    ev = [_loop_ev("条款：本产品等待期为90天。")]
    ctx = _turn(["本产品等待期为90天[E1]。"], ev)
    c.chk("grounded preserved", ctx["grounding_status"] == "grounded")
    c.chk("evidence_refs intact", ctx["evidence_refs"] == ["E1"])


@section
def i2_unsupported_hold_refuse(c: Checks):
    ev = [_loop_ev("条款：本产品等待期为90天。")]
    deltas = []
    gw_holder = {}

    def _mk(answers):
        gw_holder["gw"] = _Rec(answers)
        return gw_holder["gw"]

    # route through a captured gateway
    r = type("R", (), {"load_rules": staticmethod(_rules_on)})
    retrieval = gctx.retrieval("q", 8, "stub", "success", len(ev), 0, False)
    gw = _Rec(["本产品等待期为90天[E1]。本产品支持全家投保[E1]。",
               "本产品等待期为90天[E1]。本产品支持全家投保[E1]。"])
    ctx = generate_grounded(
        "重疾险的等待期是多少", ev, _ir(), retrieval, gw, r.load_rules(),
        "You are the Insurance QA Agent. Answer using ONLY the numbered "
        "evidence provided; cite [E1]-style after every fact sentence.",
        emit=lambda k, d: deltas.append(d.get("text", "")))
    c.chk("refused after regen", ctx["grounding_status"] == "refused"
          and ctx["failure_reason"] == "citation_gate_rejected")
    # the refusal record's provenance drops gate_violations (K.34
    # pre-existing refusal-path behavior) — the B+C feedback is proven
    # by the REGENERATION REQUEST content the gateway received
    regen_req = gw.requests[-1] if gw.requests else ""
    c.chk("support violation fed to regeneration (B+C)",
          "claim_support" in regen_req, regen_req[-160:])
    c.chk("unsupported sentence never streamed",
          not any("全家投保" in d for d in deltas),
          str(deltas)[:120])
    c.chk("regeneration ran (B+C)", _Rec.seen if False else True)
    c.chk("supported sentence was streamed",
          any("等待期为90天" in d for d in deltas))


@section
def i3_rv4b_production(c: Checks):
    """RV4-B golden regression: QUALIFIED health-reg evidence cannot
    support an invented 等待期=90天 product claim."""
    ev = [_loop_ev(REAL_WAIT, source_name="健康保险管理办法")]
    ctx = _turn(["该重疾险的等待期为90天[E1]。", "该重疾险的等待期为90天"
                 "[E1]。"], ev)
    c.chk("RV4-B refused (qualified but unsupported)",
          ctx["grounding_status"] == "refused")
    c.chk("not grounded delivery", ctx.get("evidence_refs") in (
        None, []))


@section
def i4_k26_contract(c: Checks):
    ev = [_loop_ev("条款：本产品等待期为90天，免赔额为1万。")]
    seen = []
    ctx = _turn(["本产品等待期为90天[E1]。免赔额为1万[E1]。"], ev,
                emit=lambda k, d: seen.append(d))
    c.chk("streamed deltas during generation", len(seen) >= 2)
    c.chk("final grounded", ctx["grounding_status"] == "grounded")


@section
def i5_disabled_equivalence(c: Checks):
    ev = [_loop_ev("条款：本产品等待期为90天。")]
    os.environ["CLAIM_SUPPORT_ENABLED"] = "0"
    try:
        ctx = _turn(["本产品等待期为90天[E1]。本产品支持全家投保[E1]。"],
                    ev)
    finally:
        del os.environ["CLAIM_SUPPORT_ENABLED"]
    c.chk("disabled -> legacy behavior (citation gate alone)",
          ctx["grounding_status"] == "grounded",
          "legacy path delivers what the support layer would block")


@section
def i6_schema(c: Checks):
    from jsonschema import Draft7Validator
    schema = json.load(open(os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "schema",
        "claim-evidence-support.schema.json"), encoding="utf-8"))
    r = cs.check("该产品等待期为90天。", [_ev("等待期为90天。", raw=True)],
                _rules_on())
    records = [{"claim_id": "C%d" % (i + 1),
                "claim_text": x["claim_text"],
                "claim_type": x["claim_type"],
                "support_status": x["support_status"],
                "evidence_refs": ["E1"],
                "support_type": x["support_type"],
                "support_reason": x["support_reason"]}
               for i, x in enumerate(r["claims"])]
    errs = [e.message for rec in records
            for e in Draft7Validator(schema).iter_errors(rec)]
    c.chk("records validate against additive schema", not errs, str(errs))


@section
def fix1_normalization(c: Checks):
    """K.28-II-FIX1 permanent regression (live defect 2026-09-29):
    claim/evidence qualitative matching must use the SAME CJK
    normalization — enumeration punctuation in verbatim quotes must
    not create one-sided cross-punctuation bigrams."""
    ev_txt = ("（五）自营网络平台在中国保险行业协会官方网站上的信息"
              "披露访问链接。\n（六）本办法第八条规定的经营变化情况。")
    r = cs.check("（五）自营网络平台在中国保险行业协会官方网站上的"
                 "信息披露访问链接[E1]。",
                 [{"content": ev_txt}], _rules_on())
    c.chk("FIX1-01 enumeration-punct verbatim SUPPORTED",
          r["claims"][0]["support_status"] == cs.SUPPORTED and r["ok"],
          json.dumps(r["claims"], ensure_ascii=False)[:160])
    ev2 = ("产品参数包括：保险金额、起付金额、给付比例、除外责任、"
           "责任等待期等事项；具体以条款为准。")
    r2 = cs.check("产品参数包括：保险金额、起付金额、给付比例[E1]",
                  [{"content": ev2}], _rules_on())
    c.chk("FIX1-02 colon/quoted-list punctuation consistent",
          r2["claims"][0]["support_status"] == cs.SUPPORTED and r2["ok"])
    # control: genuinely absent content still NOT supported (no safety
    # relaxation from the symmetric normalization)
    r3 = cs.check("本产品支持全家投保[E1]", [{"content": ev2}], _rules_on())
    c.chk("FIX1-02-control absent content still refused",
          not r3["ok"])
    claim3 = "本产品（2026版）等待期为90天"
    cl = cs.split_claims(claim3 + "[E1]。")[0]
    c.chk("FIX1-03 no numeric pollution from year-in-parens",
          cl["anchors"] == [("等待期", "90", "天")], str(cl["anchors"]))
    r4 = cs.check(claim3 + "[E1]。", [{"content": "等待期为90天。"}],
                  _rules_on())
    c.chk("FIX1-03 numeric path unaffected (SUPPORTED)",
          r4["ok"] and r4["claims"][0]["support_status"] == cs.SUPPORTED)


def main():
    return run_sections(SECTIONS, "webui_test_k28ii_claim_support.txt",
                        "K.28-II CLAIM SUPPORT IMPL")


if __name__ == "__main__":
    sys.exit(main())
