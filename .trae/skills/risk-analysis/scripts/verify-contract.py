"""risk-analysis contract check (dev-time).

1) every schema is a valid draft-07 schema
2) cross-file $ref resolves (client-state / risk / eval-result)
3) a golden instance validates against each schema
4) negative cases must be rejected (no fabricated facts, no UNKNOWN-as-KNOWN,
   no product recommendation leak, no ungrounded conclusion)

Run: <managed-venv-python> scripts/verify-contract.py
"""
"""Phase 2 contract smoke check:
1) every schema is a valid draft-07 schema
2) cross-file $ref (risk.schema.json / eval-result.schema.json / client-state.schema.json) resolves
3) a golden instance validates against each schema
"""
import glob
import json, os, sys

SK = r"D:\Workspace\insurance-agent\.trae\skills\risk-analysis\schemas"
FILES = {
    "client-state.schema.json": None,
    "risk-analysis-input.schema.json": None,
    "risk.schema.json": None,
    "risk-analysis-output.schema.json": None,
    "eval-result.schema.json": None,
}
for n in FILES:
    with open(os.path.join(SK, n), encoding="utf-8-sig") as fh:
        FILES[n] = json.load(fh)

from jsonschema import Draft7Validator

print("=== 1. meta-schema check ===")
bad = 0
for n, s in FILES.items():
    try:
        Draft7Validator.check_schema(s)
        print(f"  OK   {n}")
    except Exception as e:
        bad += 1
        print(f"  FAIL {n}: {e}")
if bad:
    sys.exit(1)

from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

REGISTRY = Registry().with_resources(
    [(n, Resource.from_contents(s)) for n, s in FILES.items()]
)


def validate(name, inst):
    sch = FILES[name]
    v = Draft7Validator(sch, registry=REGISTRY)
    return sorted(v.iter_errors(inst), key=lambda e: list(e.path))


def show(name, inst):
    errs = validate(name, inst)
    print(f"  {name}: ERRORS={len(errs)}")
    for e in errs[:6]:
        print(f"     at {list(e.path)}: {e.message[:130]}")
    return len(errs)


# ---------------- golden ClientState ----------------
def fv(v, st, skill, field, conf=0.9, note=None):
    d = {
        "value": v,
        "status": st,
        "source": {"layer": "client_state", "origin": {"skill": skill, "field": field}},
        "confidence": conf,
    }
    if note:
        d["note"] = note
    return d

client_state = {
    "client_state_version": "1.0",
    "source": {
        "origin_skill": "client-intake",
        "origin_artifact": "CLIENT_PROFILE.md",
        "profile_path": r"D:\...\CLIENT_PROFILE.md",
        "adapter": "risk-analysis/scripts/build-client-state.ps1",
        "adapter_version": "1.0",
        "intake_complete": True,
    },
    "family_profile": {
        "age": fv(35, "KNOWN", "client-intake", "age", 1.0),
        "children_count": fv(1, "KNOWN", "client-intake", "children_count", 1.0),
    },
    "financial_profile": {
        "household_income": fv(1200000, "ESTIMATED", "client-intake", "household_income", 0.7,
                               "客户口述'一年120万左右'"),
        "annual_income": fv(600000, "ESTIMATED", "client-intake", "annual_income", 0.7, "客户口述约60万"),
        "assets": fv(None, "UNKNOWN", "unknown", "assets", 0.0),
    },
    "responsibility_profile": {
        "mortgage_balance": fv(1500000, "ESTIMATED", "client-intake", "mortgage_balance", 0.7, "客户口述约150万"),
    },
    "existing_protection": {
        "existing_critical_illness_coverage": fv(500000, "KNOWN", "client-intake", "existing_ci_insurance", 0.9),
        "social_insurance_status": fv(None, "UNKNOWN", "unknown", "social_insurance_status", 0.0),
    },
    "health_profile": {"customer_health": fv("轻度脂肪肝", "KNOWN", "client-intake", "health_status", 0.9)},
    "employment_profile": {"occupation": fv("互联网产品经理", "KNOWN", "client-intake", "occupation", 1.0)},
    "missing_from_upstream": [
        {"field": "assets", "profile": "financial_profile", "reason": "MISSING_FROM_UPSTREAM: client-intake 未提供"}
    ],
    "conflicts": [],
}

print("=== 2. instance validation ===")
n_err = 0
n_err += show("client-state.schema.json", client_state)

risk_input = {
    "input_version": "1.0",
    "client_state": client_state,
    "requirements": [
        {"requirement_id": "REQ-001", "requirement_type": "critical_illness",
         "summary": "关注收入中断风险", "priority": "P1_HIGH", "boundary": "requirement_only"}
    ],
    "upstream": {
        "client_intake": {"provided": True, "intake_complete": True,
                          "profile_path": r"D:\...\CLIENT_PROFILE.md"},
        "requirement_analysis": {"provided": True, "analysis_status": "PRELIMINARY",
                                 "analysis_scope": ["life", "critical_illness", "accident"],
                                 "output_path": r"D:\...\analysis.json",
                                 "unknowns": [{"field": "assets", "reason": "未提供"}],
                                 "assumptions": []},
    },
    "analysis_scope": ["R1", "R2", "R3", "R4", "R5"],
    "provenance_index": [
        {"client_state_field": "financial_profile.household_income",
         "origin_skill": "client-intake", "origin_field": "household_income", "status": "ESTIMATED"}
    ],
}
n_err += show("risk-analysis-input.schema.json", risk_input)

