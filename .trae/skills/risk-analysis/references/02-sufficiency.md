# 02 · Risk Analysis — 信息充分性（Sufficiency）

> 深层规则文件。`SKILL.md` 只写 workflow，本文件写"怎么判断信息够不够"。
> 机器可读规则：[`../resources/config/risk-sufficiency.rules.json`](../resources/config/risk-sufficiency.rules.json)
> 确定性引擎：[`../scripts/invoke-risk-analysis-sufficiency.ps1`](../scripts/invoke-risk-analysis-sufficiency.ps1)

---

## 1. 为什么不用单一百分比

`requirement-analysis` 用"≥85% FORMAL / 60–84% PRELIMINARY / <60% ask"。
Risk Analysis **复用其精神，但不复制其做法**——因为风险分析是**依赖驱动**的：

| 对比 | 百分比法 | 依赖图法（本 Skill） |
|---|---|---|
| 缺失一个关键字段 | 只扣少量分，可能仍判 FORMAL | **直接置 INSUFFICIENT**，与总分无关 |
| 缺失一个无关字段 | 同样扣分 | 只掉 `confidence`，不影响状态 |
| 字段权重 | 统一 | 按风险域分别定义，同一字段在不同域权重不同 |
| 能否局部分析 | 全局一个结论 | **逐域独立判定**，一个域不足不阻塞其他域 |

**核心原则**：`required` 全部满足是 `SUFFICIENT` 的**必要非充分条件**。
分数再高，只要有一个 required 缺失，该域即 `INSUFFICIENT`。

---

## 2. 三层依赖

| 层 | 权重 | 缺失后果 |
|---|---|---|
| `required` | 1.0 | 域置 `INSUFFICIENT`，字段进 `blocking_fields` |
| `important` | 0.6 | 域降级 `PARTIAL`（**仍产出分析**，置信度下调） |
| `optional` | 0.2 | 无状态影响，仅下调 `confidence`；可进 `next_information_needed` |

### Group（any_of 组）

有些信息"知道任意一个就够"，此时用 group 而不是单字段：

| Group | any_of | 含义 |
|---|---|---|
| `income_anchor` | `annual_income` / `household_income` | 收入基数 |
| `absorb_capacity` | `household_income` / `annual_income` / `assets` | 吸收一次性支出的能力 |
| `responsibility_scale` | `mortgage_balance` / `liabilities` / `children_education` / `elderly_support` / `family_responsibility` | 长期责任规模 |

Group 未满足时，**其全部成员字段**进 `blocking_fields`（因为补任意一个即可解组）。

---

## 3. 依赖链总览

```text
家庭结构 → 责任结构 → 资产 / 收入 / 现金流 → 潜在风险事件
        → 经济后果 → 现有缓冲 → Residual Risk → Priority
```

充分性检查不是查"有没有填表"，而是查**这条链上每一环是否可计算**：

| 环节 | 需要的字段 |
|---|---|
| 家庭结构 | `age` `marital_status` `children_count` `children_info` `dependents` |
| 责任结构 | `mortgage_balance` `liabilities` `children_education` `elderly_support` `family_responsibility` |
| 资产 / 收入 | `annual_income` `household_income` `household_expense` `assets` `cash_flow` |
| 现有保障 | `social_insurance_status` `existing_*_coverage` `employer_benefits` |
| 健康 / 职业 | `customer_health` `health_history` `occupation` `employment_type` `income_stability` |

---

## 4. 各风险域依赖表

### R1 · Medical Risk（医疗支出风险）

| 层 | 字段 / Group |
|---|---|
| required | `social_insurance_status`、`existing_medical_coverage`、**`absorb_capacity`** |
| important | `customer_health`、`household_expense`、`age`、`children_count`、`dependents` |
| optional | `employer_benefits`、`city`、`health_history` |

