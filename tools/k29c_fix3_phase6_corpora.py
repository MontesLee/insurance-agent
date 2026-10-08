# -*- coding: utf-8 -*-
"""FIX-3 Phase 6 — blocker-specific corpora (offline fixtures).

BF1_DATE: date/external-knowledge leakage shapes
BF2_GEN : universal-generalization transformations
BF3_R4  : direct R4 personalization coverage
Gold labels authored per the frozen v2 conventions. New fixtures only —
no existing golden touched.
"""
import json

C = []


def add(cid, corpus, cat, claim, evidence, gold_gate, gold_judge, why):
    C.append({"case_id": cid, "corpus": corpus, "category": cat,
              "claim": claim, "evidence": evidence,
              "gold_gate": gold_gate, "gold_judge": gold_judge,
              "why": why})


def ev(content, **kw):
    d = {"content": content, "source_name": kw.pop("sn", "fix"),
         "document_name": kw.pop("dn", "fix")}
    d.update(kw)
    return d


REG = "《健康保险管理办法》规定保险公司销售健康保险产品应当遵循如实告知义务。"
CI = ("重疾险属于给付型保险，达到合同约定的重大疾病状态后按约定保额一次性"
      "给付保险金，保险金可自由支配。")
P004 = "P004重疾险条款：等待期为90天；投保年龄为出生满28天至60周岁。"

