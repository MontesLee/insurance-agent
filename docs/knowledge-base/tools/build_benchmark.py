# -*- coding: utf-8 -*-
"""Build docs/knowledge-base/retrieval-benchmark-v1.yaml.

Every positive case carries `expected_fact` — an anchor phrase that MUST
exist verbatim (whitespace-insensitive) in the expected document's
corpus file. The builder refuses to emit a case whose anchor is missing,
so no self-invented knowledge points can slip in.
"""
from __future__ import annotations

import re
from pathlib import Path

KB = Path(__file__).resolve().parents[1]
CORPUS = KB / "sources" / "corpus"

CASES = [
    # ---------------- L1 (30) ----------------
    dict(case_id="RB-L1-001", query="保险公司注册资本的最低限额是多少",
         expected_document_id="L1-01", layer="L1", risk="HIGH",
         expected_fact="注册资本的最低限额为人民币二亿元",
         note="保险法第六十九条"),
    dict(case_id="RB-L1-002", query="投保人故意不履行如实告知义务，保险公司能否解除合同",
         expected_document_id="L1-01", layer="L1", risk="HIGH",
         expected_fact="故意不履行如实告知义务", note="保险法第十六条"),
    dict(case_id="RB-L1-003", query="金融机构销售产品时产品风险等级与机构评定不一致怎么办",
         expected_document_id="L1-02", layer="L1", risk="HIGH",
         expected_fact="孰高", note="适当性办法 风险等级孰高原则"),
    dict(case_id="RB-L1-004", query="金融机构产品适当性管理办法从什么时候开始施行",
         expected_document_id="L1-02", layer="L1", risk="HIGH",
         expected_fact="自2026年2月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-005", query="保险销售行为管理覆盖哪些环节",
         expected_document_id="L1-03", layer="L1", risk="MEDIUM",
         expected_fact="保险销售前行为、保险销售中行为和保险销售后行为", note="售前售中售后"),
    dict(case_id="RB-L1-006", query="保险销售行为管理办法的施行日期",
         expected_document_id="L1-03", layer="L1", risk="HIGH",
         expected_fact="自2024年3月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-007", query="长期健康保险产品的犹豫期不得少于多少天",
         expected_document_id="L1-04", layer="L1", risk="HIGH",
         expected_fact="犹豫期不得少于15天", note="健康险办法第十五条"),
    dict(case_id="RB-L1-008", query="保险公司销售长期个人健康保险产品后需要在犹豫期内做什么",
         expected_document_id="L1-04", layer="L1", risk="HIGH",
         expected_fact="应当在犹豫期内对投保人进行回访", note="健康险办法第四十四条"),
    dict(case_id="RB-L1-009", query="保险公司销售人身保险产品时应当向消费者披露哪些产品材料",
         expected_document_id="L1-05", layer="L1", risk="MEDIUM",
         expected_fact="人身保险产品说明书", note="信披办法材料清单"),
    dict(case_id="RB-L1-010", query="人身保险产品按设计类型分为哪几种",
         expected_document_id="L1-05", layer="L1", risk="MEDIUM",
         expected_fact="普通型、分红型、万能型、投资连结型", note="产品分类"),
    dict(case_id="RB-L1-011", query="互联网保险业务可以通过什么平台经营",
         expected_document_id="L1-06", layer="L1", risk="MEDIUM",
         expected_fact="自营网络平台", note="互联网保险办法"),
    dict(case_id="RB-L1-012", query="互联网保险业务监管办法什么时候施行",
         expected_document_id="L1-06", layer="L1", risk="HIGH",
         expected_fact="自2021年2月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-013", query="经营保险代理业务需要取得什么许可",
         expected_document_id="L1-07", layer="L1", risk="MEDIUM",
         expected_fact="经营保险代理业务的许可证", note="代理人监管规定 业务许可"),
    dict(case_id="RB-L1-014", query="保险销售从业人员应当在何处进行执业登记",
         expected_document_id="L1-07", layer="L1", risk="MEDIUM",
         expected_fact="执业登记", note="代理人监管规定"),
    dict(case_id="RB-L1-015", query="保险经纪人是代表谁的利益办理保险业务",
         expected_document_id="L1-08", layer="L1", risk="MEDIUM",
         expected_fact="投保人", note="经纪人监管规定"),
    dict(case_id="RB-L1-016", query="保险经纪人监管规定的施行日期",
         expected_document_id="L1-08", layer="L1", risk="HIGH",
         expected_fact="自2018年5月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-017", query="保险公司设立分支机构需要经过什么程序",
         expected_document_id="L1-09", layer="L1", risk="MEDIUM",
         expected_fact="分支机构", note="保险公司管理规定 机构变更"),
    dict(case_id="RB-L1-018", query="保险公司管理规定的施行日期是哪一天",
         expected_document_id="L1-09", layer="L1", risk="HIGH",
         expected_fact="自2009年10月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-019", query="保险保障基金由谁缴纳、按什么缴纳",
         expected_document_id="L1-10", layer="L1", risk="MEDIUM",
         expected_fact="缴纳", note="保障基金办法"),
    dict(case_id="RB-L1-020", query="人寿保险公司破产时保单持有人能够获得什么救助",
         expected_document_id="L1-10", layer="L1", risk="HIGH",
         expected_fact="救助", note="保障基金办法 救助条款"),
    dict(case_id="RB-L1-021", query="偿付能力达标公司需要满足哪些条件",
         expected_document_id="L1-11", layer="L1", risk="HIGH",
         expected_fact="风险综合评级", note="偿付能力规定 偿付能力达标三条件"),
    dict(case_id="RB-L1-022", query="保险公司偿付能力管理规定的施行日期",
         expected_document_id="L1-11", layer="L1", risk="HIGH",
         expected_fact="自2021年3月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-023", query="银行保险机构收到消费投诉后多久作出处理决定",
         expected_document_id="L1-12", layer="L1", risk="HIGH",
         expected_fact="15日内作出处理决定", note="投诉办法"),
    dict(case_id="RB-L1-024", query="哪些机构适用银行业保险业消费投诉处理管理办法",
         expected_document_id="L1-12", layer="L1", risk="MEDIUM",
         expected_fact="投诉", note="适用范围"),
    dict(case_id="RB-L1-025", query="人身保险公司应当为投保人和被保险人提供哪些基本服务",
         expected_document_id="L1-13", layer="L1", risk="MEDIUM",
         expected_fact="服务", note="基本服务规定"),
    dict(case_id="RB-L1-026", query="人身保险业务基本服务规定的施行日期",
         expected_document_id="L1-13", layer="L1", risk="HIGH",
         expected_fact="自2010年5月1日起施行", note="VERSION/日期"),
    dict(case_id="RB-L1-027", query="人身保险公司的保险条款和保险费率需要审批还是备案",
         expected_document_id="L1-14", layer="L1", risk="HIGH",
         expected_fact="审批或者备案", note="条款费率管理办法"),
    dict(case_id="RB-L1-028", query="人身保险公司保险条款和保险费率管理办法现行版本是哪年修订的",
         expected_document_id="L1-14", layer="L1", risk="HIGH",
         expected_fact="2015年第3号", note="VERSION/2015修订版头"),
    dict(case_id="RB-L1-029", query="保险销售可回溯资料应当保存多长时间",
         expected_document_id="L1-15", layer="L1", risk="HIGH",
         expected_fact="10年", note="可回溯办法保存期限"),
    dict(case_id="RB-L1-030", query="银行保险机构董事近亲属与机构发生的关联交易要经过什么程序",
         expected_document_id="L1-21", layer="L1", risk="HIGH",
         expected_fact="关联交易控制委员会", note="VERSION-CONFLICT/2025修正新增第四十五条第三款"),
    # ---------------- L2 (15) ----------------
    dict(case_id="RB-L2-001", query="2020版重疾规范规定必须包含哪三种轻度疾病",
         expected_document_id="L2-01", layer="L2", risk="HIGH",
         expected_fact="恶性肿瘤——轻度、较轻急性心肌梗死、轻度脑中风后遗症", note="三种轻度疾病"),
    dict(case_id="RB-L2-002", query="严重溃疡性结肠炎的重疾定义是什么",
         expected_document_id="L2-01", layer="L2", risk="HIGH",
         expected_fact="严重溃疡性结肠炎", note="重疾定义3.1.1.28"),
    dict(case_id="RB-L2-003", query="重大疾病保险的疾病定义使用规范由哪些组织修订",
         expected_document_id="L2-01", layer="L2", risk="MEDIUM",
         expected_fact="中国医师协会", note="发布主体"),
    dict(case_id="RB-L2-004", query="2020版重疾定义是对哪一年的定义进行的修订",
         expected_document_id="L2-01", layer="L2", risk="MEDIUM",
         expected_fact="2007年制定的重大疾病保险的疾病定义", note="修订背景"),
    dict(case_id="RB-L2-005", query="轻度疾病的累计保险金额与重度疾病有什么比例限制",
         expected_document_id="L2-01", layer="L2", risk="HIGH",
         expected_fact="不应高于", note="轻度/轻度比例限制"),
    dict(case_id="RB-L2-006", query="重疾定义修订前后严重脑中风后遗症的定义有什么变化",
         expected_document_id="L2-02", layer="L2", risk="MEDIUM",
         expected_fact="脑中风", note="对比表"),
    dict(case_id="RB-L2-007", query="重疾定义对比表中恶性肿瘤定义修订前后的差异",
         expected_document_id="L2-02", layer="L2", risk="MEDIUM",
         expected_fact="恶性肿瘤", note="对比表"),
    dict(case_id="RB-L2-008", query="哪里可以查到重疾定义修订前和修订后的全文对照",
         expected_document_id="L2-02", layer="L2", risk="LOW",
         expected_fact="修订前", note="对比表结构"),
    dict(case_id="RB-L2-009", query="不符合2020版定义的重疾产品最迟可以销售到什么时候",
         expected_document_id="L2-03", layer="L2", risk="HIGH",
         expected_fact="2021年1月31日", note="VERSION-CONFLICT/旧定义停售"),
    dict(case_id="RB-L2-010", query="重疾新旧定义切换时监管对销售行为有什么禁止性要求",
         expected_document_id="L2-03", layer="L2", risk="HIGH",
         expected_fact="严禁借新老定义切换进行不当炒作", note="监管禁令"),
    dict(case_id="RB-L2-011", query="新开发的成年人重大疾病产品应当符合什么要求",
         expected_document_id="L2-03", layer="L2", risk="MEDIUM",
         expected_fact="十八周岁", note="适用范围"),
    dict(case_id="RB-L2-012", query="中国人身保险业经验生命表2025从什么时候开始使用",
         expected_document_id="L2-05", layer="L2", risk="HIGH",
         expected_fact="自2026年1月1日起实施", note="VERSION/生命表启用"),
    dict(case_id="RB-L2-013", query="年金保险评估法定责任准备金应当采用哪张生命表",
         expected_document_id="L2-05", layer="L2", risk="HIGH",
         expected_fact="养老类业务表", note="生命表适用规则"),
    dict(case_id="RB-L2-014", query="健康保险和定期寿险准备金评估用哪张生命表",
         expected_document_id="L2-05", layer="L2", risk="HIGH",
         expected_fact="非养老类业务一表", note="生命表适用规则"),
    dict(case_id="RB-L2-015", query="单一生命体表有什么用途",
         expected_document_id="L2-05", layer="L2", risk="MEDIUM",
         expected_fact="单一生命体表", note="第四套生命表新增表种"),
    # ---------------- Cross-domain (5) ----------------
    dict(case_id="RB-X-001", query="消费者遇到保险销售误导应该怎么投诉维权",
         expected_document_id="L1-12", secondary="L1-03", layer="CROSS", risk="MEDIUM",
         expected_fact="投诉", note="销售行为+投诉处理交叉"),
    dict(case_id="RB-X-002", query="在网上销售保险需要遵守哪些专门的监管规定",
         expected_document_id="L1-06", secondary="L1-03", layer="CROSS", risk="MEDIUM",
         expected_fact="互联网保险业务", note="互联网保险+销售行为交叉"),
    dict(case_id="RB-X-003", query="保险公司破产了消费者的人寿保险保单怎么办",
         expected_document_id="L1-10", secondary="L1-01", layer="CROSS", risk="HIGH",
         expected_fact="人寿保险", note="保障基金+保险法交叉"),
    dict(case_id="RB-X-004", query="买重疾险时新旧疾病定义有什么区别需要注意什么",
         expected_document_id="L2-01", secondary="L2-03", layer="CROSS", risk="MEDIUM",
         expected_fact="2020年修订版", note="规范+通知交叉"),
    dict(case_id="RB-X-005", query="保险公司与股东之间的关联交易受什么监管约束",
         expected_document_id="L1-21", secondary="L1-09", layer="CROSS", risk="MEDIUM",
         expected_fact="关联交易", note="关联交易+公司治理交叉"),
]