> 判断医疗风险 = 自付医疗支出 − 医保/商保 − 可动用资金。三者缺一即无法判断，故 `absorb_capacity` 是 required。

### R2 · Critical Illness Risk（重疾收入中断风险）

| 层 | 字段 / Group |
|---|---|
| required | `existing_critical_illness_coverage`、**`income_anchor`** |
| important | `customer_health`、`age`、`income_stability`、`assets`、**`responsibility_scale`** |
| optional | `social_insurance_status`、`household_expense`、`occupation`、`employment_type` |

### R3 · Accident / Disability Risk（意外失能风险）

| 层 | 字段 / Group |
|---|---|
| required | `existing_accident_coverage`、**`income_anchor`** |
| important | `occupation`、`employment_type`、`income_stability`、`existing_medical_coverage`、**`responsibility_scale`** |
| optional | `age`、`gender`、`existing_life_coverage`、`assets`、`city` |

### R4 · Death / Family Responsibility Risk（身故家庭责任风险）

| 层 | 字段 / Group |
|---|---|
| required | `existing_life_coverage`、**`income_anchor`**、**`responsibility_scale`** |
| important | `marital_status`、`children_count`、`children_info`、`spouse_income`、`dependents`、`assets` |
| optional | `spouse_employment`、`household_expense`、`city`、`household_income` |

> ⚠️ **禁止创造事实**：若 `responsibility_scale` 全部成员为 `UNKNOWN`（而非已知为"无责任"），
> 不得默认 `risk_exists = true`，也不得默认 `false` —— 该域置 `INSUFFICIENT`，`risk_exists = UNKNOWN`。

### R5 · Long-term Financial / Savings Risk（长期财务风险）

| 层 | 字段 / Group |
|---|---|
| required | **仅 `income_anchor`** |
| important | `assets`、`household_expense`、`cash_flow`、`premium_budget`、`age`、`children_education` |
| optional | `spouse_income`、`employment_type`、`income_stability`、`city` |

> R5 常态为 **P3**。required 刻意只保留 `income_anchor`，
> 避免"长期财务目标缺失"这类常态性缺失把整条链路拖成 `NEED_MORE_INFORMATION`。

---

## 5. 判定算法

### 5.1 字段是否"已满足"

```
satisfied(field) =
    status ∈ {KNOWN, ESTIMATED, ASSUMED, INFERRED}
    AND value 非 null
    AND value 非空白字符串
```

`UNKNOWN` 恒为未满足 —— **不管它是否出现在 `missing_from_upstream`**。

### 5.2 Group 是否"已满足"

```
satisfied(group) = ∃ f ∈ group.any_of : satisfied(f)
```

### 5.3 域得分

```
score(domain) = Σ( tier_weight(i) × satisfied(i) ) / Σ( tier_weight(i) )
                i ∈ required_fields ∪ required_groups ∪ important_… ∪ optional_…
```

### 5.4 域状态

```
if conflict_fields(域) 非空                      → CONFLICTING
else if 存在未满足的 required 字段或 group        → INSUFFICIENT
else if score ≥ 0.85                            → SUFFICIENT
else                                            → PARTIAL
```

### 5.5 整体状态

| 条件 | `sufficiency_status` |
|---|---|
| 任一域 `CONFLICTING` | `CONFLICTING` |
| 无 CONFLICTING，任一域 `INSUFFICIENT` | `INSUFFICIENT` |
| 全域 `SUFFICIENT` | `SUFFICIENT` |
| 其他 | `PARTIAL` |

`sufficiency_score` = 在范围内的域得分的**算术平均**。

### 5.6 → `analysis_status`

| `sufficiency_status` | `analysis_status` |
|---|---|
| `CONFLICTING` | `CONFLICTING_INFORMATION` |
| `INSUFFICIENT` | `NEED_MORE_INFORMATION` |
| `PARTIAL` | `PRELIMINARY` |
| `SUFFICIENT` | `FORMAL` |

