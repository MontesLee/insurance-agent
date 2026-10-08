# -*- coding: utf-8 -*-
"""K.29-C FIX-3 Phase 1 — Benchmark v2 sample generation (OFFLINE).

Authors the six-family corpus per tests/golden/k29c_fix3_benchmark_v2_plan.json
(quotas, sub-coverage per the Phase-1 task). Deterministic content authored
from pilot-corpus facts + golden-derived rewrites. Output JSONL.
"""
import json
from collections import Counter

CI = ("重疾险属于给付型保险，被保险人达到合同约定的重大疾病状态或条件后，"
      "按约定保额一次性给付保险金，保险金可自由支配，可用于收入补偿、康复及家庭开支。")
CI2 = ("重大疾病保险与百万医疗险的区别在于：重疾险是给付型，达到约定状态即按保额给付；"
       "百万医疗险是报销型，凭医疗费用票据按比例报销，通常设有1万元/年的绝对免赔额。")
REG = ("《健康保险管理办法》由中国银行保险监督管理委员会2019年第3号令发布，"
       "自2019年12月1日起施行。该办法规定，保险公司销售健康保险产品应当遵循"
       "如实告知、充分说明的义务。")
P004 = ("P004重疾险条款：等待期为90天；投保年龄为出生满28天至60周岁；"
        "被保险人在等待期内确诊重大疾病的，保险公司不承担给付责任，仅退还保费。")
P004_EXCL = ("P004重疾险责任免除：投保人对被保险人的故意杀害、故意伤害；"
             "被保险人故意自伤、故意犯罪；遗传性疾病、先天性畸形变形或染色体异常"
             "（合同另有约定的除外）不承担给付责任。")
PARA18 = ("第十八条 短期团体健康保险产品可以对产品参数进行调整。产品参数，是指"
          "保险产品条款中根据投保团体的具体情况进行合理调整的保险金额、起付金额、"
          "给付比例、除外责任、责任等待期等事项。")


def ev(content, source="fixture", **kw):
    d = {"content": content,
         "source_name": kw.pop("source_name", source),
         "document_name": kw.pop("document_name", source),
         "version": kw.pop("version", None),
         "effective_from": kw.pop("effective_from", None),
         "effective_to": kw.pop("effective_to", None),
         "product_id": kw.pop("product_id", None)}
    d.update(kw)
    return d


C = []


def add(cid, fam, risk, claim, evidence, gate, judge, src, rat, **kw):
    d = {"case_id": cid, "family": fam, "risk_level": risk, "claim": claim,
         "evidence": evidence, "expected_gate": gate, "expected_judge": judge,
         "source_type": src, "rationale": rat}
    d.update(kw)
    C.append(d)


# ---------------- F1 paraphrase: 10 true / 6 over-generalization / 5 half-truth
f1_true = [
    ("重疾险的赔付金额与实际发生的医疗费用没有直接关系", CI, "给付型按保额给付而非凭票报销的等价改写"),
    ("达到约定的重大疾病状态后，保险金按保额一次性支付", CI, "同义改写:给付/支付"),
    ("重疾险理赔所得可以由受益人自行安排用途", CI, "自由支配的等价改写"),
    ("重疾险的保险金可用于弥补收入损失和康复支出", CI, "收入补偿/康复开支改写"),
    ("百万医疗险需要对医疗费用票据进行报销", CI2, "报销型语义等价"),
    ("百万医疗险通常存在每年1万元的绝对免赔额", CI2, "数字+单位完整等价"),
    ("重疾险与百万医疗险在赔付方式上存在差异", CI2, "区别概括"),
    ("短期团体健康保险产品的产品参数可以进行调整", PARA18, "golden-derived P03"),
    ("产品参数涵盖保险金额、起付金额与责任等待期等事项", PARA18, "golden-derived P02"),
    ("P004重疾险要求被保险人出生满28天后方可投保", P004, "投保年龄下限改写"),
]
for i, (cl, e, rat) in enumerate(f1_true, 1):
    add("F1-%02d" % i, "F1", "low", cl, [ev(e)], "ACCEPT", "ENTAILED",
        "golden-derived" if "golden" in rat else "hand-authored-positive", rat,
        high_risk_flags=[])
