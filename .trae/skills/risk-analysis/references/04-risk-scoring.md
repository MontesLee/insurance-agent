# 04 · Risk Analysis — 风险量化与优先级（Risk Scoring）

> 深层规则文件。`SKILL.md` 只写 workflow，本文件写"风险有多大、多急、什么优先级"。
> 机器可读规则：[`../resources/config/risk-scoring.rules.json`](../resources/config/risk-scoring.rules.json)
> 确定性引擎：[`../scripts/invoke-risk-analysis-analysis.ps1`](../scripts/invoke-risk-analysis-analysis.ps1)
> 上游阶段：[`03-risk-taxonomy.md`](03-risk-taxonomy.md)（发现 → 三态）

```
scoring_version : 1.0
scoring_method  : risk_scoring_v1
```

规则全部外置。引擎只做确定性计算，不依赖 LLM；任何档位阈值都来自 `risk-scoring.rules.json`，
**不允许在脚本里写死 magic number**（见 `CONTRACT.md` §11 已决项）。

---

## 1. 输入与输出边界

**输入**（两路，只读）：

1. `RiskAnalysisInput`（ClientState + requirements）—— 取事实数值
2. Phase 4 的 discovery 阶段产物 —— 取 `risk_candidates`（`IDENTIFIED` / `NOT_IDENTIFIED` / `UNDETERMINED`）

**输出**（stage=analysis 阶段产物）：

- `risks[]` —— 完整 `Risk` 对象（对齐 `schemas/risk.schema.json`）
- `risk_matrix[]` / `top_priorities[]` / `family_risk_overview`
- 前向合并的 `unknowns` / `assumptions` / `next_information_needed`

**对象归属规则**（沿用 Phase 4 决策）：

| discovery_status | 是否进 `risks[]` | 说明 |
|---|---|---|
| `IDENTIFIED` | ✅ | 完整打分 |
| `NOT_IDENTIFIED` | ✅ | 进 `risks[]`，`risk_exists=false`，severity/likelihood/residual 置低档，priority 封顶 P3（消极证据也是证据，供 Eval 4/5 校验） |
| `UNDETERMINED` | ❌ | **不提升为 `Risk` 对象**；其 unknowns / next_information_needed 前向合并到阶段顶层 |

---

## 2. 量化链路（确定性）

```text
primary_income ─┐
responsibility  ├─► gross_impact（按域公式）
coverage_field  ┘
      │
      ▼
protected_amount = 现有相关保障数值（coverage_map 映射）
unprotected_amount = max(gross_impact − protected_amount, 0)
      │
      ▼
severity = band(unprotected_amount)  →  absorption_cap（家庭资产能自保则降档）
      │
      ▼
likelihood = base + indicators（年龄/健康/职业/用工形态条件）
      │
      ▼
residual = severity_rank × w_s + likelihood_rank × w_l   →  band
      │
      ▼
priority = priority_matrix[severity][likelihood]  →  overrides 修正
```

### 2.1 各域 `gross_impact` 公式

| 域 | 公式（参数见 rules） |
|---|---|
| R1 医疗 | `medical_base_cost` +（无商业医疗险 ? `+r1_no_medical_insurance_addon`）+（健康异常 ? `+r1_health_anomaly_addon`） |
| R2 重疾 | `primary_income × income_replacement_years.R2 + rehab_cost_per_event` |
| R3 意外失能 | `primary_income × income_replacement_years.R3 × disability_factor` |
| R4 身故责任 | `房贷余额 + 其他负债 + 子女教育 + 老人赡养 + primary_income × income_replacement_years.R4` |
| R5 长期财务 | `max(退休目标, 教育目标) − 家庭资产`；无明确目标时回退 `家庭年收入 × r5_retirement_income_multiple − 资产` |

`primary_income` 推导：已知 `annual_income` → 用之；否则已知 `household_income` → 减去已知 `spouse_income`（未知则 ×0.6）并记一条 `assumptions`；两者皆未知 → 0 且记 assumption。
**所有推导出的取值都必须写进 `assumptions[]`**，否则 Eval 5 判 `UNKNOWN_AS_KNOWN`。

### 2.2 `severity` 档位

```
LOW      : unprotected_amount <  severity_thresholds.LOW       (30 万)
MEDIUM   : <  severity_thresholds.MEDIUM                       (100 万)
HIGH     : <  severity_thresholds.HIGH                         (300 万)
CRITICAL : >= severity_thresholds.HIGH
```
`absorption_cap`：取 `assets` 为流动性近似（高于真实流动性，偏乐观，安全侧留白）。
若 `unprotected_amount ≤ 0.5 × assets` → 封顶 `MEDIUM`；`≤ 1.0 × assets` → 封顶 `HIGH`。
即"家底厚"会压低严重度，但**不消除**风险本身（priority 仍由 residual 决定）。