NEGATIVE = [
    dict(case_id="RB-N-001", query="如何办理机动车驾驶证换证手续"),
    dict(case_id="RB-N-002", query="社会保险里的养老保险退休后怎么办理领取手续"),
    dict(case_id="RB-N-003", query="医院门诊挂号预约有哪些方式"),
    dict(case_id="RB-N-004", query="机动车年检流程是怎样的"),
    dict(case_id="RB-N-005", query="明天天气怎么样适合出游吗"),
    dict(case_id="RB-N-006", query="未成年人办理身份证需要什么材料"),
    dict(case_id="RB-N-007", query="个人所得税专项附加扣除怎么填报"),
]


def esc(s):
    s = str(s)
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def main() -> None:
    errors = []
    for c in CASES:
        f = CORPUS / f"{c['expected_document_id']}.md"
        if not f.exists():
            errors.append(f"{c['case_id']}: corpus missing {f.name}")
            continue
        compact = "".join(f.read_text(encoding="utf-8").split())
        if "".join(c["expected_fact"].split()) not in compact:
            errors.append(f"{c['case_id']}: fact anchor not in corpus: {c['expected_fact']}")
    if errors:
        print("FACT ANCHOR ERRORS:")
        for e in errors:
            print(" -", e)
        raise SystemExit(1)

    lines = [
        "# WeKnora Insurance KB v1.0 — Retrieval Benchmark v1",
        "# 50 positive cases (L1=30, L2=15, CROSS=5) + 7 negative cases.",
        "# Every positive case's expected_fact is verified verbatim against the",
        "# expected document's corpus file at build time (build_benchmark.py).",
        "# Layers: L1=法律/监管规章 L2=行业标准 CROSS=跨文档 NEGATIVE=无关/近域负例",
        "",
    ]
    for c in CASES:
        lines += [
            f"{c['case_id']}:",
            f"  query: {esc(c['query'])}",
            f"  expected_document_id: {c['expected_document_id']}",
            f"  secondary_document_id: {esc(c.get('secondary', ''))}",
            f"  expected_source: {esc('docs/knowledge-base/sources/corpus/' + c['expected_document_id'] + '.md')}",
            f"  expected_layer: {c['layer']}",
            f"  expected_fact: {esc(c['expected_fact'])}",
            f"  retrieval_required: true",
            f"  qualification_required: true",
            f"  risk_level: {c['risk']}",
            f"  claim_support_required: {c['risk'] == 'HIGH'}",
            f"  note: {esc(c.get('note', ''))}",
            "",
        ]
    lines.append("# ---- Negative retrieval (must return no relevant hit) ----")
    for c in NEGATIVE:
        lines += [
            f"{c['case_id']}:",
            f"  query: {esc(c['query'])}",
            f"  expected_document_id: null",
            f"  expected_layer: NEGATIVE",
            f"  retrieval_required: true",
            f"  qualification_required: false",
            f"  risk_level: LOW",
            f"  claim_support_required: false",
            f"  note: {esc('与保险无关或关键词相近但不属于目标法规范围')}",
            "",
        ]
    out = KB / "retrieval-benchmark-v1.yaml"
    out.write_text("\n".join(lines), encoding="utf-8")
    n_pos = len(CASES)
    n_neg = len(NEGATIVE)
    print(f"benchmark written: {out} ({n_pos} positive + {n_neg} negative)")
    print(
        "layer counts: L1=%d L2=%d CROSS=%d"
        % (
            sum(1 for c in CASES if c["layer"] == "L1"),
            sum(1 for c in CASES if c["layer"] == "L2"),
            sum(1 for c in CASES if c["layer"] == "CROSS"),
        )
    )


if __name__ == "__main__":
    main()
