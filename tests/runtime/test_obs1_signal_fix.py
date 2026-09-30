# -*- coding: utf-8 -*-
"""Pre-UAT OBS-1 deterministic signal fix regression (v1 frozen).

§5 contamination (20 planning + QA), §6 minimal semantic contrast
(2 signals x positive/negative/near-miss), OBS-1 matrix vs SEALED
taxonomy. Test-only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime.intent.classifier import classify  # noqa: E402
from runtime.router import route                # noqa: E402
from runtime.agent_registry import default_registry  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def cl(m, ctx=None, pending=False):
    return classify(m, conversation_context=ctx or [],
                    pending_clarification=pending)


@section
def obs1_matrix(t: Checks):
    SEALED = {  # sealed-gold expectations (e306118 golden + FIX rulings)
        1: "insurance_qa", 2: "insurance_qa", 3: "insurance_qa",
        4: "insurance_plan", 5: "insurance_qa", 6: "insurance_qa",
        7: "insurance_qa", 8: "insurance_qa", 9: "insurance_qa",
        10: "insurance_qa"}
    MSGS = ["重疾险一般买多少保额？", "重疾保额通常建议多少？",
            "我35岁，家庭收入50万，重疾险买多少合适？",
            "按照我的情况，重疾险应该配置多少？",
            "我已经有100万重疾险，还需要买吗？",
            "重疾险保额怎么计算？",
            "我的家庭收入50万，房贷80万，重疾险应该买多少？",
            "重疾险保额一般怎么算？",
            "我只想了解行业通常的重疾险保额。",
            "根据我的家庭情况给我一个重疾险保额建议。"]
    for i, m in enumerate(MSGS, 1):
        got = cl(m)["intent_id"]
        t.chk("OBS1-%02d sealed-gold %s" % (i, SEALED[i]),
              got == SEALED[i], "got %s" % got)
    t.chk("OBS1-02 gap CLOSED (was unknown)",
          cl("重疾保额通常建议多少？")["intent_id"] == "insurance_qa")


@section
def planning_contamination(t: Checks):
    """§5: planning-shaped messages must NOT flip to QA via the new
    signals (plan action signals keep priority by rule order)."""
    PLAN = [
        "帮我做家庭保障规划",
        "帮我规划全家保险",
        "家庭保险怎么配置",
        "给我出一个保险方案",
        # NOTE: 怎么给一家人买保险 is NOT here — sealed FIX-A semantics:
        # 怎么+买 adjacency fails (给 intervenes) -> plan suppressed ->
        # question_form rescue -> qa (pre-existing sealed behavior).
        "我想投保重疾险",
        "预算2万怎么买保险",
        "怎么安排孩子的保障",
        "帮我做家庭保障规划，重疾险建议多少保额？",
        "规划一下，重疾险一般建议多少？",
        "我的家庭收入50万，帮我配置一下保险",
        "按照我的家庭情况做个方案",
        "怎么规划家庭保险，一般建议多少保额？",
        "帮我规划，预算有限，多少保额合适？",
        "我想给我爸妈配置保险，怎么配？",
    ]
    for m in PLAN:
        got = cl(m)["intent_id"]
        t.chk("plan-keep %r" % m[:16], got == "insurance_plan",
              "got %s" % got)
    # pending continuation with new signal present must STILL switch
    # (advice-quantity question = switch, per frozen C1 semantics)
    t.chk("pending + 建议多少-question = switch to qa",
          cl("那重疾险建议多少保额？", ["帮我做家庭保障规划"],
             pending=True)["intent_id"] == "insurance_qa")
    t.chk("pending + pure answer keeps continuation",
          cl("房贷还有100万", ["帮我做家庭保障规划"],
             pending=True)["intent_id"] == "insurance_plan")


@section
def qa_contamination(t: Checks):
    QA = ["重疾险一般保额是多少？", "行业通常建议多少保额？",
          "重疾险保额怎么计算？", "重疾险保额通常怎么确定？",
          "重疾保额通常建议多少？", "意外险一般建议多少保额？",
          "定期寿险多少保额是什么意思？", "年金险通常建议多少？"]
    for m in QA:
        got = cl(m)["intent_id"]
        t.chk("qa-keep %r" % m[:14], got == "insurance_qa",
              "got %s" % got)
    # PRE-EXISTING sealed characteristic (recorded, not fixed — out of
    # minimal scope): the anchor-free quantity-signal family captures
    # non-insurance quantity questions ("手机买多少合适" -> qa PRE-fix).
    # The 2 new signals behave consistently with that sealed family.
    for m in ["房子一般建议多少首付？", "工资建议多少存起来？",
              "手机买多少合适"]:
        got = cl(m)["intent_id"]
        t.chk("quantity-family capture (pre-existing class) %r" % m[:10],
              got == "insurance_qa", "got %s" % got)
    # non-insurance WITHOUT any quantity signal stays unknown
    for m in ["今天天气怎么样", "附近有什么好吃的"]:
        t.chk("non-insurance no-signal stays unknown %r" % m[:8],
              cl(m)["intent_id"] == "unknown_insurance_intent")


@section
def minimal_contrast(t: Checks):
    """§6: one-word changes flip intent as expected."""
    # signal 建议多少: positive / negative / near-miss
    t.chk("pos 建议多少", cl("重疾保额通常建议多少？")["intent_id"]
          == "insurance_qa")
    # anchor-free signal fires (consistent with sealed quantity family)
    t.chk("neg-shape (no anchor) still fires (sealed family trait)",
          cl("通常建议多少？")["intent_id"] == "insurance_qa")
    t.chk("near-miss 建议买多少 (买 intervenes) NOT captured",
          cl("重疾保额建议买多少")["intent_id"]
          == "unknown_insurance_intent")
    # signal 多少保额
    t.chk("pos 多少保额", cl("行业一般多少保额？")["intent_id"]
          == "insurance_qa")
    t.chk("definition marker fires qa (sealed rule 5)",
          cl("重疾保额是什么")["intent_id"] == "insurance_qa")
    t.chk("near-miss 保额多少 bare (no 多少保额 substring order)",
          cl("保额多少")["intent_id"] == "unknown_insurance_intent")
    # one-word flip: 03 shape
    t.chk("one-word: 配置 flips 03-shape to plan",
          cl("我35岁，家庭收入50万，重疾险怎么配置合适")["intent_id"]
          == "insurance_plan")
    t.chk("one-word: 买多少合适 keeps qa",
          cl("我35岁，家庭收入50万，重疾险买多少合适")["intent_id"]
          == "insurance_qa")


@section
def router_paths(t: Checks):
    reg = default_registry()
    for m, want in [("重疾保额通常建议多少？", "insurance-qa-agent"),
                    ("帮我做家庭保障规划", "insurance-planning-agent"),
                    ("P001是什么产品", "insurance-qa-agent"),
                    ("今天天气怎么样", "conversation-agent")]:
        rd = route(cl(m), reg)
        t.chk("router %r->%s" % (m[:10], want), rd["agent_id"] == want,
              "got %s (%s)" % (rd["agent_id"], rd["decision_source"]))


def main():
    return run_sections(SECTIONS, "webui_test_obs1_signal_fix.txt",
                        "OBS-1 SIGNAL FIX")


if __name__ == "__main__":
    sys.exit(main())