### 2.3 `likelihood` 指示条件

每域有 `base` 档，按 `raise` / `lower` 条件列表调整（条件全满足才生效，`likelihood_rank` 取 max/min）。
条件 op 复用发现阶段的字段求值（numeric_*/status_*/string_contains/status_absent）。
例：R2 base=MEDIUM，年龄 ≥50 或健康史异常 → HIGH；年龄 <30 且健康史缺失 → LOW。

### 2.4 `residual` 计算

```
residual_score = severity_rank × residual_weights.severity + likelihood_rank × residual_weights.likelihood
band:  score ≥ 3.0 → CRITICAL ; ≥ 2.0 → HIGH ; ≥ 1.2 → MEDIUM ; else LOW
```
（severity_rank 1–4，likelihood_rank 1–3，故 score ∈ [1.0, 4.0]）

### 2.5 `priority` 矩阵 + override

```
priority = priority_matrix[severity][likelihood]
override（按优先级应用）：
  · R5_always_low      : R5 的 priority 不高于 P3
  · critical_residual_high_likelihood_p0 : residual=CRITICAL 且 likelihood=HIGH → 至少 P0
  · not_identified_p3  : risk_exists=false → 不高于 P3
```

---

## 3. 允许"部分分析"（信息缺失不中止）

- 缺 `assets` → `absorption_cap` 不触发，severity 按 gross 档位；`coverage_assessment.confidence` 下调
- 缺 `annual_income` 但家庭收入已知 → 用推导收入 + 记 assumption，不中止
- 任一数值字段 UNKNOWN → 该域 `impact_estimate.confidence` 下调，并进入 `next_information_needed`
- 缺失一个字段**不得**停止整个 Skill；其他域照常分析

`impact_estimate.confidence` = 所用事实 confidence 的最小值；若任一事实为 ESTIMATED/ASSUMED/INFERRED 则封顶 0.6。
`coverage_assessment.confidence` 同理，且保障字段 UNKNOWN 时下调。

---

## 4. 风险存在 ≠ 现在处理

```jsonc
{ "risk_exists": true, "materiality": "MEDIUM", "residual_risk": "LOW", "priority": "P3" }
```
是合法结果。优先级由 residual × likelihood × 时间敏感性决定，**不由域名决定**：
- "医疗风险"不天然是 P0
- R5 常态 P3（除非 residual CRITICAL 且 likelihood HIGH，仍封顶 P3 by R5_always_low）
- 不得因为"人总会死 / 大家都有风险"就默认高优先级

---

## 5. 与其他阶段的接口

```text
Phase 4 discovery（成不成立） ──► Phase 5 scoring（多大/多急/什么优先级）
        │                                  │
        │  discovery.risk_candidates        ▼
        │                          risks[] + risk_matrix + top_priorities
        │                          + family_risk_overview
        └──── unknowns / next_information_needed / assumptions 前向合并
                      │
                      ▼
              Phase 6 eval（7 项机检）
```

- 阶段产物 `stage=analysis`，**不产出** `eval` 字段（那是 Phase 6 的活）
- `guardrails` 恒 `product_recommendation_included=false` / `sales_language_detected=false`
- 实测反例（用于校准 rules）：双职工 + 房贷 150 万 + 收入 60 万 → R2 gross≈210 万 → HIGH，
  residual 受资产吸收后可能降 MEDIUM；R4 责任缺口受定寿保额吸收后 residual 可能 LOW → priority P2/P3，
  证明"有收入有负债 ≠ 必然 P0"

---

## 6. 产物与校验

- 规则：`resources/config/risk-scoring.rules.json`
- 引擎：`scripts/invoke-risk-analysis-analysis.ps1 -InputJsonPath … -DiscoveryJsonPath … -OutputJsonPath … [-RulesPath …] [-SharedRulesPath …] [-SufficiencyJsonPath …]`
- 单测：`scripts/test-risk-analysis-analysis.ps1`
- 契约：`scripts/verify-contract.py` §6 对 `risks[]` 按 `schemas/risk.schema.json` 子结构校验 + 悬空 evidence ref 检测 + 三态/risk_exists 一致性 + priority 与 severity/likelihood/residual 一致性
