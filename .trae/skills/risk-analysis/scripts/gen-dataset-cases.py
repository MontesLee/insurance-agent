# 生成 Phase 8 Dataset 端到端用例输入（可复现：每次运行覆盖重写）
#
# 产出：evals/cases/dataset/<case-id>.input.json —— 符合 schemas/risk-analysis-input.schema.json
# 输入是「真实家庭原型」的紧凑规格，本脚本负责补齐 FactValue 四元组、provenance_index、
# 未声明字段的 UNKNOWN 槽位与 missing_from_upstream，避免手写 10 份 600 行 JSON 产生漂移。
import json
import os

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SKILL, "evals", "cases", "dataset")
os.makedirs(OUT, exist_ok=True)

VOCAB = {
    "family_profile": ["age", "gender", "city", "marital_status", "spouse_employment",
                       "spouse_income", "children_count", "children_info", "dependents"],
    "financial_profile": ["household_income", "annual_income", "household_expense",
                          "assets", "cash_flow", "premium_budget"],
    "responsibility_profile": ["mortgage_balance", "liabilities", "children_education",
                               "elderly_support", "family_responsibility"],
    "existing_protection": ["social_insurance_status", "existing_life_coverage",
                            "existing_critical_illness_coverage", "existing_medical_coverage",
                            "existing_accident_coverage", "employer_benefits"],
    "health_profile": ["customer_health", "health_history"],
    "employment_profile": ["occupation", "employment_type", "income_stability"],
}

REQ_TEXT = {
    "life": "关注家庭责任与身故后的收入替代",
    "critical_illness": "关注重疾导致的收入中断",
    "medical": "关注大额医疗支出",
    "accident": "关注意外伤残导致的收入能力损失",
    "savings": "关注子女教育与养老的长期储备",
}


def fv(field, spec):
    """spec = (value, status) | (value, status, confidence) | (value, status, confidence, note)"""
    value, status = spec[0], spec[1]
    conf = spec[2] if len(spec) > 2 else (0.9 if status == "KNOWN" else 0.6)
    note = spec[3] if len(spec) > 3 else None
    entry = {
        "value": value,
        "status": status,
        "source": {
            "layer": "client_state",
            "origin": {"skill": "client-intake", "field": field},
        },
        "confidence": conf,
    }
    if note:
        entry["note"] = note
    if status == "UNKNOWN":
        entry["value"] = None
        entry["confidence"] = 0.0
    return entry


def build(case):
    cid = case["id"]
    fields = case.get("fields", {})
    client_state = {"client_state_version": "1.0", "source": {
        "origin_skill": "client-intake",
        "origin_artifact": "CLIENT_PROFILE.md",
        "profile_path": "client-intake-data/clients/{0}/CLIENT_PROFILE.md".format(cid),
        "adapter": "risk-analysis/scripts/build-client-state.ps1",
        "adapter_version": "1.0",
        "intake_complete": case.get("intake_complete", True),
    }}

    mfu = []
    provenance = []
    for profile, names in VOCAB.items():
        block = {}
        for name in names:
            if name in fields.get(profile, {}):
                spec = fields[profile][name]
                block[name] = fv(name, spec)
            else:
                block[name] = fv(name, (None, "UNKNOWN", 0.0))
                mfu.append({"field": name, "profile": profile,
                            "reason": "MISSING_FROM_UPSTREAM: client-intake 未提供"})
            provenance.append({"client_state_field": "{0}.{1}".format(profile, name),
                               "origin_skill": "client-intake",
                               "origin_field": name,
                               "status": block[name]["status"]})
        client_state[profile] = block

    for extra in case.get("explicit_missing", []):
        mfu.append(extra)
    client_state["missing_from_upstream"] = mfu
    client_state["conflicts"] = case.get("conflicts", [])

    req_types = case.get("requirements", [])
    requirements = []
    for i, rt in enumerate(req_types, start=1):
        requirements.append({
            "requirement_id": "REQ-{0:03d}".format(i),
            "requirement_type": rt,
            "summary": REQ_TEXT[rt],
            "priority": "P1_HIGH",
            "boundary": "requirement_only",
        })

    ra_provided = case.get("ra_provided", True)
    upstream = {
        "client_intake": {
            "provided": case.get("intake_provided", True),
            "intake_complete": case.get("intake_complete", True),
            "profile_path": "client-intake-data/clients/{0}/CLIENT_PROFILE.md".format(cid),
        },
        "requirement_analysis": ({
            "provided": True,
            "analysis_status": case.get("ra_status", "PRELIMINARY"),
            "analysis_scope": req_types,
            "output_path": "requirement_analysis/tmp/{0}.json".format(cid),
            "unknowns": [],
            "assumptions": [],
        } if ra_provided else {
            "provided": False,
            "analysis_status": "NOT_PROVIDED",
            "analysis_scope": [],
            "output_path": "",
            "unknowns": [],
            "assumptions": [],
        }),
    }
    # 注意：requirement_analysis 缺失由 sufficiency 引擎自行登记（source=requirement-analysis），
    # 此处若再写进 client_state.missing_from_upstream 会被映射成 source=client-intake 而重复一条。
    return {
        "input_version": "1.0",
        "client_state": client_state,
        "requirements": requirements,
        "upstream": upstream,
        "analysis_scope": case.get("analysis_scope", ["R1", "R2", "R3", "R4", "R5"]),
        "provenance_index": provenance,
    }


