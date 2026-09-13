---
name: recommendation
description: >
  Evaluate candidate insurance solutions against the client's analyzed requirements and risks,
  compare trade-offs, verify evidence, and produce a structured, evidence-backed recommendation
  with explicit uncertainty. Decision-support only — never a sales script.
argument-hint: <requirement_analysis + risk_analysis + candidate_solutions + knowledge_search_results>
---

# Recommendation

## 何时调用
仅当已具备 `requirement-analysis` 与 `risk-analysis` 结构化输出、且有候选方案需要比较适配性时调用。
**不用于**：采集客户事实、重做需求/风险分析、生成销售话术、代表保险公司做承保决定。

## 输入
见 `schemas/recommendation-input.schema.json`。核心四块：
- `requirement_analysis`（需求、优先级、预算约束）
- `risk_analysis`（重大风险、缺口）
- `candidate_solutions`（候选方案的 coverage / premium / term / 证据引用）
- `knowledge_search_results`（产品/条款事实，用于证据校验）
- 可选 `constraints`（hard：budget / term / liquidity）

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

## References（渐进加载）
- `references/01-recommendation-methodology.md` — 定位/边界/工程原则
- `references/02-matching-framework.md` — 适配等级与 Coverage Matrix
- `references/03-evidence-policy.md` — 证据必须有、禁止模型记忆补全
- `references/04-recommendation-rules.md` — 规则文件字段说明与 Human Review Gate
- 权重与阈值：`resources/config/recommendation.rules.json`（外置，引擎只读）

## Eval
见 `evals/eval-policy.md`；运行 `scripts/run_recommendation_dataset.py`（全量回归）+ `scripts/test-recommendation.py`（单测）。