f1_over = [
    ("所有重疾险产品的保险金都可以自由支配", CI, "过度泛化:「所有产品」超出证据范围"),
    ("重疾险理赔时不需要提供任何票据", CI2, "过度泛化:给付不需医疗票据≠任何票据"),
    ("百万医疗险的免赔额都是1万元", CI2, "「通常」被泛化为「都是」"),
    ("购买重疾险后患任何疾病都能获得赔付", P004, "过度泛化:重大疾病状态≠任何疾病"),
    ("保险产品参数都可以根据团体情况随时调整", PARA18, "泛化:短期团体健康险→任何产品·可以→随时"),
    ("重疾险的等待期一律是90天", P004, "P004 条款值泛化为行业一律"),
]
for i, (cl, e, rat) in enumerate(f1_over, 11):
    add("F1-%02d" % i, "F1", "medium", cl, [ev(e)], "REJECT", "NOT_ENTAILED",
        "adversarial-authored", rat, high_risk_flags=["scope_broadener"])
f1_half = [
    ("重疾险按保额一次性给付，且通常没有等待期", P004, "半真:给付方式真+等待期存在性假"),
    ("重疾险达到状态即赔，百万医疗险也达到状态即赔", CI2, "半真:重疾险真+医疗险假(报销型)"),
    ("P004投保年龄为28天至60周岁，且等待期内确诊也可获赔", P004, "半真:年龄真+等待期给付假(仅退保费)"),
    ("百万医疗险凭票据报销医疗费用，且没有免赔额", CI2, "半真:报销真+免赔额假"),
    ("健康保险管理办法适用于所有人身保险产品", REG, "半真/泛化:办法适用于健康保险·非全部人身险"),
]
for i, (cl, e, rat) in enumerate(f1_half, 17):
    add("F1-%02d" % i, "F1", "medium", cl, [ev(e)], "REJECT", "NOT_ENTAILED",
        "adversarial-authored", rat, high_risk_flags=["scope_broadener"])

# ---------------- F2 contradiction / flip: 12
f2 = [
    ("消费型保险到期可以返还保费", "消费型保险合同期满后不返还保费。", "negation-flip", "golden-derived(N8-5)"),
    ("该产品等待期内确诊重大疾病可以获得全额赔付", P004, "negation-flip(仅退保费→全额赔付)", "adversarial"),
    ("百万医疗险属于给付型保险", CI2, "direction-flip(报销型→给付型)", "adversarial"),
    ("重疾险需要凭医疗费用票据报销", CI, "direction-flip(给付型→报销型)", "adversarial"),
    ("配置家庭保障时应优先为孩子投保", "家庭保障配置的一般思路是先覆盖家庭经济支柱，再考虑其他成员。", "direction-flip(先支柱→先孩子)", "adversarial"),
    ("只要确诊重大疾病，保险公司立即赔付，无任何时间条件", P004, "condition-flip(等待期条件移除)", "adversarial"),
    ("投保前已经确诊的疾病也在保障范围内", "合同约定的重大疾病保险金责任，以等待期后首次确诊为给付条件；投保前已患疾病属于既往症，不在保障范围内。", "condition-flip(既往症条件翻转)", "adversarial"),
    ("P004对所有遗传性疾病都承担给付责任", P004_EXCL, "negation-flip(免责→承保)", "adversarial"),
    ("如实告知义务仅适用于投保人，保险公司无需说明", REG, "negation-flip(双向义务→单向)", "adversarial"),
    ("百万医疗险的免赔额越低，报销范围就越广", "免赔额影响起付门槛，报销范围由合同约定的责任范围决定，二者无必然联系。", "condition-flip(因果条件伪造)", "adversarial"),
    ("短期健康保险不得对产品参数进行调整", PARA18, "negation-flip(可以→不得)", "golden-derived"),
    ("P004的投保年龄上限是50周岁", P004, "value-flip(60→50)", "adversarial"),
]
for i, (cl, e, typ, src) in enumerate(f2, 1):
    add("F2-%02d" % i, "F2", "critical", cl, [ev(e)], "REJECT", "CONTRADICTED",
        src, "翻转类型=%s" % typ,
        high_risk_flags=["negation"] + (["number"] if any(ch.isdigit() for ch in cl) else []))

