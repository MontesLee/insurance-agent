# 02 — Matching Framework

Recommendation 的核心机制是 **Coverage Matrix**（需求 × 候选），而不是一个黑盒总分。

## 适配等级（fit labels）

每个候选方案在 *需求适配* 与 *风险适配* 两个维度上各给出一个等级：

| 等级 | 含义 | 触发（score = 加权命中率） |
|---|---|---|
| `strong_fit` | 强适配 | score ≥ 0.80 |
| `good_fit` | 较好适配 | score ≥ 0.60 |
| `partial_fit` | 部分适配 | score ≥ 0.40 |
| `poor_fit` | 弱适配 | score ≥ 0.20 |
| `not_suitable` | 不合适 | score < 0.20 |
| `insufficient_evidence` | 证据不足，无法判定 | 候选声称的 coverage 无知识库证据支撑 |

阈值定义在 `resources/config/recommendation.rules.json → fit_score_thresholds`。

## 需求适配（requirement_fit）

- 对每个 `requirement`（带优先级权重 P0..P3）判断其在候选中的覆盖状态：
  - `matched`：候选 `coverage_structure` 含该 `requirement_type`
  - `partial`：候选 `coverage_partial` 含该类型
  - `unmet`：均未含
- 加权命中率 = Σ(权重 × 状态值) / Σ权重，状态值 `matched=1.0 / partial=0.5 / unmet=0.0`
- 输出 `overall` 等级 + `matched/partial/unmet` 需求 ID 列表

## 风险适配（risk_fit）

- 仅看"重大风险"：`residual_risk ∈ {HIGH, CRITICAL}` 且 `priority ∈ {P0, P1}`
- `requirement_type → risk_category` 映射：`medical→R1, critical_illness→R2, accident→R3, life→R4, savings→R5`（见 rules）
- 候选 `covers_risk_categories` 覆盖到的重大风险 → `covered_risks`，未覆盖 → `remaining_gaps`
- 风险适配 score = 覆盖数 / 重大风险总数（无重大风险时视为 1.0）

## 约束适配（constraint_fit）

- **hard constraint**（`budget / term / liquidity`）：违反即进入 `violations`，该候选原则上不能成为 primary
- **soft constraint / preference**：记录但不强制拦截
- 违反 hard constraint 的候选 → `recommendation_status = not_recommended`（除非显式 `exception` + `human_review_required`）

## 推荐分层

- `primary_recommendation`：eligible 中 composite 最高者
- `alternatives`：其余 eligible（最多 2 个）
- `not_recommended`：hard 违反 / 证据不足 / 适配过差者，附原因

composite = `0.4·requirement_fit + 0.4·risk_fit + 0.2·evidence_ok`，权重见 rules。