ev = {
    "evidence_id": "E001",
    "fact": "家庭年收入约 120 万",
    "source": {"layer": "client_state", "field": "financial_profile.household_income",
               "origin": {"skill": "client-intake", "field": "household_income"}, "status": "ESTIMATED"},
}
risk = {
    "risk_id": "R2-001", "risk_category": "R2", "risk_name": "Critical Illness Risk",
    "status": "INFERRED", "risk_exists": True, "materiality": "HIGH",
    "trigger": {"event": "主要收入者确诊重大疾病并长期无法工作"},
    "exposure": {"why_exposed": "家庭收入高度依赖夫妻双方工资，且有持续刚性支出"},
    "potential_impact": {"financial": "收入中断 + 康复支出上升",
                         "lifestyle": "生活水平下降",
                         "family_responsibility": "房贷与子女教育支出仍然持续"},
    "impact_estimate": {"amount": 1500000, "range": {"low": 1000000, "high": 2200000}, "confidence": 0.6},
    "existing_resources": {"cash": None, "investments": None, "income": None,
                           "employer_benefits": None, "social_security": None,
                           "existing_insurance": None, "family_support": None},
    "existing_protection": "已有终身重疾保额约 50 万",
    "coverage_assessment": {"protected_amount": 500000, "unprotected_amount": 1000000,
                            "confidence": 0.5,
                            "liquidity_constraint": "资产情况未知，无法判断可动用流动性"},
    "residual_risk": "HIGH", "severity": "HIGH", "likelihood": "MEDIUM", "priority": "P1",
    "reasoning": "家庭收入 120 万且集中于工资收入；房贷 150 万与子女抚养构成持续刚性支出；现有重疾保额 50 万不足以覆盖收入中断期缺口。",
    "conclusion": "存在较高的收入中断风险，Residual Risk = HIGH。",
    "reasoning_evidence_refs": ["E001", "REQ-001"],
    "evidence": [ev],
    "assumptions": [{"field": "income_replacement_ratio", "assumption": "收入替代按 70% 估算",
                     "reason": "缺乏客户实际支出结构，采用保守通用口径"}],
    "unknowns": [{"field": "assets", "reason": "client-intake 未提供家庭可动用金融资产"}],
    "next_information_needed": [{"field": "assets",
                                 "question": "目前家庭大概有多少可以随时动用的现金或金融资产？",
                                 "why_needed": "用于判断家庭能否独立吸收收入中断带来的现金流冲击"}],
}
n_err += show("risk.schema.json", risk)

eval_ok = {
    "eval_status": "PASS",
    "checks": {k: {"status": "PASS", "score": 1.0, "issues": []} for k in
               ["completeness", "evidence_grounding", "reasoning_consistency",
                "separation", "unknown_integrity", "priority_consistency", "anti_sales"]},
    "failures": [], "repair_required": False, "repair_attempts": 0, "max_repair_attempts": 2,
}
n_err += show("eval-result.schema.json", eval_ok)

output = {
    "output_version": "1.0", "layer": "risk_analysis", "upstream": "requirement_analysis",
    "analysis_status": "PRELIMINARY", "overall_confidence": 0.72,
    "sufficiency": {
        "sufficiency_status": "PARTIAL", "method": "risk_dependency_graph_v1", "sufficiency_score": 0.71,
        "domain_results": [
            {"risk_category": c, "score": 0.7, "status": "PARTIAL",
             "blocking_fields": [], "conflict_fields": []} for c in ["R1", "R2", "R3", "R4", "R5"]],
        "blocking_fields": ["assets"], "conflict_fields": [],
    },
    "family_risk_overview": "双职工家庭，收入集中，有房贷与未成年子女，主要暴露为重疾与身故责任风险。",
    "risks": [risk],
    "risk_matrix": [{"risk_id": "R2-001", "risk_category": "R2", "severity": "HIGH",
                     "likelihood": "MEDIUM", "residual_risk": "HIGH", "priority": "P1"}],
    "top_priorities": [{"risk_id": "R2-001", "priority": "P1", "reason": "收入中断后果严重且现有保障不足"}],
    "unknowns": [{"field": "assets", "reason": "未提供"}],
    "assumptions": [{"field": "income_replacement_ratio", "assumption": "70%", "reason": "通用保守口径"}],
    "next_information_needed": [{"question_id": "Q001",
                                 "question": "目前家庭大概有多少可以随时动用的现金或金融资产？",
                                 "why_needed": "用于判断能否独立吸收收入中断冲击",
                                 "affects_risks": ["R3", "R4"], "priority": "HIGH",
                                 "expected_information_value": 0.82}],
    "missing_from_upstream": [{"source": "client-intake", "field": "assets",
                               "reason": "MISSING_FROM_UPSTREAM: 画像未采集"}],
    "guardrails": {"product_recommendation_included": False, "sales_language_detected": False,
                   "layer_note": "本分析只到风险层，不涉及任何保险产品推荐。"},
    "eval": eval_ok,
}
n_err += show("risk-analysis-output.schema.json", output)

print()
print("=== 3. negative checks (must FAIL) ===")
neg = 0

# N1: UNKNOWN 却给了具体数值（禁止伪造事实）
cs_bad = json.loads(json.dumps(client_state))
cs_bad["financial_profile"]["assets"]["value"] = 3000000
r = validate("client-state.schema.json", cs_bad)
print(f"  N1 UNKNOWN-with-value rejected: {len(r) > 0}")
neg += 0 if r else 1

# N2: ESTIMATED 缺 note（依据必填）
cs_bad2 = json.loads(json.dumps(client_state))
cs_bad2["financial_profile"]["household_income"].pop("note")
r = validate("client-state.schema.json", cs_bad2)
print(f"  N2 ESTIMATED-without-note rejected: {len(r) > 0}")
neg += 0 if r else 1

# N3: 风险结论无 evidence 锚点
risk_bad = json.loads(json.dumps(risk))
risk_bad["reasoning_evidence_refs"] = []
r = validate("risk.schema.json", risk_bad)
print(f"  N3 empty evidence_refs rejected: {len(r) > 0}")
neg += 0 if r else 1

# N4: 不可溯源证据伪装成 KNOWN
risk_bad2 = json.loads(json.dumps(risk))
risk_bad2["evidence"] = [{"evidence_id": "E002", "fact": "客户资产约 300 万",
                          "source": {"layer": "unknown", "field": "assets",
                                     "origin": {"skill": "client-intake", "field": "assets"},
                                     "status": "KNOWN"}}]
r = validate("risk.schema.json", risk_bad2)
print(f"  N4 untraceable-evidence-as-KNOWN rejected: {len(r) > 0}")
neg += 0 if r else 1

# N5: 输出出现产品推荐
out_bad = json.loads(json.dumps(output))
out_bad["guardrails"]["product_recommendation_included"] = True
r = validate("risk-analysis-output.schema.json", out_bad)
print(f"  N5 product_recommendation_included=true rejected: {len(r) > 0}")
neg += 0 if r else 1

print()
print("RESULT:", "ALL GREEN" if (n_err == 0 and neg == 0) else f"PROBLEMS instance_err={n_err} negative_fail={neg}")

# ============================================================================
# 4. Sufficiency stage outputs + unit fixtures（若已生成则校验，未生成则 SKIP）
# ============================================================================
print()
print("=== 4. sufficiency stage outputs / fixtures ===")

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = FILES["risk-analysis-output.schema.json"]

