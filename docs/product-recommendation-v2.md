# Phase 5：Product Recommendation V2 —— 根治 `candidate_solutions` 断点

> 对应 Phase 0 审计结论 **P1（致命）**。本文记录断点的性质、根治方式、以及为什么这样切边界。

---

## 1. 断点是什么

Phase 0 实跑 `knowledge-search → recommendation → report-generation` 时发现：

```
requirement
    ↓
risk
    ↓
       ??? candidate_solutions        ← 没有任何 Skill 生产它
                ↓
          recommendation
```

`recommendation` 的 V1 输入契约把 `candidate_solutions` 列为 **required**：

```json
"required": ["requirement_analysis", "risk_analysis", "candidate_solutions"]
```

但整条链上没有任何 Skill 产出它。这不是「字段缺失」，而是**架构上缺一层业务能力**：
候选方案本质上是「应该采用什么解决策略」这个问题的答案产物。

---

## 2. 根治方式：SolutionPlan 成为 Canonical 来源

按用户评审，不新增一个叫 `candidate-solutions` 的 Skill，而是：

```
Risk → CoverageGap → Solution（策略）→ Product Recommendation
```

因为 `candidate_solutions` 不是一个独立业务能力，而是 **Solution Skill 的中间产物**。

Phase 5 把它落到代码上：

```
SolutionPlan.solutions[]
        ↓  solution_to_candidates.py（适配器边界，规则外置）
candidate_solutions[]
        ↓  recommendation_engine（既有评估逻辑，未重写）
ProductRecommendation
```

**关键点：`candidate_solutions` 不再是输入，而是派生产物。**

---

## 3. V2 输入契约：机器强制的 P1 护栏

`schemas/product-recommendation-input.schema.json`：

```json
"required": ["requirement_analysis", "risk_assessment",
             "coverage_gap_analysis", "solution_plan"],
"not": { "required": ["candidate_solutions"] }
```

`not` 子句让「禁止把 candidate_solutions 当独立隐式输入」成为**可机检的契约约束**，
而不是文档里的一句话。负向探针已验证：删掉 `not` 后同一份输入即从「拒绝」变为「通过」，
证明护栏真实生效。

---

## 4. 诚实边界：策略层不生产产品事实

`SolutionPlan` 是**策略**（「建立家庭责任保障」），不是产品。它天然没有
保费、期限、保险公司、产品名。

`solution_to_candidates.py` 因此：

| 字段 | 来源 |
| --- | --- |
| `candidate_id` | `solution_id` |
| `coverage_structure` | 规则映射 `solution_type → requirement_types` |
| `covers_risk_categories` | `related_risk_ids` → 在 RiskAssessment 中查真实 `risk_category` |
| `source_refs` | `solution.evidence_refs`（来自 Phase 4 Evidence 回环） |
| `premium` / `term` / `insurer` / `product_name` | **刻意缺省，绝不推导** |
| `liquidity_impact` | 全部 `unknown`（流动性是产品属性，策略层无从得知） |

风险类别解析优先查 `RiskAssessment` 里的真实 `risk_category`，查不到才退化到
`risk_id` 前缀，再退化到 `solution_type` 默认映射 —— 且默认映射写在规则文件里，可审计。

---

## 5. 顺带修掉的一个真实缺陷：不可验证 ≠ 通过

这是 Phase 5 里最值得单独说的一处修改。

**原实现**：

```python
if budget is not None and hc["value"] is not None and budget > hc["value"]:
    violations.append(...)
else:
    hard_pass.append("budget")      # ← premium 缺失时也走这里
```

当候选没有 `premium` 时，`budget is None` 使条件为假，于是落进 `else`，
被记成 **budget 通过**。`generate_recommendation` 随后据此生成
`reason_codes = ["within_budget"]`。

这在 V1 下无人触发（11 个既有用例全部显式提供 premium/term）。
但 Phase 5 的候选全部来自策略层，**天然没有 premium** —— 若不修，
系统会对一条没有任何报价数据的策略断言「在预算内」。这是**伪造通过**。

**现状**：

```python
if budget is None:
    unverifiable.append({"type": "budget", ...})   # 既不是违规，也不是通过
elif budget > hc["value"]:
    violations.append(...)
else:
    hard_pass.append("budget")
```

三态：**violation / pass / unverifiable**。

配套的两条判断：

