---
name: recommendation
description: >
  Evaluate candidate insurance solutions against the client's analyzed requirements and risks,
  compare trade-offs, verify evidence, and produce a structured, evidence-backed recommendation
  with explicit uncertainty. Decision-support only — never a sales script.
argument-hint: <requirement_analysis + risk_assessment + coverage_gap_analysis + solution_plan + knowledge_evidence>
---

# Recommendation（Canonical: product-recommendation）

## 何时调用
仅当已具备 `requirement-analysis` 与 `risk-analysis` 结构化输出、且有候选方案需要比较适配性时调用。
**不用于**：采集客户事实、重做需求/风险分析、生成销售话术、代表保险公司做承保决定。

## 输入

### V2（默认，Phase 5 起）

见 `schemas/product-recommendation-input.schema.json`。核心五块：

- `requirement_analysis`（需求、优先级、预算约束）
- `risk_assessment`（重大风险、残余风险）
- `coverage_gap_analysis`（保障缺口）
- `solution_plan`（解决策略 —— **候选方案的 Canonical 来源**）
- `knowledge_evidence`（产品/条款证据，经 Phase 4 Evidence Provider 获取）
- 可选 `constraints`（hard：budget / term / liquidity）

**`candidate_solutions` 不再是输入**，且被契约用 `not: {required: [...]}` 明确禁止 ——
它历史上是整条链上没有任何 Skill 生产的幽灵字段（Phase 0 审计 P1）。
候选由 `scripts/solution_to_candidates.py` 从 `solution_plan.solutions[]` 派生，
映射规则外置于 `resources/config/solution-to-candidate.rules.json`。

入口：`scripts/invoke-product-recommendation.py`。

### V1（legacy，仅用于既有 11 case 回归）

见 `schemas/recommendation-input.schema.json`，仍接受显式 `candidate_solutions`。
保留它是为了让既有 eval 继续充当回归基线；新调用方一律走 V2。

## 输出
见 `schemas/recommendation-output.schema.json`：
- `status`：`COMPLETE` / `INSUFFICIENT_INPUT` / `NO_CANDIDATES` / `INCOMPLETE_EVIDENCE`
- `candidate_evaluations[]`：每个候选的 `requirement_fit` / `risk_fit` / `constraint_fit` / `evidence`
- `primary_recommendation` / `alternatives[]` / `not_recommended[]`
- `tradeoffs[]` / `uncertainties[]` / `evidence_refs[]` / `human_review_required`

## 核心工作流
`Validate → DecisionContext → CoverageMatrix → RequirementFit → RiskFit → ConstraintFit → Evidence → Trade-off → Recommendation → SanityCheck → Output`。
引擎在 `scripts/recommendation_engine.py`，所有权重/阈值外置于 `resources/config/recommendation.rules.json`。

## 失败 / 边界处理
- 关键输入缺失 → `status=INSUFFICIENT_INPUT`，列明缺失项，**不自行补全**
- 无候选方案 → `status=NO_CANDIDATES`
- 候选声称的 coverage 无知识库证据 → `evidence=insufficient`，不进 primary
- hard constraint 违反 → 不进 primary（除非 `exception` + `human_review_required`）
- 任何不确定 → 显式 `uncertainties[]` + `human_review_required=true`

## 策略层候选的诚实边界（Phase 5）

`SolutionPlan` 是策略，不是产品，天然没有保费 / 期限 / 保险公司 / 产品名。
翻译器对这些字段**一律缺省，绝不推导**。

因此硬约束判定是**三态**的：

| 状态 | 含义 |
| --- | --- |
| `violations` | 确实违反 |
| `hard_constraints`（pass） | 确实满足 |
| `unverifiable_constraints` | 数据缺失，无法验证 —— **既不是通过也不是违规** |

不可验证会写入 `uncertainties[].constraint_unverifiable` 并强制 `human_review_required=true`，
但**不阻断入选**，也不把顶层 status 降级为 `INCOMPLETE_EVIDENCE`（证据没问题，缺的是产品数据）。

## References（渐进加载）
- `references/01-recommendation-methodology.md` — 定位/边界/工程原则
- `references/02-matching-framework.md` — 适配等级与 Coverage Matrix
- `references/03-evidence-policy.md` — 证据必须有、禁止模型记忆补全
- `references/04-recommendation-rules.md` — 规则文件字段说明与 Human Review Gate
- 权重与阈值：`resources/config/recommendation.rules.json`（外置，引擎只读）
- 策略→候选映射：`resources/config/solution-to-candidate.rules.json`（外置）

## Eval
见 `evals/eval-policy.md`。

```bash
# V2（默认）
python scripts/run_product_recommendation_dataset.py       # 5 case
python scripts/test_product_recommendation_v2.py           # 10 项架构不变量
python scripts/invoke-product-recommendation.py --input <v2.json>

# V1 回归基线（必须保持 11/11）
python scripts/run_recommendation_dataset.py
python scripts/test-recommendation.py
```
