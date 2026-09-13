# 生成 Phase 7 Repair 测试 fixture（可复现：每次运行覆盖重写）
#
# 前置依赖（必须先跑过一次 test-risk-analysis-analysis.ps1）：
#   tmp/ana_dual.json   双职工家庭（5 域全 IDENTIFIED）
#   tmp/ana_resp.json   有责任无收入（含 residual=MEDIUM 的 R5-001）
#   tmp/ana_neg.json    中文负向表述（含 NOT_IDENTIFIED 的 R4-001）
# 基线取真实 analysis 产物，保证篡改后的 fixture 除目标字段外完全真实。
import copy, json, os

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(SKILL, "evals", "fixtures", "unit", "repair")
os.makedirs(OUT, exist_ok=True)


def load(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def dump(name, obj):
    p = os.path.join(OUT, name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print("  wrote", name)


def get_risk(d, rid):
    return next(r for r in d["risks"] if r["risk_id"] == rid)


SEV_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
LIK_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "UNKNOWN": 2}


def expected_residual(sev, lik, thr, w):
    s = SEV_RANK[sev] * w["severity"] + LIK_RANK[lik] * w["likelihood"]
    if s >= thr["CRITICAL"]:
        return "CRITICAL"
    if s >= thr["HIGH"]:
        return "HIGH"
    if s >= thr["MEDIUM"]:
        return "MEDIUM"
    return "LOW"


dual = load(os.path.join(SKILL, "tmp", "ana_dual.json"))
resp = load(os.path.join(SKILL, "tmp", "ana_resp.json"))
neg = load(os.path.join(SKILL, "tmp", "ana_neg.json"))

# ---------------------------------------------------------------- 1. 干净基线：应 PASS、零修复
dump("repair-clean.json", copy.deepcopy(dual))

# ---------------------------------------------------------------- 2. residual 错档 → RECOMPUTE_RESIDUAL
d = copy.deepcopy(dual)
get_risk(d, "R2-001")["residual_risk"] = "LOW"      # 应重算回 HIGH
dump("repair-residual.json", d)

# ---------------------------------------------------------------- 3. priority 错配 → RECOMPUTE_PRIORITY
d = copy.deepcopy(resp)
get_risk(d, "R5-001")["priority"] = "P1"            # LOW/HIGH→residual MEDIUM，P1 失配；矩阵应给 P3
dump("repair-priority.json", d)

# ---------------------------------------------------------------- 4. NOT_IDENTIFIED 档位越界 → CLAMP
d = copy.deepcopy(neg)
r = get_risk(d, "R4-001")
assert r["risk_exists"] is False
r["severity"] = "HIGH"
r["residual_risk"] = "CRITICAL"
r["priority"] = "P1"
dump("repair-not-identified.json", d)

# ---------------------------------------------------------------- 5. 悬空证据锚点 → DROP_DANGLING_REFS
d = copy.deepcopy(dual)
r = get_risk(d, "R2-001")
r["reasoning_evidence_refs"] = list(r["reasoning_evidence_refs"]) + ["E999"]
dump("repair-dangling.json", d)

# ---------------------------------------------------------------- 6/7. 注入 scoring 规则（多轮 / 不动点）
base_sc = load(os.path.join(SKILL, "resources", "config", "risk-scoring.rules.json"))

ALT_THR = {"MEDIUM": 1.2, "HIGH": 5.0, "CRITICAL": 6.0}   # 抬高 HIGH/CRITICAL 门槛，使多数风险落到 MEDIUM
sc_alt = copy.deepcopy(base_sc)
sc_alt["residual_thresholds"] = ALT_THR
dump("repair-alt.scoring.json", sc_alt)

w = base_sc["residual_weights"]


def prealign(doc):
    """把 doc 内所有 risk 的 residual 改成 ALT_THR 下的应然值，避免噪声干扰目标用例"""
    for r in doc["risks"]:
        r["residual_risk"] = expected_residual(r["severity"], r["likelihood"], ALT_THR, w)


# 6. 多轮收敛：第 1 轮修 residual，第 2 轮才暴露并修 priority
d = copy.deepcopy(dual)
prealign(d)
r = get_risk(d, "R2-001")
r["residual_risk"] = "CRITICAL"     # 应然 MEDIUM → 第 1 轮修回 MEDIUM
r["priority"] = "P1"                # 与 MEDIUM 失配 → 第 2 轮才被检出并修回 P2
dump("repair-multiround.json", d)

# 7. 不动点：AUTO 动作存在但重算结果与原值相同 → 应提前终止，不消耗 attempt
d = copy.deepcopy(dual)
prealign(d)
r = get_risk(d, "R1-001")
r["severity"] = "HIGH"              # HIGH/HIGH → ALT_THR 下 residual=MEDIUM
r["residual_risk"] = "MEDIUM"
r["priority"] = "P1"                # matrix[HIGH][HIGH]=P1，重算仍是 P1 → 无变化
dump("repair-fixpoint.json", d)

print("DONE")