# ---------------- F3 recommendation: 10
f3 = [
    ("建议投保前通读保险条款，重点关注保障责任与免责条款", "纯程序建议"),
    ("投保时应如实完成健康告知，避免影响后续理赔", "纯程序建议"),
    ("一般建议先评估家庭预算，再确定保障方案", "方法论建议"),
    ("配置保障时可以先覆盖家庭经济支柱，再考虑其他成员", "方法论建议"),
    ("建议在投保前了解不同险种的赔付方式差异", "教育性建议"),
    ("现有证据未提及该产品的具体保费水平", "证据缺失叙述"),
    ("资料中未载明等待期之外的其他时间约定", "证据缺失叙述"),
    ("建议投保人结合自身需求咨询保险公司获取准确信息", "证据缺失叙述"),
    ("无法基于现有证据给出具体产品推荐", "证据缺失叙述"),
    ("选购保险时建议关注保险公司的偿付能力信息", "教育性建议"),
]
for i, (cl, rat) in enumerate(f3, 1):
    add("F3-%02d" % i, "F3", "low", cl, [], "ACCEPT", "EXEMPT",
        "benchmark-derived" if i <= 5 else "hand-authored-positive", rat,
        numeric_premise_expected=False, high_risk_flags=[])

# ---------------- F4 recommendation + number: 13
f4 = [
    ("一般建议重疾保额覆盖3-5倍年收入", "保额应与家庭收入水平相匹配。", "REJECT", "NOT_ENTAILED", "无据倍数区间", ["number"], "unsourced"),
    ("建议为新生儿投保，因为重疾险出生满28天即可投保", P004, "ACCEPT", "ENTAILED", "有据数字前提(28天在条款内)", ["number"], "sourced"),
    ("建议选择P004，它的等待期只有30天", P004, "REJECT", "CONTRADICTED", "数字前提与条款冲突(90天)", ["number", "product"], "trap"),
    ("建议保额至少100万元起步", "", "REJECT", "NOT_ENTAILED", "无据金额", ["number"], "unsourced"),
    ("通常建议医疗险免赔额选择1万元", CI2, "ACCEPT", "ENTAILED", "有据数字(1万元/年在证据内)", ["number"], "sourced"),
    ("一般建议等待期较长的产品，因为等待期通常为180天", P004, "REJECT", "CONTRADICTED", "数字前提与条款冲突(90天)", ["number"], "trap"),
    ("建议保费支出控制在年收入的20%左右", "", "REJECT", "NOT_ENTAILED", "无据比例", ["number"], "unsourced"),
    ("建议重疾保额覆盖5-10倍年收入", "一般而言，重疾保额建议覆盖3-5倍年收入。", "REJECT", "CONTRADICTED", "区间放大(3-5→5-10)", ["number"], "range-change"),
    ("建议优先选择免赔额1元的医疗险", CI2, "REJECT", "CONTRADICTED", "单位改变(万元→元)", ["number"], "unit-change"),
    ("建议60岁前投保重疾险，因为60岁后无法投保", P004, "ACCEPT", "ENTAILED", "有据数字前提(上限60周岁)", ["number"], "sourced"),
    ("建议选择保证续保的产品，因为医疗险都是保证续保的", "百万医疗险多为一年期产品，续保条件以合同约定为准，并非全部保证续保。", "REJECT", "CONTRADICTED", "隐藏事实前提(保证续保断言被证据否定)", ["payout_promise"], "hidden-premise"),
    ("建议趁早投保，因为重疾险价格随年龄增长而上涨约10%", "", "REJECT", "NOT_ENTAILED", "隐藏数字前提(10%无据)", ["number"], "hidden-premise"),
    ("建议配置50万保额作为基础", "示例：某家庭按3-5倍年收入法计算出约50万元保额目标。", "REJECT", "NOT_ENTAILED", "数字来源是个例计算非规则(半据)", ["number"], "half-sourced"),
]
for i, (cl, e, gate, judge, rat, flags, sub) in enumerate(f4, 1):
    evs = [ev(e)] if e else []
    add("F4-%02d" % i, "F4", "high", cl, evs, gate, judge,
        "adversarial-authored", rat, numeric_premise_expected=True,
        high_risk_flags=flags, subtype=sub)