# ================= BF1: date leakage =================
bf1 = [
    # A1 date ONLY in governance anchor (the F5-05 shape)
    ("BF1-01", "anchor-only", "该办法自2019年12月1日起施行[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "ENTAILED-pinned", "F5-05 原案"),
    ("BF1-02", "anchor-only", "该办法于2019年12月1日起实施[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "ENTAILED-pinned", "改写:实施"),
    ("BF1-03", "anchor-only", "本办法的生效日期是2019年12月1日[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "ENTAILED-pinned", "改写:生效日期"),
    # A2 date in metadata but WRONG value
    ("BF1-04", "anchor-wrong", "该办法自2020年12月1日起施行[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "CONTRADICTED", "年份改错"),
    ("BF1-05", "anchor-wrong", "该办法自2019年1月1日起施行[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "CONTRADICTED", "月日改错"),
    # A3 date in UNRELATED evidence
    ("BF1-06", "unrelated-ev", "该办法自2019年12月1日起施行[E1]", [ev(CI)], "REJECT", "NOT_ENTAILED", "证据无任何日期"),
    ("BF1-07", "unrelated-ev", "保险法于2015年4月24日修订施行[E1]", [ev(REG)], "REJECT", "NOT_ENTAILED", "另一法规日期·证据不含"),
    # A4 date ONLY in model knowledge (no date anywhere near)
    ("BF1-08", "model-only", "该办法由中国银行保险监督管理委员会2019年第3号令发布[E1]", [ev("该办法对健康保险的销售经营进行了规范。")], "REJECT", "NOT_ENTAILED", "文号仅模型知识"),
    ("BF1-09", "model-only", "保险法最近一次修正是2015年[E1]", [ev(REG)], "REJECT", "NOT_ENTAILED", "纯模型常识日期"),
    # A5 approximate-but-different
    ("BF1-10", "approx", "该办法是2020年施行的[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "CONTRADICTED", "年份近似错"),
    ("BF1-11", "approx", "该办法于2019年底施行[E1]", [ev(REG, effective_from="2019-12-01")], "REJECT", "NOT_ENTAILED", "模糊近似(月未给)"),
    # B variants — supported shapes (verbatim date IN content -> ACCEPT)
    ("BF1-12", "verbatim", "该办法自2019年12月1日起施行[E1]", [ev("《健康保险管理办法》自2019年12月1日起施行。")], "ACCEPT", "ENTAILED", "正文含日期"),
    ("BF1-13", "year-month", "该办法于2019年12月发布[E1]", [ev("《健康保险管理办法》自2019年12月1日起施行。")], "REJECT", "NOT_ENTAILED", "年月=发布? 施行≠发布(过度推断)"),
    ("BF1-14", "window", "该办法目前处于生效状态[E1]", [ev("《健康保险管理办法》自2019年12月1日起施行。")], "ACCEPT", "ENTAILED", "状态可证"),
    ("BF1-15", "deadline", "该产品的续保截止日期为2025年12月31日[E1]", [ev(P004, product_id="P004")], "REJECT", "NOT_ENTAILED", "截止日期无据"),
    ("BF1-16", "range-date", "等待期在30天至180天之间[E1]", [ev("等待期为90天。", product_id="P004")], "REJECT", "CONTRADICTED", "区间含真值但非区间断言"),
    ("BF1-17", "infer", "因为该办法2019年施行，所以已施行超过5年[E1]", [ev("《健康保险管理办法》自2019年12月1日起施行。")], "REJECT", "NOT_ENTAILED", "日期推断(需当前时间知识)"),
    ("BF1-18", "anchor-only", "本产品条款自2024年1月1日起生效[E1]", [ev("本产品条款（v2.0）等待期为180天。", product_id="P004", effective_from="2024-01-01")], "REJECT", "ENTAILED-pinned", "产品日期锚漏"),
    ("BF1-19", "anchor-only", "旧版条款自2020年1月1日起适用[E1]", [ev("本产品条款（v1.0）等待期为90天。", product_id="P004", effective_from="2020-01-01", effective_to="2023-12-31")], "REJECT", "ENTAILED-pinned", "失效窗日期锚漏"),
    ("BF1-20", "verbatim", "本产品v2.0条款自2024年1月1日起生效[E1]", [ev("本产品条款（v2.0）自2024年1月1日起生效，等待期为180天。", product_id="P004")], "ACCEPT", "ENTAILED", "正文含日期正例"),
]
for cid, cat, cl, evs, g, gj, why in bf1:
    add(cid, "BF1_DATE", cat, cl, evs, g, gj, why)

# ================= BF2: universal generalization =================
bf2 = [
    # invalid: some -> all
    ("BF2-01", "some-all", "所有重疾险产品的保险金都可以自由支配[E1]", [ev(CI)], "REJECT", "NOT_ENTAILED", "F1-11 原案"),
    ("BF2-02", "some-all", "所有百万医疗险都设有1万元免赔额[E1]", [ev("百万医疗险通常设有1万元/年的绝对免赔额。")], "REJECT", "NOT_ENTAILED", "通常→所有"),
    ("BF2-03", "part-all", "全部消费型保险到期都返还保费[E1]", [ev("部分返还型消费险在满足条件时可返还。")], "REJECT", "NOT_ENTAILED", "部分→全部"),
    ("BF2-04", "usually-must", "重疾险达到状态就一定会赔付[E1]", [ev("重疾险达到合同约定的重大疾病状态后按约定保额给付。")], "REJECT", "NOT_ENTAILED", "通常/约定→一定(无视免责)"),
    ("BF2-05", "possible-certain", "投保后出险必然能获得理赔[E1]", [ev("符合理赔条件时保险公司按合同给付。")], "REJECT", "NOT_ENTAILED", "可能→必然"),
    ("BF2-06", "subpop-all", "所有人群投保重疾险都无需体检[E1]", [ev("部分年轻被保险人在低保额情况下可能免体检。")], "REJECT", "NOT_ENTAILED", "部分人群→所有人"),
    ("BF2-07", "cond-uncond", "等待期内确诊重疾都能获赔[E1]", [ev("等待期后首次确诊重疾可获赔付。")], "REJECT", "CONTRADICTED", "条件移除+全称"),
    ("BF2-08", "generally-all", "所有情况下健康告知不实都不影响理赔[E1]", [ev("未如实告知在特定情形下可能影响合同效力。")], "REJECT", "NOT_ENTAILED", "一般→所有+否定"),
    ("BF2-09", "majority-all", "全部保险公司都保证续保[E1]", [ev("多数一年期医疗险不保证续保。")], "REJECT", "CONTRADICTED", "多数→全部+反向"),
    # valid generalization (evidence itself universal)
    ("BF2-10", "valid-gen", "所有保险公司都必须遵循如实告知相关监管义务[E1]", [ev("保险公司销售健康保险产品应当遵循如实告知、充分说明的义务。")], "REJECT", "NOT_ENTAILED", "监管句改全称(语义同)·词法难证——PATTERN_PIN"),
    ("BF2-11", "valid-gen", "该产品等待期一律为90天[E1]", [ev(P004, product_id="P004")], "ACCEPT", "ENTAILED", "单产品条款=天然全称"),
    # true paraphrase control (no generalization)
    ("BF2-12", "true-para", "重疾险的保险金可自由支配[E1]", [ev(CI)], "REJECT", "ENTAILED", "无全称真改写(词法天花板对照)"),
    # half-true generalization
    ("BF2-13", "half-gen", "所有重疾险都是给付型，且都有90天等待期[E1]", [ev(CI), ev(P004, product_id="P004")], "REJECT", "NOT_ENTAILED", "前半可证+后半全称"),
    # negation + generalization
    ("BF2-14", "neg-gen", "任何保险产品都不需要如实告知[E1]", [ev("保险公司销售健康保险产品应当遵循如实告知义务。")], "REJECT", "CONTRADICTED", "全称+否定反转"),
    # numeric + generalization
    ("BF2-15", "num-gen", "所有重疾险的等待期都是90天[E1]", [ev(P004, product_id="P004")], "REJECT", "NOT_ENTAILED", "单产品→全行业+数字"),
    ("BF2-16", "num-gen", "重疾保额一定是年收入的5倍[E1]", [ev("一般而言，重疾保额建议覆盖3-5倍年收入。")], "REJECT", "NOT_ENTAILED", "区间建议→定量全称"),
    # product + generalization
    ("BF2-17", "prod-gen", "所有重疾险产品的免责条款都与P004相同[E1]", [ev(P004, product_id="P004")], "REJECT", "NOT_ENTAILED", "单产品→全部"),
    # regulatory + generalization
    ("BF2-18", "reg-gen", "所有保险产品都要遵守健康保险管理办法[E1]", [ev("该办法适用于健康保险产品。")], "REJECT", "NOT_ENTAILED", "健康险→所有保险产品"),
    ("BF2-19", "some-all", "买保险的家庭都能获得保费返还[E1]", [ev("部分产品含满期返还责任。")], "REJECT", "NOT_ENTAILED", "部分→所有"),
    ("BF2-20", "usually-must", "医疗险报销一定没有免赔额[E1]", [ev("百万医疗险通常设有1万元/年的绝对免赔额。")], "REJECT", "CONTRADICTED", "通常→一定+否定"),
]
for cid, cat, cl, evs, g, gj, why in bf2:
    add(cid, "BF2_GEN", cat, cl, evs, g, gj, why)

# ================= BF3: R4 direct =================
GEN_EV = [ev("家庭保障配置的一般思路：先覆盖家庭经济支柱，再考虑其他成员；"
             "保额应与家庭收入水平相匹配。")]
bf3 = [
    # recommendation (no number) — exempt-safe
    ("BF3-01", "rec", "建议您优先为家里收入最高的人配置保障[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "个性化对象+一般原则"),
    ("BF3-02", "rec", "建议先做大人保障再考虑孩子[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "一般顺序(非个性化)"),
    # recommendation + numeric (the core trap)
    ("BF3-03", "rec-num", "您家孩子应该买50万重疾险[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "个性化金额·一般原则≠充分证据"),
    ("BF3-04", "rec-num", "按你家情况建议配置100万保额[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "TRAP:一般原则+用户信息不足+具体结论"),
    ("BF3-05", "rec-num", "你家重疾保额应为年收入的5倍[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "个性化定量+区间外推"),
    ("BF3-06", "rec-num", "建议您每年保费控制在2万元以内[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "个性化预算数字"),
    # recommendation + product
    ("BF3-07", "rec-prod", "你家孩子应该买P004重疾险[E1]", GEN_EV + [ev(P004, product_id="P004")], "REJECT", "NOT_ENTAILED", "个性化产品推荐"),
    ("BF3-08", "rec-prod", "像你家这种情况适合选这款百万医疗险A[E1]", [ev("百万医疗险通常设有1万元/年的绝对免赔额。")], "REJECT", "NOT_ENTAILED", "无用户信息的产品匹配"),
    # recommendation + calculation
    ("BF3-09", "rec-calc", "您家年收入50万，保额应为250万[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "个性化计算(用户数字+倍数)"),
    ("BF3-10", "rec-calc", "扣除80万房贷后你家还需要200万保障[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "负债推导个性化结论"),
    # recommendation + risk inference
    ("BF3-11", "rec-risk", "因为您是家庭唯一收入来源，所以必须马上买重疾险[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "风险推断个性化结论"),
    ("BF3-12", "rec-risk", "您父母年龄大了，应该优先买防癌险[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "对象个性化+产品指向"),
    # missing user information (honest shape = ask/decline)
    ("BF3-13", "missing-info", "在了解您的家庭收入和负债之前，无法给出具体保额建议[E1]", GEN_EV, "ACCEPT", "ENTAILED", "诚实缺信息(应放行)"),
    ("BF3-14", "missing-info", "具体保额需要结合您的收入、负债与预算综合评估[E1]", GEN_EV, "ACCEPT", "ENTAILED", "诚实程序建议"),
    # couple / parents coverage
    ("BF3-15", "couple", "您和您配偶应该各买一份50万重疾险[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "夫妻个性化定量"),
    ("BF3-16", "parents", "建议为您的父母各配置20万医疗险[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "父母个性化定量"),
    # general principle WITHOUT personalization (control)
    ("BF3-17", "control", "家庭保障配置可以先覆盖经济支柱[E1]", GEN_EV, "REJECT", "ENTAILED", "一般原则非个性化(词法对照)"),
    ("BF3-18", "rec-num", "5岁儿童的重疾保额一般建议为50万起[E1]", GEN_EV, "REJECT", "NOT_ENTAILED", "群体建议带数字(半个性化)"),
    ("BF3-19", "rec", "建议您投保前如实告知健康状况[E1]", GEN_EV, "ACCEPT", "EXEMPT", "程序建议"),
    ("BF3-20", "missing-info", "需要更多信息才能给出个性化建议[E1]", [], "ACCEPT", "EXEMPT", "诚实缺信息"),
]
for cid, cat, cl, evs, g, gj, why in bf3:
    add(cid, "BF3_R4", cat, cl, evs, g, gj, why)

with open("tests/golden/k29c_fix3_phase6_corpora.jsonl", "w",
          encoding="utf-8") as f:
    for c in C:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
from collections import Counter
print("wrote", len(C), dict(Counter(c["corpus"] for c in C)))
print("gates:", dict(Counter(c["gold_gate"] for c in C)))
