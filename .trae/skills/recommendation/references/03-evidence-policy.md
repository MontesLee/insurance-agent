# 03 — Evidence Policy

> 核心红线：**禁止用模型记忆补充关键产品事实**。检索负责找证据，Recommendation 负责基于证据做判断。

## 什么信息必须有证据

| 信息 | 证据来源 | 无证据时行为 |
|---|---|---|
| 产品是否含某项责任 | `knowledge_search_results` 中 `source_refs`/`evidence_refs` 命中的 chunk | 标记 `insufficient_evidence` |
| 条款 / 除外责任 | Knowledge Search 返回的 `content` | 列出 `missing_evidence` |
| 保费 / 期限 / 适用人群 | 候选方案自带 `premium/term` 字段 + Knowledge Search 佐证 | 字段缺失 → `uncertainties` |
| 客户优先级 / 风险 | 直接来自 `requirement_analysis` / `risk_analysis`（它们本身就是证据链产物） | 上游状态异常 → 上抛 uncertainty |

## 什么信息可以来自前置 Skill

- 客户需求、优先级、预算约束：来自 `requirement_analysis`（已由上游做事实/推理/假设/未知分离）
- 风险等级、缺口、重大风险：来自 `risk_analysis`（`reasoning_evidence_refs` 已锚定 E###/REQ-###）

## 什么信息必须 Knowledge Search

- 任何"产品事实"类断言（某医疗险是否含 CAR-T、某重疾险是否含多次赔付、等待期几天…）
- 候选方案的 `source_refs` / `evidence_refs` 必须能在 `knowledge_search_results.results[].chunk_id` 中找到，否则视为无支撑

## 何时必须标记 insufficient_evidence

- 候选 `coverage_structure` 非空，但其 `source_refs` 在知识库中**无一命中** → `evidence.status = insufficient`，`missing_evidence` 列出声称覆盖的维度
- `knowledge_search_results.status == insufficient_evidence` → 所有候选证据状态降级为 `insufficient`
- `knowledge_search_results.conflict == true` → 相关候选 `evidence.status = conflict`

此时该候选 `recommendation_status = insufficient_evidence`，**不得**进入 primary，并在 `uncertainties` 中记录。

## 验证（确定性）

`scripts/validate_output.py` 强制：
- `evidence.status ∈ {insufficient, conflict}` 的候选必须有对应 `uncertainties` 条目或 `missing_evidence`
- `status=COMPLETE` 且有 primary 时 `evidence_refs` 非空
- 不得有 hard-constraint 违反或 evidence 不足的候选成为 primary（除非 exception + human_review）