优先级（`precedence`）：`FAILED` > `NEEDS_REVIEW` > `CONFLICTING_INFORMATION` > `NEED_MORE_INFORMATION` > `PRELIMINARY` > `FORMAL`。

---

## 6. 部分分析原则（不得因缺一个字段而停机）

一个域 `INSUFFICIENT` **不得**阻止其他域产出分析。

| 情形 | 处理 |
|---|---|
| 缺 `assets` | R2/R4/R5 仍照常分析，只把 `impact_estimate.confidence` 与 `coverage_assessment.confidence` 下调，并把 `assets` 列入 `next_information_needed` |
| 缺 `responsibility_scale` | 仅 R4 置 `INSUFFICIENT`；R1/R2/R3 不受影响 |
| 缺 `customer_health` | R1/R2 的 `likelihood` 判 `UNKNOWN`，但 `severity` 与 residual 仍可基于收入/责任计算 |

**输出契约要求**：`domain_results` 必须包含 `analysis_scope` 内的**全部**域，
不允许因为某个域不足就把它从结果里删掉。

---

## 7. 冲突处理

`client_state.conflicts[]` 中的字段，若出现在某域依赖表里（任一层），该域：

- `conflict_fields` 记入该字段
- 域状态 `CONFLICTING`
- 整体 `analysis_status = CONFLICTING_INFORMATION`

**禁止自行择一**。例：上游同时出现"家庭年收入 100 万"与"50 万"：

```jsonc
{ "field": "household_income", "candidate_values": ["100万", "50万"], "reason": "两处陈述不一致" }
```

引擎保留 `status=UNKNOWN` + 候选值，并把该字段以 `conflict_bonus` 提权进入追问列表。

---

## 8. Expected Information Value（EIV）追问协议

**不机械罗列所有缺失字段**，只问"对当前风险结论影响最大"的信息。

```
raw = tier_weight × blocking_multiplier × spread × status_factor + conflict_bonus
EIV = min(raw / 4.0, 1.0)
```

| 因子 | 取值 |
|---|---|
| `tier_weight` | required 1.0 / important 0.6 / optional 0.2（跨域取最大） |
| `blocking_multiplier` | 字段在某域 `blocking_fields` 中 → 2.0；否则 1.0 |
| `spread` | `min(1 + 0.25 × (受影响域数 − 1), 2.0)` |
| `status_factor` | `UNKNOWN` 1.0 / `ESTIMATED`·`ASSUMED` 0.6 / `INFERRED` 0.5 / `KNOWN` 0.0 |
| `conflict_bonus` | 字段在 `conflicts[]` → +0.5 |

优先级：`EIV ≥ 0.75` → `HIGH`；`≥ 0.45` → `MEDIUM`；否则 `LOW`。
**每轮最多 3 个问题**（与 `client-intake` 的 `next_questions ≤ 3` 对齐）。

每个问题必须带 `why_needed` 与 `affects_risks`：

```jsonc
{
  "question_id": "Q001",
  "question": "如果家庭主要收入来源中断，目前大概有多少可以随时动用的现金或金融资产？",
  "why_needed": "用于判断家庭能否独立吸收收入中断带来的现金流冲击，决定残余风险高低。",
  "affects_risks": ["R1", "R2", "R4"],
  "priority": "HIGH",
  "expected_information_value": 0.75
}
```

> 这正是需求文档 §18 的例子：判断死亡责任风险时问"可动用金融资产"，
> 而不是问"你有几辆车"——`assets` 是 R1 的 required group 成员（blocking ×2）且跨域影响 3 个域，
> 计算 `1.0 × 2.0 × 1.5 × 1.0 ÷ 4.0 = 0.75`，正好达到 HIGH 阈值。

### 8.1 实测校验（case-missing）

