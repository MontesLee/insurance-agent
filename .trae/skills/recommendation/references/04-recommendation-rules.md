# 04 — Recommendation Rules

所有可调参数集中在 `resources/config/recommendation.rules.json`。引擎**只读不算**，改规则不改代码即可调整行为。

## 字段说明

| 字段 | 含义 | 默认值/示例 |
|---|---|---|
| `priority_weight` | 需求优先级权重 P0..P3 | P0=4, P1=3, P2=2, P3=1 |
| `risk_priority_weight` | 风险优先级权重 | P0=4 … P3=1 |
| `requirement_type_to_risk_category` | 需求类型 → 风险域映射 | medical→R1, critical_illness→R2, accident→R3, life→R4, savings→R5 |
| `fit_score_thresholds` | 适配等级阈值 | strong≥0.80, good≥0.60, partial≥0.40, poor≥0.20 |
| `requirement_fit_weights` | 覆盖状态值 | matched=1.0, partial=0.5, unmet=0.0 |
| `hard_constraint_types` | 硬约束类型 | budget, term, liquidity |
| `evidence_required_for_primary` | 是否要求 primary 有证据支撑 | true |
| `min_evidence_refs_for_supported` | 判定 supported 最少引用数 | 1 |
| `recommendation_weights` | composite 权重 | requirement_fit=0.4, risk_fit=0.4, evidence=0.2 |
| `residual_risk_major` / `risk_priority_major` | "重大风险"判定 | HIGH/CRITICAL × P0/P1 |

## Human Review Gate 触发条件

满足任一即 `human_review_required = true`：

1. evidence `insufficient` / `conflict`
2. 证据冲突（`knowledge_search_results.conflict`）
3. hard constraint `exception`（需人工确认）
4. 重大风险未被任何候选覆盖（remaining_gaps 非空且无 primary）
5. 推荐基于 assumption（上游 `assumptions` 非空且影响结论）
6. 候选数据不完整（缺 `coverage_structure` / `premium` / `term`）

## 不写进规则的东西

- 具体产品知识（由 Knowledge Search 提供）
- 具体客户事实（由上游 Skill 提供）
- 销售话术模板（不在本 Skill 职责内）

规则只描述**判定逻辑的形状**，不描述事实内容。