# --------------------------------------------------------------------------- 用例规格
UNKNOWN_FIN = {"assets": (None, "UNKNOWN", 0.0)}

CASES = [
    {
        "id": "ds-001-complete-dual-income",
        "fields": {
            "family_profile": {
                "age": (38, "KNOWN"),
                "gender": ("男", "KNOWN"),
                "city": ("上海", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("在职（全职）", "KNOWN"),
                "spouse_income": (350000, "ESTIMATED", 0.7, "客户口述配偶年收入约 35 万"),
                "children_count": (2, "KNOWN"),
                "children_info": ("儿子 8 岁、女儿 3 岁", "KNOWN"),
                "dependents": ("需赡养双方父母", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (1050000, "ESTIMATED", 0.7, "本人与配偶收入合计估算"),
                "annual_income": (700000, "ESTIMATED", 0.7, "客户口述本人年收入约 70 万"),
                "household_expense": (480000, "ESTIMATED", 0.6, "客户估算家庭年支出约 48 万"),
                "assets": (3200000, "ESTIMATED", 0.5, "自住房产净值 + 存款，客户估算"),
                "cash_flow": (570000, "ESTIMATED", 0.5, "由收入减支出估算"),
                "premium_budget": (60000, "ESTIMATED", 0.5, "客户表示每年可承受约 6 万保费"),
            },
            "responsibility_profile": {
                "mortgage_balance": (2200000, "ESTIMATED", 0.7, "客户口述房贷剩余约 220 万"),
                "liabilities": ("车贷剩余约 12 万", "ESTIMATED", 0.6, "客户口述"),
                "children_education": ("两个孩子国内读完大学，预算约 160 万", "ESTIMATED", 0.5, "客户初步估计"),
                "elderly_support": ("双方父母，每月约 6000 元", "ESTIMATED", 0.6, "客户口述"),
                "family_responsibility": ("房贷 + 两孩教育 + 双方赡养", "INFERRED", 0.5,
                                          "由房贷余额、子女教育预算与赡养支出推导"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (1000000, "KNOWN"),
                "existing_critical_illness_coverage": (300000, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("补充医疗 + 年度体检", "KNOWN"),
            },
            "health_profile": {
                "customer_health": ("轻度脂肪肝", "KNOWN"),
                "health_history": ("父亲有高血压病史", "KNOWN"),
            },
            "employment_profile": {
                "occupation": ("软件架构师", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("较稳定", "KNOWN"),
            },
        },
        "requirements": ["life", "critical_illness", "medical"],
    },
    {
        "id": "ds-002-missing-assets",
        "fields": {
            "family_profile": {
                "age": (35, "KNOWN"),
                "gender": ("男", "KNOWN"),
                "city": ("北京", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("在职（全职）", "KNOWN"),
                "spouse_income": (400000, "ESTIMATED", 0.7, "客户口述配偶年收入约 40 万"),
                "children_count": (1, "KNOWN"),
                "children_info": ("女儿 6 岁，小学一年级", "KNOWN"),
                "dependents": ("无", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (1000000, "ESTIMATED", 0.7, "客户口述家庭年收入约 100 万"),
                "annual_income": (600000, "ESTIMATED", 0.7, "客户口述本人年收入约 60 万"),
                "household_expense": (500000, "ESTIMATED", 0.6, "客户估算家庭年支出约 50 万"),
                "assets": (None, "UNKNOWN", 0.0),
                "cash_flow": (500000, "ESTIMATED", 0.5, "由收入减支出估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": (1500000, "ESTIMATED", 0.7, "客户口述房贷剩余约 150 万"),
                "liabilities": ("无", "KNOWN"),
                "children_education": ("计划国内读完大学，预算约 80 万", "ESTIMATED", 0.5, "客户初步估计"),
                "elderly_support": ("无", "KNOWN"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (500000, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("补充医疗（小额）", "KNOWN"),
            },
            "health_profile": {"customer_health": ("轻度脂肪肝", "KNOWN")},
            "employment_profile": {
                "occupation": ("互联网产品经理", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("较稳定", "KNOWN"),
            },
        },
        "requirements": ["life", "critical_illness"],
    },
    {
        "id": "ds-003-single-no-dependents",
        "fields": {
            "family_profile": {
                "age": (30, "KNOWN"),
                "gender": ("女", "KNOWN"),
                "city": ("深圳", "KNOWN"),
                "marital_status": ("未婚", "KNOWN"),
                "children_count": (0, "KNOWN"),
                "dependents": ("无", "KNOWN"),
            },
            "financial_profile": {
                "annual_income": (300000, "ESTIMATED", 0.7, "客户口述年收入约 30 万"),
                "household_expense": (180000, "ESTIMATED", 0.6, "客户估算年支出约 18 万"),
                "assets": (500000, "ESTIMATED", 0.5, "存款与理财，客户估算"),
                "cash_flow": (120000, "ESTIMATED", 0.5, "由收入减支出估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": ("无", "KNOWN"),
                "liabilities": ("无", "KNOWN"),
                "children_education": ("无", "KNOWN"),
                "elderly_support": ("父母有退休金，无需固定赡养", "KNOWN"),
                "family_responsibility": ("无", "KNOWN"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (0, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("补充医疗", "KNOWN"),
            },
            "health_profile": {"customer_health": ("健康，年度体检正常", "KNOWN")},
            "employment_profile": {
                "occupation": ("设计师", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("较稳定", "KNOWN"),
            },
        },
        "requirements": ["medical", "critical_illness"],
    },
    {
        "id": "ds-004-high-risk-occupation",
        "fields": {
            "family_profile": {
                "age": (42, "KNOWN"),
                "gender": ("男", "KNOWN"),
                "city": ("成都", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("在职（兼职）", "KNOWN"),
                "spouse_income": (80000, "ESTIMATED", 0.6, "客户口述配偶年收入约 8 万"),
                "children_count": (1, "KNOWN"),
                "children_info": ("儿子 12 岁", "KNOWN"),
                "dependents": ("无", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (260000, "ESTIMATED", 0.6, "本人与配偶收入合计估算"),
                "annual_income": (180000, "ESTIMATED", 0.6, "客户口述本人年收入约 18 万"),
                "household_expense": (160000, "ESTIMATED", 0.6, "客户估算家庭年支出约 16 万"),
                "assets": (300000, "ESTIMATED", 0.5, "存款，客户估算"),
                "cash_flow": (100000, "ESTIMATED", 0.5, "由收入减支出估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": (800000, "ESTIMATED", 0.7, "客户口述房贷剩余约 80 万"),
                "liabilities": ("无", "KNOWN"),
                "children_education": ("国内读完大学，预算约 60 万", "ESTIMATED", 0.5, "客户初步估计"),
                "elderly_support": ("每月给父母约 2000 元", "ESTIMATED", 0.6, "客户口述"),
            },
            "existing_protection": {
                "social_insurance_status": ("城乡居民医保", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (0, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("建筑施工意外险（团体，保额较低）", "KNOWN"),
            },
            "health_profile": {"customer_health": ("腰肌劳损", "KNOWN")},
            "employment_profile": {
                "occupation": ("建筑工地施工员", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("项目制，收入随工期波动", "KNOWN"),
            },
        },
        "requirements": ["accident", "life"],
    },
    {
        "id": "ds-005-retired-no-income",
        "fields": {
            "family_profile": {
                "age": (66, "KNOWN"),
                "gender": ("女", "KNOWN"),
                "city": ("杭州", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("已退休", "KNOWN"),
                "children_count": (2, "KNOWN"),
                "children_info": ("子女均已工作", "KNOWN"),
                "dependents": ("无", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (0, "KNOWN", 0.9, "已退休，无工资性收入（养老金另计，本字段仅统计劳动收入）"),
                "annual_income": (0, "KNOWN", 0.9, "已退休，无工资性收入"),
                "household_expense": (120000, "ESTIMATED", 0.6, "客户估算年支出约 12 万"),
                "assets": (1800000, "ESTIMATED", 0.5, "存款与理财，客户估算"),
                "cash_flow": (0, "ESTIMATED", 0.4, "收入为零，结余按零计"),
            },
            "responsibility_profile": {
                "mortgage_balance": ("无", "KNOWN"),
                "liabilities": ("无", "KNOWN"),
                "children_education": ("无", "KNOWN"),
                "elderly_support": ("无", "KNOWN"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保（退休）", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (0, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("无", "KNOWN"),
            },
            "health_profile": {"customer_health": ("高血压，长期服药", "KNOWN")},
            "employment_profile": {
                "occupation": ("已退休", "KNOWN"),
                "employment_type": ("无", "KNOWN"),
                "income_stability": ("不适用", "KNOWN"),
            },
        },
        "requirements": ["medical"],
    },
    {
        "id": "ds-006-all-unknown",
        "fields": {},
        "requirements": [],
        "ra_status": "NEED_MORE_INFORMATION",
    },
    {
        "id": "ds-007-income-conflict",
        "fields": {
            "family_profile": {
                "age": (40, "KNOWN"),
                "gender": ("男", "KNOWN"),
                "city": ("广州", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("在职（全职）", "KNOWN"),
                "children_count": (1, "KNOWN"),
                "children_info": ("女儿 10 岁", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (None, "UNKNOWN", 0.0),
                "annual_income": (None, "UNKNOWN", 0.0),
                "household_expense": (300000, "ESTIMATED", 0.6, "客户估算年支出约 30 万"),
                "assets": (1200000, "ESTIMATED", 0.5, "客户估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": (900000, "ESTIMATED", 0.7, "客户口述房贷剩余约 90 万"),
                "liabilities": ("无", "KNOWN"),
                "children_education": ("国内读完大学，预算约 70 万", "ESTIMATED", 0.5, "客户初步估计"),
                "elderly_support": ("无", "KNOWN"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (500000, "KNOWN"),
                "existing_critical_illness_coverage": (200000, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("补充医疗", "KNOWN"),
            },
            "health_profile": {"customer_health": ("未见异常", "KNOWN")},
            "employment_profile": {
                "occupation": ("销售经理", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("提成制，波动较大", "KNOWN"),
            },
        },
        "conflicts": [
            {"field": "household_income", "candidate_values": ["100 万", "50 万"],
             "reason": "客户先后两次陈述不一致，未澄清前保留 UNKNOWN"}
        ],
        "requirements": ["life", "critical_illness"],
    },
    {
        "id": "ds-008-no-ra-upstream",
        "fields": {
            "family_profile": {
                "age": (33, "KNOWN"),
                "gender": ("男", "KNOWN"),
                "city": ("武汉", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("在职（全职）", "KNOWN"),
                "spouse_income": (150000, "ESTIMATED", 0.6, "客户口述配偶年收入约 15 万"),
                "children_count": (1, "KNOWN"),
                "children_info": ("儿子 2 岁", "KNOWN"),
                "dependents": ("无", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (450000, "ESTIMATED", 0.7, "本人与配偶收入合计估算"),
                "annual_income": (300000, "ESTIMATED", 0.7, "客户口述本人年收入约 30 万"),
                "household_expense": (240000, "ESTIMATED", 0.6, "客户估算家庭年支出约 24 万"),
                "assets": (400000, "ESTIMATED", 0.5, "存款，客户估算"),
                "cash_flow": (210000, "ESTIMATED", 0.5, "由收入减支出估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": (1100000, "ESTIMATED", 0.7, "客户口述房贷剩余约 110 万"),
                "liabilities": ("无", "KNOWN"),
                "children_education": ("国内读完大学，预算约 80 万", "ESTIMATED", 0.5, "客户初步估计"),
                "elderly_support": ("无", "KNOWN"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (0, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("无", "KNOWN"),
            },
            "health_profile": {"customer_health": ("健康", "KNOWN")},
            "employment_profile": {
                "occupation": ("中学教师", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("稳定", "KNOWN"),
            },
        },
        "ra_provided": False,
        "requirements": [],
    },
    {
        "id": "ds-009-single-earner-large-mortgage",
        "fields": {
            "family_profile": {
                "age": (36, "KNOWN"),
                "gender": ("男", "KNOWN"),
                "city": ("北京", "KNOWN"),
                "marital_status": ("已婚", "KNOWN"),
                "spouse_employment": ("全职居家，无收入", "KNOWN"),
                "spouse_income": (0, "KNOWN", 0.9, "配偶当前无收入"),
                "children_count": (2, "KNOWN"),
                "children_info": ("儿子 5 岁、女儿 1 岁", "KNOWN"),
                "dependents": ("需赡养父母", "KNOWN"),
            },
            "financial_profile": {
                "household_income": (500000, "ESTIMATED", 0.7, "家庭唯一收入来源，客户口述约 50 万"),
                "annual_income": (500000, "ESTIMATED", 0.7, "客户口述本人年收入约 50 万"),
                "household_expense": (360000, "ESTIMATED", 0.6, "客户估算家庭年支出约 36 万"),
                "assets": (600000, "ESTIMATED", 0.5, "存款，客户估算"),
                "cash_flow": (140000, "ESTIMATED", 0.5, "由收入减支出估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": (3000000, "ESTIMATED", 0.7, "客户口述房贷剩余约 300 万"),
                "liabilities": ("消费贷约 20 万", "ESTIMATED", 0.6, "客户口述"),
                "children_education": ("两个孩子国内读完大学，预算约 180 万", "ESTIMATED", 0.5, "客户初步估计"),
                "elderly_support": ("每月约 5000 元", "ESTIMATED", 0.6, "客户口述"),
                "family_responsibility": ("唯一收入者 + 房贷 300 万 + 两孩教育 + 赡养", "INFERRED", 0.5,
                                          "由收入结构、房贷余额、教育预算与赡养支出推导"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (0, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("无", "KNOWN"),
            },
            "health_profile": {"customer_health": ("体重超标，血脂偏高", "KNOWN")},
            "employment_profile": {
                "occupation": ("企业中层管理", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("较稳定", "KNOWN"),
            },
        },
        "requirements": ["life", "critical_illness"],
    },
    {
        "id": "ds-010-chinese-negative-tokens",
        "fields": {
            "family_profile": {
                "age": (29, "KNOWN"),
                "gender": ("女", "KNOWN"),
                "city": ("南京", "KNOWN"),
                "marital_status": ("未婚", "KNOWN"),
                "children_count": (0, "KNOWN"),
                "dependents": ("无", "KNOWN"),
            },
            "financial_profile": {
                "annual_income": (240000, "ESTIMATED", 0.7, "客户口述年收入约 24 万"),
                "household_expense": (150000, "ESTIMATED", 0.6, "客户估算年支出约 15 万"),
                "assets": (200000, "ESTIMATED", 0.5, "存款，客户估算"),
                "cash_flow": (90000, "ESTIMATED", 0.5, "由收入减支出估算"),
            },
            "responsibility_profile": {
                "mortgage_balance": ("无房贷", "KNOWN"),
                "liabilities": ("没有负债", "KNOWN"),
                "children_education": ("无子女", "KNOWN"),
                "elderly_support": ("不承担赡养", "KNOWN"),
                "family_responsibility": ("无", "KNOWN"),
            },
            "existing_protection": {
                "social_insurance_status": ("城镇职工医保", "KNOWN"),
                "existing_life_coverage": (0, "KNOWN"),
                "existing_critical_illness_coverage": (0, "KNOWN"),
                "existing_medical_coverage": (0, "KNOWN"),
                "existing_accident_coverage": (0, "KNOWN"),
                "employer_benefits": ("补充医疗", "KNOWN"),
            },
            "health_profile": {"customer_health": ("健康", "KNOWN")},
            "employment_profile": {
                "occupation": ("会计", "KNOWN"),
                "employment_type": ("全职", "KNOWN"),
                "income_stability": ("稳定", "KNOWN"),
            },
        },
        "requirements": ["medical"],
    },
]


def main():
    print("生成 Dataset 用例输入 ->", OUT)
    for case in CASES:
        obj = build(case)
        path = os.path.join(OUT, case["id"] + ".input.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        print("  wrote", case["id"] + ".input.json")
    print("total:", len(CASES))


if __name__ == "__main__":
    main()