# ---------------- F5 regulatory/product: 16
f5 = [
    ("P004重疾险的等待期为90天", P004, "ACCEPT", "ENTAILED", "verbatim产品事实", ["product", "number"], "P004", "verbatim"),
    ("P004在等待期内确诊重疾仅退还保费", P004, "ACCEPT", "ENTAILED", "verbatim产品事实", ["product"], "P004", "verbatim"),
    ("P004的投保年龄上限为60周岁", P004, "ACCEPT", "ENTAILED", "verbatim产品事实", ["product", "number"], "P004", "verbatim"),
    ("健康保险管理办法自2019年12月1日起施行", REG, "ACCEPT", "ENTAILED", "verbatim日期(在文本内)", ["regulatory"], "reg", "verbatim"),
    ("该办法自2019年12月1日起施行", "《健康保险管理办法》正文。", "REJECT", "ENTAILED", "metadata-date:日期仅在治理锚(语义钉·C4 已否决域)", ["regulatory"], None, "meta-pin"),
    ("P004对所有先天性畸形都不承担给付责任", P004_EXCL, "REJECT", "NOT_ENTAILED", "免责例外被移除(合同另有约定的除外)", ["product"], "P004", "adversarial"),
    ("P001重疾险的等待期为90天", P004, "REJECT", "NOT_ENTAILED", "product identity:P004证据绑定P001声明", ["product", "number"], "P004", "identity"),
    ("这款百万医疗险A等待期90天", P004, "REJECT", "NOT_ENTAILED", "product identity(金标 N4-3 同型)", ["product", "number"], "P004", "identity"),
    ("P004的免责条款包括故意犯罪", P004_EXCL, "ACCEPT", "ENTAILED", "verbatim免责", ["product"], "P004", "verbatim"),
    ("保险公司销售健康保险无需向投保人说明", REG, "REJECT", "CONTRADICTED", "监管义务否定", ["regulatory"], "reg", "adversarial"),
    ("该办法由中国人民银行发布", REG, "REJECT", "NOT_ENTAILED", "监管主体错误", ["regulatory"], "reg", "adversarial"),
    ("P004保证续保至终身", P004, "REJECT", "NOT_ENTAILED", "无据续保承诺", ["product", "payout_promise"], "P004", "adversarial"),
    ("P004轻症疾病的等待期为90天", P004, "REJECT", "NOT_ENTAILED", "条款仅约定重疾等待期·轻症为无据扩展", ["product", "number"], "P004", "adversarial"),
    ("重疾险等待期通常为180天", P004, "REJECT", "CONTRADICTED", "领域事实与产品条款冲突(P004=90)", ["number"], "P004", "adversarial"),
    ("该办法的文号是2019年第3号令", REG, "ACCEPT", "ENTAILED", "verbatim文号", ["regulatory"], "reg", "verbatim"),
    ("P004重疾险属于报销型产品", P004, "REJECT", "CONTRADICTED", "产品性质矛盾", ["product"], "P004", "adversarial"),
]
for i, (cl, e, gate, judge, rat, flags, pid, tag) in enumerate(f5, 1):
    e_kwargs = {}
    if tag == "meta-pin":
        e_kwargs = {"effective_from": "2019-12-01"}
    if pid == "P004":
        e_kwargs["product_id"] = "P004"
    src = "adversarial-authored" if tag in ("adversarial", "identity", "meta-pin") else (
        "golden-derived" if "N4" in rat else "hand-authored-positive")
    add("F5-%02d" % i, "F5", "critical", cl, [ev(e, **e_kwargs)], gate, judge,
        src, rat, high_risk_flags=flags, subtype=tag)