1. **不可验证不阻断入选** —— 缺报价不等于方案不合适，不该因此把策略踢掉；
   它转化为 `uncertainties[].constraint_unverifiable` 并强制 `human_review_required=true`。
2. **不可验证不降级为 `INCOMPLETE_EVIDENCE`** —— 证据没问题，问题在缺产品数据。
   把它标成 `INCOMPLETE_EVIDENCE` 会让下游误读成「证据不可信」。
   因此顶层 status 只被 **blocking 类**不确定度（`insufficient_evidence` /
   `evidence_conflict` / `missing_information`，外置于 `blocking_uncertainty_types`）降级。

负向探针双向验证：无 premium → `hard_pass=[]` 且 `unverifiable=['budget']`；
注入 premium=999999 → `violations=['budget']` 且 `rec_status=not_recommended`。
说明护栏既不是橡皮图章，也不是一刀切拦截。

---

## 6. 变更范围

**新增（recommendation skill 内）**

| 文件 | 作用 |
| --- | --- |
| `schemas/product-recommendation-input.schema.json` | V2 输入契约，含 P1 `not` 护栏 |
| `scripts/solution_to_candidates.py` | SolutionPlan → candidates 翻译器 |
| `resources/config/solution-to-candidate.rules.json` | 映射规则外置 |
| `scripts/invoke-product-recommendation.py` | V2 入口（校验→翻译→引擎→契约） |
| `scripts/run_product_recommendation_dataset.py` | V2 数据集 runner |
| `scripts/test_product_recommendation_v2.py` | 10 项架构不变量 |
| `evals/cases/product-recommendation-manifest.json` | 5 例，单一真源 |

**修改（仅 recommendation，Phase 5 授权）**

| 文件 | 改动 |
| --- | --- |
| `scripts/recommendation_engine.py` | 三态约束判定 + `unverifiable_constraints` + status 仅被 blocking 降级 + `strategy_trace` 透传 |
| `resources/config/recommendation.rules.json` | 新增 `known_liquidity_impacts` / `unverifiable_constraint_detail` / `blocking_uncertainty_types` |
| `schemas/recommendation-output.schema.json` | uncertainties type 枚举新增 `constraint_unverifiable` |

**评估逻辑本身未重写**：打分、排序、证据策略仍是原实现，11 个既有用例作为回归基线。

---

## 7. 验证结论

| 套件 | 结果 |
| --- | --- |
| recommendation **LEGACY** 数据集（11 case） | **ALL GREEN** |
| recommendation **V2** 数据集（5 case） | **ALL GREEN** |
| product-recommendation 架构不变量 | **10/10** |
| 契约测试 | **9/9**（product-recommendation 已改为跑真实 V2 管线） |
| 其余 5 个数据集 + 3 个单测套件 | **ALL GREEN** |
| 合计 | **12/12 套件 0 失败** |
| 负向探针 | **3/3 GUARDS LIVE**（规则驱动 / 约束真实响应 / P1 护栏生效） |

`git diff --stat`：仅上述 3 个 `recommendation` 文件被修改（+52 / -8），
其余 Skill 全部 0 改动。

---

## 8. 一个可以推翻的决定

**`liquidity_impact` 一律设为 `unknown`**，而不是按 `solution_type` 猜（比如给
`SAVINGS` 判 `high`）。

理由：流动性占用是具体产品的属性，策略层无从得知；按类型猜等于用一个
「看起来合理」的泛化去承担事实责任。代价是只要编排层传了
`liquidity_required`，就必然产生一条 `constraint_unverifiable` 并触发人工复核 ——
我认为这个代价值得，因为它把「我们其实不知道」明确写进了产物。

如果你希望策略层承担这个泛化判断，改
`resources/config/solution-to-candidate.rules.json` 的
`liquidity_impact_by_solution_type` 即可，无需动引擎。

---

## 9. 运行方式

```bash
# V2 入口
python .trae/skills/recommendation/scripts/invoke-product-recommendation.py \
    --input <v2-composite.json> --output <out.json>

# V2 数据集
python .trae/skills/recommendation/scripts/run_product_recommendation_dataset.py

# V2 架构不变量
python .trae/skills/recommendation/scripts/test_product_recommendation_v2.py

# 既有回归（必须保持全绿）
python .trae/skills/recommendation/scripts/run_recommendation_dataset.py
```