SUBS = {
    "sufficiency": {"$id": "sub-suff.schema.json",
                    "$ref": "risk-analysis-output.schema.json#/properties/sufficiency"},
    "next_information_needed": {"$id": "sub-q.schema.json", "type": "array",
                                "items": OUT["properties"]["next_information_needed"]["items"]},
    "unknowns": {"$id": "sub-unk.schema.json", "type": "array",
                 "items": OUT["properties"]["unknowns"]["items"]},
    "assumptions": {"$id": "sub-asm.schema.json", "type": "array",
                    "items": OUT["properties"]["assumptions"]["items"]},
    "missing_from_upstream": {"$id": "sub-mfu.schema.json", "type": "array",
                              "items": OUT["properties"]["missing_from_upstream"]["items"]},
}
REG2 = Registry().with_resources(
    [(n, Resource.from_contents(s, default_specification=DRAFT7)) for n, s in FILES.items()]
    + [(k, Resource.from_contents(v, default_specification=DRAFT7)) for k, v in SUBS.items()]
)

stage_err = 0
stage_dir = os.path.join(SKILL, "tmp")
stage_files = sorted(glob.glob(os.path.join(stage_dir, "suff_*.json")))
if not stage_files:
    print("  SKIP no stage output (run test-risk-analysis-sufficiency.ps1 first)")
for p in stage_files:
    with open(p, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    n = 0
    for label, sch in SUBS.items():
        errs = list(Draft7Validator(sch, registry=REG2).iter_errors(doc.get(label)))
        n += len(errs)
        for e in errs[:2]:
            print(f"     {label} at {list(e.path)}: {e.message[:110]}")
    stage_err += n
    print(f"  {'OK  ' if n == 0 else 'FAIL'} {os.path.basename(p)} stage_errors={n}")

fx_err = 0
fx_dir = os.path.join(SKILL, "evals", "fixtures", "unit", "sufficiency")
# 该 fixture 是对抗用例：故意让 status=UNKNOWN 带非空 value，用于验证引擎防御，
# 因此它本身不是合法 FactValue，跳过 schema 校验。
FX_SKIP = {"case-unknown-with-value.json"}
fx_files = sorted(glob.glob(os.path.join(fx_dir, "*.json")))
if not fx_files:
    print("  SKIP no fixtures")
for p in fx_files:
    name = os.path.basename(p)
    with open(p, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    if name in FX_SKIP:
        print(f"  SKIP {name} (adversarial: intentionally violates FactValue invariant)")
        continue
    errs = validate("risk-analysis-input.schema.json", doc)
    fx_err += len(errs)
    for e in errs[:2]:
        print(f"     at {list(e.path)}: {e.message[:110]}")
    print(f"  {'OK  ' if not errs else 'FAIL'} {name} input_errors={len(errs)}")

print()
print("STAGE/FIXTURE RESULT:",
      "ALL GREEN" if (stage_err == 0 and fx_err == 0)
      else f"PROBLEMS stage_err={stage_err} fixture_err={fx_err}")

# ============================================================================
# 5. Discovery stage outputs + unit fixtures（若已生成则校验，未生成则 SKIP）
#    risk_candidates 是阶段对象，不是最终 Risk：允许 evidence / refs 为空，
#    但字段名与类型必须与 risk.schema.json 的定义保持一致（供 Phase 5 直接提升）。
# ============================================================================
print()
print("=== 5. discovery stage outputs / fixtures ===")

RISK = FILES["risk.schema.json"]


def rp(name):
    return RISK["properties"][name]


DISC_CANDIDATE = {
    "$id": "disc-candidate.schema.json",
    "title": "RiskCandidate",
    "type": "object",
    "additionalProperties": False,
    "required": ["risk_id", "risk_category", "risk_name", "status", "risk_exists",
                 "discovery_status", "trigger", "exposure", "exposure_signals",
                 "amplifier_signals", "evidence", "reasoning_evidence_refs",
                 "assumptions", "unknowns", "next_information_needed"],
    "properties": {
        "risk_id": rp("risk_id"),
        "risk_category": {"$ref": "risk.schema.json#/definitions/riskCategory"},
        "risk_name": {"type": "string", "minLength": 1},
        "risk_name_zh": {"type": "string", "minLength": 1},
        "status": {"$ref": "risk.schema.json#/definitions/status"},
        "risk_exists": {"type": ["boolean", "null"]},
        "discovery_status": {"type": "string",
                             "enum": ["IDENTIFIED", "NOT_IDENTIFIED", "UNDETERMINED"]},
        "trigger": {"$ref": "risk.schema.json#/properties/trigger"},
        "exposure": {"$ref": "risk.schema.json#/properties/exposure"},
        "evidence": {"type": "array",
                     "items": {"$ref": "risk.schema.json#/definitions/evidenceEntry"}},
        "reasoning_evidence_refs": {
            "type": "array",
            "items": {"type": "string", "pattern": "^(E[0-9]{3}|REQ-[0-9]{3})$"},
        },
        "assumptions": rp("assumptions"),
        "unknowns": rp("unknowns"),
        "next_information_needed": rp("next_information_needed"),
        "exposure_signals": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["signal_id", "target", "op", "state", "fields", "description"],
            "properties": {
                "signal_id": {"type": "string", "minLength": 1},
                "target": {"type": "string", "minLength": 1},
                "op": {"type": "string", "minLength": 1},
                "state": {"type": "string", "enum": ["MATCHED", "ABSENT", "UNRESOLVED"]},
                "fields": {"type": "object"},
                "description": {"type": "string", "minLength": 1},
            }}},
        "amplifier_signals": {"type": "array", "items": {"type": "object"}},
    },
}

REG3 = Registry().with_resources(
    [(n, Resource.from_contents(s, default_specification=DRAFT7)) for n, s in FILES.items()]
    + [(k, Resource.from_contents(v, default_specification=DRAFT7)) for k, v in SUBS.items()]
    + [("disc-candidate.schema.json",
        Resource.from_contents(DISC_CANDIDATE, default_specification=DRAFT7))]
)

CAND_V = Draft7Validator(DISC_CANDIDATE, registry=REG3)
DISC_SKIP = {"disc_integ_suff.json"}  # 该产物来自充分性引擎，不按 discovery 校验

disc_err = 0
disc_files = sorted(glob.glob(os.path.join(SKILL, "tmp", "disc_*.json")))
if not disc_files:
    print("  SKIP no discovery output (run test-risk-analysis-discovery.ps1 first)")