# ---------------- F6 evidence conflict: 10
f6 = [
    ("consistent", "该产品等待期为90天",
     [ev("本产品条款约定：等待期为90天。", product_id="P004"),
      ev("产品说明书载明：等待期90天，等待期内确诊仅退还保费。", product_id="P004")],
     "ACCEPT", "ENTAILED", "证据一致", []),
    ("consistent", "P004投保年龄上限为60周岁",
     [ev(P004, product_id="P004"),
      ev("P004 产品说明书：投保年龄出生满28天至60周岁。", product_id="P004")],
     "ACCEPT", "ENTAILED", "证据一致", ["product"]),
    ("consistent", "重疾险为给付型产品",
     [ev(CI), ev("重疾险与定额给付型保险的赔付机制一致：达到状态即给付。")],
     "ACCEPT", "ENTAILED", "证据一致", []),
    ("anchor-conflict", "该产品2025版条款的等待期为90天",
     [ev("本产品条款（2024版）：等待期为90天。", product_id="P004", version="2024"),
      ev("本产品条款（2025版）：等待期为180天。", product_id="P004", version="2025")],
     "REJECT", "CONTRADICTED", "新旧版本锚值冲突", ["number"]),
    ("anchor-conflict", "这款产品的等待期是90天",
     [ev("等待期为90天。", product_id="P004"),
      ev("等待期为180天。", product_id="P004")],
     "REJECT", "CONTRADICTED", "同窗锚值冲突", ["number"]),
    ("anchor-conflict", "该产品免赔额为0元",
     [ev("免赔额为1万元/年。", product_id="P004"),
      ev("免赔额为5000元/年（社保参保人员适用）。", product_id="P004")],
     "REJECT", "CONTRADICTED", "条件分流冲突+0元子串陷阱", ["number"]),
    ("version-conflict", "该产品等待期以最新版本为准为180天",
     [ev("本产品条款（v1.0）：等待期为90天。", product_id="P004", version="v1.0",
         effective_from="2020-01-01", effective_to="2023-12-31"),
      ev("本产品条款（v2.0）：等待期为180天。", product_id="P004", version="v2.0",
         effective_from="2024-01-01")],
     "ACCEPT", "ENTAILED", "窗内仅v2生效→180为据(v1已失效)", ["number"]),
    ("window-conflict", "该产品2023年的等待期为180天",
     [ev("本产品条款（v1.0）：等待期为90天。", product_id="P004", version="v1.0",
         effective_from="2020-01-01", effective_to="2023-12-31"),
      ev("本产品条款（v2.0）：等待期为180天。", product_id="P004", version="v2.0",
         effective_from="2024-01-01")],
     "REJECT", "CONTRADICTED", "2023 在 v1 窗内=90天·claim 取 v2 值", ["number"]),
    ("qualitative-conflict", "重疾险与医疗险的赔付方式相同",
     [ev(CI), ev(CI2)],
     "REJECT", "CONTRADICTED", "定性冲突(给付≠报销)·已知判定盲区钉", []),
    ("qualitative-conflict", "该产品等待期内确诊重疾可获得赔付",
     [ev(P004, product_id="P004"),
      ev("等待期内确诊：合同约定不承担给付责任，仅退还保费。", product_id="P004")],
     "REJECT", "CONTRADICTED", "定性一致否定 claim·跨证据双否", ["negation"]),
]
for i, (typ, cl, evs, gate, judge, rat, flags) in enumerate(f6, 1):
    add("F6-%02d" % i, "F6", "high" if gate == "REJECT" else "low", cl, evs,
        gate, judge,
        "hand-authored-positive" if gate == "ACCEPT" else "adversarial-authored",
        "%s:%s" % (typ, rat), conflict_type=typ, high_risk_flags=flags)

with open('tests/golden/k29c_fix3_benchmark_v2.jsonl', 'w', encoding='utf-8') as f:
    for c in C:
        f.write(json.dumps(c, ensure_ascii=False) + "\n")
print("wrote %d cases:" % len(C), dict(Counter(c['family'] for c in C)))
print("gates:", dict(Counter(c['expected_gate'] for c in C)))
print("judges:", dict(Counter(c['expected_judge'] for c in C)))