实测中三个 blocking 保障字段的 EIV 均为 **0.625**（跨域 2 个域：
`1.0 × 2.0 × 1.25 × 1.0 ÷ 4.0`），而只影响单个域的 `existing_critical_illness_coverage`
为 **0.5**（`1.0 × 2.0 × 1.0 × 1.0 ÷ 4.0`）更低——
**"影响面越广、越是 blocking，EIV 越高"** 的排序目标成立。

`PARTIAL` 场景下非阻塞的 `important` 字段 EIV 仅 **0.15**（`0.6 × 1.0 × 1.0 × 1.0 ÷ 4.0`），
`optional` 字段仅 **0.05**，自然排在最后，不会挤占每轮 3 个问题的名额。

---

## 9. 上游缺失降级

| 上游 | 处理 |
|---|---|
| `upstream.client_intake.provided = false` | ClientState 全字段 `UNKNOWN` → 所有域 `INSUFFICIENT` → `NEED_MORE_INFORMATION` |
| `upstream.requirement_analysis.provided = false` | `requirements = []`，在 `missing_from_upstream[]` 记 `MISSING_FROM_UPSTREAM: requirement_analysis`；**不阻塞**风险分析（事实层仍完整） |
| 上游字段缺失（单项） | 记 `missing_from_upstream[]`，按依赖图层级降级，**绝不反向修改上游** |

---

## 10. 反例（禁止）

| ❌ 禁止 | ✅ 正确 |
|---|---|
| 用"填了 80% 字段"判 FORMAL | 按域依赖图判；required 缺失即 INSUFFICIENT |
| 因缺 `assets` 停止全部分析 | 其他域照常分析，只下调 confidence |
| `responsibility_scale` 全 UNKNOWN 时默认"有责任" | `risk_exists = UNKNOWN`，域 INSUFFICIENT |
| 冲突时取较大的那个值 | 保留 UNKNOWN + 候选值，整体 CONFLICTING |
| 把所有缺失字段都问一遍 | 按 EIV 排序，每轮 ≤3 |
| 把 `ESTIMATED` 当 `KNOWN` 计满权重 | status 如实透传；EIV 的 `status_factor` 已降权 |

---

## 11. 产物与校验

- 规则：`resources/config/risk-sufficiency.rules.json`（`rules_version` 变更需回归）
- 引擎：`scripts/invoke-risk-analysis-sufficiency.ps1 -InputJsonPath … -OutputJsonPath … [-RulesPath …]`
- 单测：`scripts/test-risk-analysis-sufficiency.ps1`（8 case，含 2 个负向/对抗）
- 契约：`scripts/verify-contract.py` §4 对 `sufficiency` / `next_information_needed` /
  `unknowns` / `assumptions` / `missing_from_upstream` 五段按
  [`schemas/risk-analysis-output.schema.json`](../schemas/risk-analysis-output.schema.json) 的子结构校验

### 阶段产物形态

引擎输出的是**阶段结果**（`stage = "sufficiency"`），不是最终 `RiskAnalysisOutput`——
`risks` / `risk_matrix` / `top_priorities` 属于后续阶段，本阶段不产出、也不允许填占位。
阶段产物的 `analysis_status` 直接驱动 workflow：

| `analysis_status` | 下一步 |
|---|---|
| `FORMAL` / `PRELIMINARY` | 进入 Risk Discovery（Phase 4） |
| `NEED_MORE_INFORMATION` | 先按 `next_information_needed` 追问，再重跑本阶段 |
| `CONFLICTING_INFORMATION` | 先澄清冲突字段，**禁止自行择一后继续** |

### 当前验证状态（Phase 3）

- 单测 8/8 PASS，`tmp/sufficiency_test_result.json` 落盘
- 8 份阶段产物 + 6 份正向 fixture 契约校验 0 错误
- `case-unknown-with-value.json` 为对抗用例，故意违反 FactValue 不变式（`UNKNOWN` 带非空 value），
  用于验证引擎侧防御，故跳过输入 schema 校验