for p in disc_files:
    name = os.path.basename(p)
    if name in DISC_SKIP:
        print(f"  SKIP {name} (sufficiency stage output)")
        continue
    with open(p, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    n = 0
    for label in ("unknowns", "assumptions", "next_information_needed"):
        errs = list(Draft7Validator(SUBS[label], registry=REG3).iter_errors(doc.get(label)))
        n += len(errs)
        for e in errs[:2]:
            print(f"     {label} at {list(e.path)}: {e.message[:110]}")
    seen_ids = set()
    for cand in doc.get("risk_candidates", []):
        errs = list(CAND_V.iter_errors(cand))
        n += len(errs)
        for e in errs[:3]:
            print(f"     candidate {cand.get('risk_id')} at {list(e.path)}: {e.message[:110]}")
        ev_ids = {e["evidence_id"] for e in cand.get("evidence", [])}
        # 锚点必须能在自身证据里找到（UNDETERMINED 允许 0 条，但不得凭空引用）
        for ref in cand.get("reasoning_evidence_refs", []):
            if ref.startswith("E") and ref not in ev_ids:
                n += 1
                print(f"     candidate {cand.get('risk_id')} dangling evidence ref: {ref}")
        if cand.get("risk_id") in seen_ids:
            n += 1
            print(f"     duplicate risk_id: {cand.get('risk_id')}")
        seen_ids.add(cand.get("risk_id"))
        # 三态与 risk_exists 必须一致
        st, ex = cand.get("discovery_status"), cand.get("risk_exists")
        if (st == "IDENTIFIED" and ex is not True) or \
           (st == "NOT_IDENTIFIED" and ex is not False) or \
           (st == "UNDETERMINED" and ex is not None):
            n += 1
            print(f"     candidate {cand.get('risk_id')} state/exists mismatch: {st} / {ex!r}")
    disc_err += n
    print(f"  {'OK  ' if n == 0 else 'FAIL'} {name} discovery_errors={n}")

dfx_err = 0
dfx_dir = os.path.join(SKILL, "evals", "fixtures", "unit", "discovery")
dfx_files = sorted(glob.glob(os.path.join(dfx_dir, "*.json")))
if not dfx_files:
    print("  SKIP no discovery fixtures")
for p in dfx_files:
    with open(p, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    errs = validate("risk-analysis-input.schema.json", doc)
    dfx_err += len(errs)
    for e in errs[:2]:
        print(f"     at {list(e.path)}: {e.message[:110]}")
    print(f"  {'OK  ' if not errs else 'FAIL'} {os.path.basename(p)} input_errors={len(errs)}")

print()
print("DISCOVERY RESULT:",
      "ALL GREEN" if (disc_err == 0 and dfx_err == 0)
      else f"PROBLEMS discovery_err={disc_err} fixture_err={dfx_err}")

# ============================================================================
# 6. Analysis stage outputs（若已生成则校验，未生成则 SKIP）
#    完整 Risk 对象校验：每个 risk 必须严格符合 risk.schema.json
#    （含 additionalProperties:false）；推理锚点不得悬空；risk_exists 必为布尔；
#    NOT_IDENTIFIED（risk_exists=False）须 severity=LOW / residual=LOW / priority=P3；
#    priority 须可由 (severity, likelihood) 经 priority_matrix + overrides 反推一致
#    （确定性复算，与引擎同源，非 LLM）。
# ============================================================================
print()
print("=== 6. analysis stage outputs ===")

RISK = FILES["risk.schema.json"]
RISK_V = Draft7Validator(RISK, registry=REGISTRY)

# 反推 priority 所需规则（与引擎确定性一致）
try:
    _rules_path = os.path.join(SKILL, "resources", "config", "risk-scoring.rules.json")
    RULES = json.load(open(_rules_path, encoding="utf-8-sig"))
    PMATRIX = RULES["priority_matrix"]
    PRANK = RULES["priority_rank"]
    OVERRIDES = RULES["priority_overrides"]
    HAVE_RULES = True
except Exception as e:
    print(f"  WARN cannot load scoring rules ({e}); skip priority re-derivation")
    HAVE_RULES = False


def expected_priority(cat, severity, likelihood, residual, risk_exists):
    """复算引擎 priority：matrix[severity][likelihood] 再顺序应用 overrides。

    与 invoke-risk-analysis-analysis.ps1 的 445/458-464 行逻辑逐字对应：
      max_priority: if rank < mx -> rank = mx
      min_priority: if rank < mn -> rank = mn
    """
    base = PMATRIX[severity][likelihood]
    prio, rank = base, PRANK[base]
    for ov in OVERRIDES:
        c = ov.get("if", {})
        if c.get("category") and c["category"] != cat:
            continue
        if c.get("residual") and c["residual"] != residual:
            continue
        if c.get("likelihood") and c["likelihood"] != likelihood:
            continue
        if "risk_exists" in c and c["risk_exists"] is not None and c["risk_exists"] != risk_exists:
            continue
        if "max_priority" in ov:
            mx = PRANK[ov["max_priority"]]
            if rank < mx:
                prio, rank = ov["max_priority"], mx
        if "min_priority" in ov:
            mn = PRANK[ov["min_priority"]]
            if rank < mn:
                prio, rank = ov["min_priority"], mn
    return prio


# ana_single2 为 ana_single 在同名 discovery 用例单跑分析时的复制产物，重复计数为噪声
ANA_SKIP = {"ana_single2.json"}

ana_err = 0
ana_files = sorted(glob.glob(os.path.join(SKILL, "tmp", "ana_*.json")))
if not ana_files:
    print("  SKIP no analysis output (run test-risk-analysis-analysis.ps1 first)")
for p in ana_files:
    name = os.path.basename(p)
    if name in ANA_SKIP:
        continue
    with open(p, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    if doc.get("stage") != "analysis" or "risks" not in doc:
        continue  # 跳过 discovery 重嵌产物（stage=discovery）与 sufficiency 产物
    n = 0
    seen_ids = set()
    for r in doc["risks"]:
        rid = r.get("risk_id")
        # (a) 完整 schema 校验
        errs = list(RISK_V.iter_errors(r))
        n += len(errs)
        for e in errs[:3]:
            print(f"     {rid} schema at {list(e.path)}: {e.message[:110]}")
        # (b) 悬空 E### 锚点（REQ-### 为跨阶段引用，此处不校验）
        ev_ids = {e["evidence_id"] for e in r.get("evidence", [])}
        for ref in r.get("reasoning_evidence_refs", []):
            if ref.startswith("E") and ref not in ev_ids:
                n += 1
                print(f"     {rid} dangling evidence ref: {ref}")
        # (c) risk_exists 必为布尔（schema 仅声明 type:boolean，未 required，额外契约）
        rx = r.get("risk_exists")
        if not isinstance(rx, bool):
            n += 1
            print(f"     {rid} risk_exists not boolean: {rx!r}")
        # (d) NOT_IDENTIFIED（不成立）约束：低档 severity / residual / priority 封顶 P3
        if rx is False:
            for fld, exp in (("severity", "LOW"), ("residual_risk", "LOW"), ("priority", "P3")):
                if r.get(fld) != exp:
                    n += 1
                    print(f"     {rid} NOT_IDENTIFIED {fld} expected {exp} got {r.get(fld)!r}")
        # (e) priority 反推一致
        if HAVE_RULES and isinstance(rx, bool):
            exp = expected_priority(r.get("risk_category"), r.get("severity"),
                                    r.get("likelihood"), r.get("residual_risk"), rx)
            if exp != r.get("priority"):
                n += 1
                print(f"     {rid} priority mismatch: actual {r.get('priority')} expected {exp} "
                      f"(sev={r.get('severity')} like={r.get('likelihood')} "
                      f"res={r.get('residual_risk')} exists={rx})")
        # 重复 risk_id
        if rid in seen_ids:
            n += 1
            print(f"     duplicate risk_id: {rid}")
        seen_ids.add(rid)
    ana_err += n
    print(f"  {'OK  ' if n == 0 else 'FAIL'} {name} analysis_errors={n}")

print()
print("ANALYSIS RESULT:",
      "ALL GREEN" if ana_err == 0 else f"PROBLEMS analysis_err={ana_err}")

# ============================================================================
# 8. Eval 阶段产物（tmp/evd_*_e.json 正向 / tmp/evn_* 负向）
#    引擎：invoke-risk-analysis-eval.ps1；产物由 test-risk-analysis-eval.ps1 生成。
#    校验：EvalResult schema 合规 + 正向 7 项全 PASS + 负向精确命中目标检查。
# ============================================================================
print()
print("=== 8. eval stage outputs ===")

EVAL = FILES["eval-result.schema.json"]
EVAL_V = Draft7Validator(EVAL, registry=REGISTRY)

CHECK_KEYS = ["completeness", "evidence_grounding", "reasoning_consistency",
              "separation", "unknown_integrity", "priority_consistency", "anti_sales"]

# 负向 fixture → 预期唯一命中的检查，读自 evals/cases/manifest.json（单一真源）
NEG_TARGET = {}
_manifest_path = os.path.join(SKILL, "evals", "cases", "manifest.json")
try:
    with open(_manifest_path, encoding="utf-8-sig") as fh:
        _manifest = json.load(fh)
    for _c in _manifest.get("negative", []):
        NEG_TARGET[_c["fixture"]] = _c["target_check"]
except Exception as e:
    print(f"  WARN cannot load eval manifest ({e}); negative target assertion disabled")

eval_err = 0

def _check_eval_doc(path, expect_status, target=None):
    """返回错误数。target 非空时额外断言：仅 target 一项 FAIL，其余 6 项 PASS。"""
    global eval_err
    name = os.path.basename(path)
    with open(path, encoding="utf-8-sig") as fh:
        doc = json.load(fh)
    n = 0
    # (a) EvalResult schema 合规
    errs = list(EVAL_V.iter_errors(doc))
    n += len(errs)
    for e in errs[:3]:
        print(f"     {name} schema at {list(e.path)}: {e.message[:110]}")
    # (b) 7 项检查齐全
    checks = doc.get("checks", {})
    for k in CHECK_KEYS:
        if k not in checks:
            n += 1
            print(f"     {name} missing check: {k}")
    # (c) eval_status
    st = doc.get("eval_status")
    if st != expect_status:
        n += 1
        print(f"     {name} eval_status expected {expect_status} got {st!r}")
    # (d) failures 只含 BLOCKING；FAIL 时非空
    fail_items = doc.get("failures", [])
    for it in fail_items:
        if it.get("severity") != "BLOCKING":
            n += 1
            print(f"     {name} failures contains non-BLOCKING issue: {it.get('code')}")
    if expect_status == "FAIL" and not fail_items:
        n += 1
        print(f"     {name} eval_status=FAIL but failures is empty")
    if expect_status == "PASS":
        for k in CHECK_KEYS:
            if checks.get(k, {}).get("status") != "PASS":
                n += 1
                print(f"     {name} check [{k}] expected PASS got {checks.get(k, {}).get('status')!r}")
    # (e) 负向：精确命中，且不误伤其他检查
    if target:
        if checks.get(target, {}).get("status") != "FAIL":
            n += 1
            print(f"     {name} target check [{target}] expected FAIL got "
                  f"{checks.get(target, {}).get('status')!r}")
        for k in CHECK_KEYS:
            if k != target and checks.get(k, {}).get("status") != "PASS":
                n += 1
                print(f"     {name} collateral damage: [{k}] should be PASS got "
                      f"{checks.get(k, {}).get('status')!r}")
    eval_err += n
    print(f"  {'OK  ' if n == 0 else 'FAIL'} {name} eval_errors={n}")
    return n

pos_files = sorted(glob.glob(os.path.join(SKILL, "tmp", "evd_*_e.json")))
neg_files = sorted(glob.glob(os.path.join(SKILL, "tmp", "evn_*.json")))

if not pos_files and not neg_files:
    print("  SKIP no eval output (run test-risk-analysis-eval.ps1 first)")

for p in pos_files:
    _check_eval_doc(p, "PASS")

for p in neg_files:
    name = os.path.basename(p)
    # evn_eval-neg-xxx.json.json —— 中间段即 fixture 名
    fixture = name[len("evn_"):]
    if fixture.endswith(".json.json"):
        fixture = fixture[:-len(".json")]
    _check_eval_doc(p, "FAIL", NEG_TARGET.get(fixture))

print()
print("EVAL RESULT:", "ALL GREEN" if eval_err == 0 else f"PROBLEMS eval_err={eval_err}")

# ============================================================================
# 9. repair stage outputs —— 消费 tmp/rpt_*.json（由 test-risk-analysis-repair.ps1 产出）
#    除 schema 与清单断言外，加两条红线断言：
#      · evidence 集合不得被修复改动（禁止补/删证据＝禁止发明事实）
#      · impact_estimate.amount 不得被修复改动（禁止编造量化）
# ============================================================================
print()
print("=== 9. repair stage outputs ===")

REPAIR_MANIFEST = os.path.join(SKILL, "evals", "cases", "repair-manifest.json")

rep_err = 0

def _canon(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)

def _risk_index(doc):
    return {r.get("risk_id"): r for r in doc.get("risks", []) or []}

try:
    with open(REPAIR_MANIFEST, encoding="utf-8-sig") as fh:
        rp_manifest = json.load(fh)
    rp_cases = rp_manifest.get("cases", [])
except Exception as e:
    rp_cases = []
    rep_err += 1
    print(f"  ERROR cannot load repair-manifest.json ({e})")

_fx_base = os.path.join(SKILL, "evals", "fixtures", "unit")

for c in rp_cases:
    name = c["name"]
    dir_key = c.get("dir", "repair")
    fixture = os.path.join(_fx_base, dir_key, c["fixture"])
    ev_p = os.path.join(SKILL, "tmp", f"rpt_{name}_e.json")
    an_p = os.path.join(SKILL, "tmp", f"rpt_{name}_a.json")

    if not os.path.exists(ev_p) or not os.path.exists(an_p):
        rep_err += 1
        print(f"     {name}: MISSING repair output (run test-risk-analysis-repair.ps1 first)")
        continue
    if not os.path.exists(fixture):
        rep_err += 1
        print(f"     {name}: MISSING fixture {fixture}")
        continue

    with open(ev_p, encoding="utf-8-sig") as fh:
        ev = json.load(fh)
    with open(an_p, encoding="utf-8-sig") as fh:
        rep = json.load(fh)
    with open(fixture, encoding="utf-8-sig") as fh:
        src = json.load(fh)

    # (a) EvalResult schema 合规
    errs = list(EVAL_V.iter_errors(ev))
    rep_err += len(errs)
    for e in errs[:3]:
        print(f"     {name} eval schema at {list(e.path)}: {e.message[:110]}")

    # (b) 修复后产物仍须契约合规：按 §6 同一口径逐条校验 risks[]（阶段产物非顶层 RiskAnalysisOutput）
    for r in (rep.get("risks") or []):
        errs = list(RISK_V.iter_errors(r))
        rep_err += len(errs)
        for e in errs[:2]:
            print(f"     {name} repaired risk {r.get('risk_id')} schema at {list(e.path)}: {e.message[:110]}")

    exp = c.get("expect", {})

    # (c) 清单断言
    if ev.get("eval_status") != exp.get("eval_status"):
        rep_err += 1
        print(f"     {name} eval_status expected {exp.get('eval_status')} got {ev.get('eval_status')!r}")
    if ev.get("repair_attempts") != exp.get("repair_attempts"):
        rep_err += 1
        print(f"     {name} repair_attempts expected {exp.get('repair_attempts')} got {ev.get('repair_attempts')!r}")
    if ev.get("max_repair_attempts") != 2:
        rep_err += 1
        print(f"     {name} max_repair_attempts must be 2, got {ev.get('max_repair_attempts')!r}")
    if (ev.get("repair_attempts") or 0) > 2:
        rep_err += 1
        print(f"     {name} repair_attempts exceeds cap 2")

    # (d) repair_log 条数 == repair_attempts
    log = ev.get("repair_log", []) or []
    if len(log) != (ev.get("repair_attempts") or 0):
        rep_err += 1
        print(f"     {name} repair_log len {len(log)} != repair_attempts {ev.get('repair_attempts')}")

    # (e) NEEDS_REVIEW 必须给出说明；PASS 不得残留
    note = ev.get("needs_review_note")
    if exp.get("eval_status") == "PASS":
        if note is not None:
            rep_err += 1
            print(f"     {name} PASS 不应残留 needs_review_note")
    else:
        if not note or "需人工确认" not in note:
            rep_err += 1
            print(f"     {name} NEEDS_REVIEW 的 needs_review_note 缺失或缺少『需人工确认』段")

    # (f) 红线 1：evidence 集合不得被修复改动（禁止发明/删除事实）
    si, ri = _risk_index(src), _risk_index(rep)
    for rid, sr in si.items():
        rr = ri.get(rid)
        if rr is None:
            rep_err += 1
            print(f"     {name} repaired output 丢失 risk {rid}")
            continue
        se = sorted(str(x.get("evidence_id")) for x in (sr.get("evidence") or []))
        re_ = sorted(str(x.get("evidence_id")) for x in (rr.get("evidence") or []))
        if se != re_:
            rep_err += 1
            print(f"     {name} RED-LINE {rid}: evidence 集合被修复改动 {se} -> {re_}")

    # (g) 红线 2：impact_estimate.amount 不得被修复改动（禁止编造量化）
    for rid, sr in si.items():
        rr = ri.get(rid)
        if rr is None:
            continue
        sa = (((sr.get("impact_estimate") or {}).get("amount")), )
        ra = (((rr.get("impact_estimate") or {}).get("amount")), )
        if sa != ra:
            rep_err += 1
            print(f"     {name} RED-LINE {rid}: impact_estimate.amount 被修复改动 {sa} -> {ra}")

    # (h) 不可自动修复类：产物必须原样保留（留痕，禁止清洗）
    if exp.get("output_unchanged"):
        if _canon(src) != _canon(rep):
            rep_err += 1
            print(f"     {name} 不可自动修复的用例不得改动产物")

    # (i) 期望清除的锚点
    absent = exp.get("absent_ref")
    if absent:
        for rr in (rep.get("risks") or []):
            if absent in (rr.get("reasoning_evidence_refs") or []):
                rep_err += 1
                print(f"     {name} 修复后仍残留锚点 {absent} ({rr.get('risk_id')})")

if not rp_cases:
    print("  SKIP no repair cases")

print()
print("REPAIR RESULT:", "ALL GREEN" if rep_err == 0 else f"PROBLEMS repair_err={rep_err}")

# ============================================================================
# ============================================================================
# 10. Dataset（Phase 8 端到端产物）
#     - 清单完整性：每个用例必须有输入文件；dimensions 必须映射到真实 Eval 检查键
#     - 逐用例：risks[] 严格符合 risk.schema.json；EvalResult 符合 eval-result.schema.json
#     - 期望断言：analysis_status / discovery 三态 / risk_exists / priority / eval_status / repair_attempts
#     - Repair 红线：evidence 集合与 impact_estimate.amount 修复前后必须完全一致
# ============================================================================
print()
print("=== 10. dataset (phase 8) ===")

ds_err = 0
DS_CASES = os.path.join(SKILL, "evals", "cases", "dataset")
DS_MANIFEST = os.path.join(SKILL, "evals", "cases", "dataset-manifest.json")
TMP = os.path.join(SKILL, "tmp")

if not os.path.isfile(DS_MANIFEST):
    print("  SKIP no dataset manifest")
    ds_cases = []
else:
    with open(DS_MANIFEST, encoding="utf-8") as fh:
        ds_manifest = json.load(fh)
    ds_cases = ds_manifest.get("cases") or []
    check_keys = set((FILES["eval-result.schema.json"].get("properties", {})
                      .get("checks", {}).get("properties", {}) or {}).keys())
    if not check_keys:
        # 退化：从实际 EvalResult 产物里取键
        check_keys = {"completeness", "evidence_grounding", "reasoning_consistency",
                      "separation", "unknown_integrity", "priority_consistency", "anti_sales"}
    for dim, members in (ds_manifest.get("dimensions") or {}).items():
        for m in members:
            if m not in check_keys:
                ds_err += 1
                print(f"     dimension {dim} 引用了不存在的 Eval 检查键: {m}")
    print(f"  manifest cases={len(ds_cases)}")

    for c in ds_cases:
        cid = c.get("case_id")
        inp = c.get("input") or ((c.get("base_case") or "") + ".input.json")
        if not os.path.isfile(os.path.join(DS_CASES, inp)):
            ds_err += 1
            print(f"     {cid} 输入文件缺失: {inp}")
        if not c.get("expect"):
            ds_err += 1
            print(f"     {cid} 缺少 expect（期望是数据集的意义所在）")

    ap = os.path.join(TMP, "ds_%s_a.json")
    mp = os.path.join(TMP, "ds_%s_am.json")
    dp = os.path.join(TMP, "ds_%s_d.json")
    ep = os.path.join(TMP, "ds_%s_e.json")
    rp_ = os.path.join(TMP, "ds_%s_ar.json")

    def _load(path):
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)

    for c in ds_cases:
        cid = c.get("case_id")
        a_doc = _load(ap % cid)
        e_doc = _load(ep % cid)
        if a_doc is None or e_doc is None:
            print(f"  SKIP {cid} (no artifacts; run run-risk-analysis-dataset.ps1 first)")
            continue

        # --- schema
        for r in (a_doc.get("risks") or []):
            errs = sorted(RISK_V.iter_errors(r), key=lambda e: list(e.path))
            if errs:
                ds_err += 1
                print(f"     {cid} risk {r.get('risk_id')} schema ERRORS={len(errs)}: {errs[0].message[:110]}")
        e_errs = validate("eval-result.schema.json", e_doc)
        if e_errs:
            ds_err += 1
            print(f"     {cid} EvalResult schema ERRORS={len(e_errs)}: {e_errs[0].message[:110]}")

        # --- 期望
        exp = c.get("expect") or {}
        if exp.get("analysis_status") and a_doc.get("analysis_status") != exp["analysis_status"]:
            ds_err += 1
            print(f"     {cid} analysis_status {a_doc.get('analysis_status')} != {exp['analysis_status']}")
        if exp.get("eval_status") and e_doc.get("eval_status") != exp["eval_status"]:
            ds_err += 1
            print(f"     {cid} eval_status {e_doc.get('eval_status')} != {exp['eval_status']}")
        if exp.get("repair_attempts") is not None and e_doc.get("repair_attempts") != exp["repair_attempts"]:
            ds_err += 1
            print(f"     {cid} repair_attempts {e_doc.get('repair_attempts')} != {exp['repair_attempts']}")

        risks = a_doc.get("risks") or []
        if exp.get("risk_count") is not None and len(risks) != exp["risk_count"]:
            ds_err += 1
            print(f"     {cid} risk_count {len(risks)} != {exp['risk_count']}")
        by_cat = {}
        for r in risks:
            by_cat.setdefault(r.get("risk_category"), r)

        d_doc = _load(dp % cid)
        if d_doc and exp.get("discovery"):
            status_by_cat = {x.get("risk_category"): x.get("discovery_status")
                             for x in (d_doc.get("risk_candidates") or [])}
            for cat, want in exp["discovery"].items():
                if status_by_cat.get(cat) != want:
                    ds_err += 1
                    print(f"     {cid} discovery {cat} {status_by_cat.get(cat)} != {want}")
        for cat, want in (exp.get("risk_exists") or {}).items():
            got = (by_cat.get(cat) or {}).get("risk_exists")
            if got != want:
                ds_err += 1
                print(f"     {cid} risk_exists {cat} {got} != {want}")
        for cat, want in (exp.get("priority") or {}).items():
            got = (by_cat.get(cat) or {}).get("priority")
            if got != want:
                ds_err += 1
                print(f"     {cid} priority {cat} {got} != {want}")

        # --- Repair 红线（对有变异/修复产物的用例生效）
        src_doc = _load(mp % cid) or a_doc
        rep_doc = _load(rp_ % cid)
        if rep_doc is not None:
            si = {r.get("risk_id"): r for r in (src_doc.get("risks") or [])}
            ri = {r.get("risk_id"): r for r in (rep_doc.get("risks") or [])}
            for rid, s in si.items():
                r2 = ri.get(rid)
                if r2 is None:
                    continue
                if sorted(str(x.get("evidence_id")) for x in (s.get("evidence") or [])) != \
                   sorted(str(x.get("evidence_id")) for x in (r2.get("evidence") or [])):
                    ds_err += 1
                    print(f"     {cid} RED-LINE {rid}: evidence 集合被修复改动")
                sa = (s.get("impact_estimate") or {}).get("amount")
                ra = (r2.get("impact_estimate") or {}).get("amount")
                if sa != ra:
                    ds_err += 1
                    print(f"     {cid} RED-LINE {rid}: impact_estimate.amount {sa} -> {ra}")

    # --- 数据集运行器汇总产物
    res = _load(os.path.join(TMP, "dataset_result.json"))
    if res is None:
        print("  SKIP no dataset_result.json")
    else:
        if res.get("failed_cases"):
            ds_err += 1
            print(f"     dataset_result.json failed_cases={res.get('failed_cases')}")
        if res.get("total_cases") and res.get("total_cases") != len(ds_cases):
            ds_err += 1
            print(f"     dataset_result.json 用例数 {res.get('total_cases')} 与清单 {len(ds_cases)} 不一致")

if not ds_cases:
    print("  SKIP no dataset cases")

print()
print("DATASET RESULT:", "ALL GREEN" if ds_err == 0 else f"PROBLEMS dataset_err={ds_err}")

# ============================================================================
# ============================================================================
# 11. Anatomy / Review（架构守卫产物 + 独立于 PowerShell 的配置卫生复算）
# ============================================================================
print()
print("=== 11. Anatomy / Review ===")

SKILL_ROOT = r"D:\Workspace\insurance-agent\.trae\skills\risk-analysis"
TMP_DIR = os.path.join(SKILL_ROOT, "tmp")
an_err = 0

# 11.1 守卫与其负向自检的产物必须存在且全绿
for _art in ("anatomy_result.json", "anatomy_test_result.json"):
    _p = os.path.join(TMP_DIR, _art)
    if not os.path.exists(_p):
        print(f"  FAIL missing artifact: {_art}（先跑 check-skill-anatomy.ps1 / test-risk-analysis-anatomy.ps1）")
        an_err += 1
        continue
    with open(_p, encoding="utf-8-sig") as _fh:
        _d = json.load(_fh)
    _f = _d.get("fail", -1)
    print(f"  {'OK  ' if _f == 0 else 'FAIL'} {_art} fail={_f}")
    if _f != 0:
        an_err += 1

# 11.2 规则文件顶层键不得为死键（与守卫 B2 独立复算，防止单侧实现出错）
_META = {
    "rules_version", "taxonomy_version", "method", "description", "note", "shared_sources",
    "anti_sales_version", "repair_version", "repair_method", "principles", "version",
    "scoring_version", "scoring_method", "documentation",
}
_scripts_dir = os.path.join(SKILL_ROOT, "scripts")
_script_text = ""
for _fn in sorted(os.listdir(_scripts_dir)):
    if _fn.endswith((".ps1", ".py")):
        with open(os.path.join(_scripts_dir, _fn), encoding="utf-8-sig", errors="replace") as _fh:
            _script_text += _fh.read()

_dead = []
for _cf in sorted(glob.glob(os.path.join(SKILL_ROOT, "resources", "config", "*.rules.json"))):
    with open(_cf, encoding="utf-8-sig") as _fh:
        _d = json.load(_fh)
    for _k in _d:
        if _k in _META:
            continue
        if _k not in _script_text:
            _dead.append(f"{os.path.basename(_cf)}#{_k}")
print(f"  {'OK  ' if not _dead else 'FAIL'} dead rule keys: {len(_dead)}")
if _dead:
    an_err += len(_dead)
    print(f"       {_dead}")

# 11.3 priority_overrides 必须显式 enabled
with open(os.path.join(SKILL_ROOT, "resources", "config", "risk-scoring.rules.json"), encoding="utf-8-sig") as _fh:
    _sc = json.load(_fh)
_ov_bad = [o.get("id") for o in _sc.get("priority_overrides", []) if "enabled" not in o]
print(f"  {'OK  ' if not _ov_bad else 'FAIL'} priority_overrides explicit enabled: missing={_ov_bad}")
if _ov_bad:
    an_err += len(_ov_bad)

# 11.4 profile_names 必须是单一真源（三个引擎都读它，且不再硬编码 profile 列表）
_engines = ["invoke-risk-analysis-sufficiency.ps1", "invoke-risk-analysis-discovery.ps1",
            "invoke-risk-analysis-analysis.ps1"]
_srcs = {}
for _e in _engines:
    with open(os.path.join(_scripts_dir, _e), encoding="utf-8-sig") as _fh:
        _srcs[_e] = _fh.read()
_pn_bad = [e for e in _engines if "profile_names" not in _srcs[e]]
_hard = [e for e in _engines if "'family_profile', 'financial_profile'" in _srcs[e]]
print(f"  {'OK  ' if not _pn_bad and not _hard else 'FAIL'} profile_names single source: not_read={_pn_bad} still_hardcoded={_hard}")
an_err += len(_pn_bad) + len(_hard)

# 11.5 文档引用不得悬空（未标 ⏳ 即视为假引用）
_dangling = []
_md = [os.path.join(SKILL_ROOT, f) for f in os.listdir(SKILL_ROOT) if f.endswith(".md")]
for _sub in ("references", "resources", "evals"):
    _d2 = os.path.join(SKILL_ROOT, _sub)
    if os.path.isdir(_d2):
        _md += [os.path.join(_d2, f) for f in os.listdir(_d2) if f.endswith(".md")]
import re as _re
for _f in _md:
    with open(_f, encoding="utf-8-sig", errors="replace") as _fh:
        for _i, _line in enumerate(_fh, 1):
            for _m in _re.finditer(r"(?<![\w./-])((?:references|schemas|scripts|resources|evals)/[A-Za-z0-9._/-]+\.(?:md|json|ps1|py))", _line):
                _rel = _m.group(1)
                if ".." in _rel:
                    continue
                if not os.path.exists(os.path.join(SKILL_ROOT, _rel)) and "⏳" not in _line:
                    _dangling.append(f"{os.path.basename(_f)}:{_i}->{_rel}")
print(f"  {'OK  ' if not _dangling else 'FAIL'} dangling doc refs: {len(_dangling)}")
if _dangling:
    an_err += len(_dangling)
    print(f"       {_dangling}")

print("ANATOMY RESULT:", "ALL GREEN" if an_err == 0 else f"PROBLEMS anatomy_err={an_err}")

# 11. Aggregate exit-code（供 dev/CI 判定）
# ============================================================================
# ============================================================================
print()
total_problems = (n_err + neg + stage_err + fx_err + disc_err + dfx_err
                  + ana_err + eval_err + rep_err + ds_err + an_err)
print("=" * 60)
print(f"  meta/instance : {n_err}")
print(f"  negative      : {neg}")
print(f"  sufficiency   : {stage_err} (stage) + {fx_err} (fixture)")
print(f"  discovery     : {disc_err} (stage) + {dfx_err} (fixture)")
print(f"  analysis      : {ana_err}")
print(f"  eval          : {eval_err}")
print(f"  repair        : {rep_err}")
print(f"  dataset       : {ds_err}")
print(f"  anatomy       : {an_err}")
print("=" * 60)
print("FINAL:", "ALL GREEN" if total_problems == 0 else f"PROBLEMS total={total_problems}")
if total_problems:
    sys.exit(1)
