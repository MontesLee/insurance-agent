> 🌐 **Language:** 🇺🇸 [English](ADR-006-candidate-recommendation-separation.md) · 🇨🇳 中文

# ADR-006 · Product Candidate / Recommendation separation

## Context
V2 早期，`recommendation` 直接消费 `candidate_solutions`（由 solution 层生成）。
问题：策略里**没有产品**——没有保费、期限、投保资格、证据。`recommendation` 实际在给一批
「不可能存在于任何产品库的对象」排序，等于自欺。

## Decision
插入独立一层：`Product Catalog → product-candidate-provider → ProductCandidates → recommendation`。
- **Candidate Provider 只做生成**：类型 / 方向 / 资格 / 证据四类确定性判定并打标（`admissible` 与原因码），**不排序、不选主推**。
- **Recommendation 只做选择**：消费真实 Catalog 候选，硬拒任何未通过产品校验者；`COMPLETE / INCOMPLETE_EVIDENCE / NO_CANDIDATES` 三态明确区分。

## Alternatives
- 保持策略级候选：推荐的不是产品，是概念。
- 合并为一层「生成并推荐」：同一环节自我认证，无法独立校验。

## Why
生成与选择分离，才能对「候选是否合法」与「选择是否合理」分别校验。
这也让 `product_hallucination_rate` 成为可测的硬门（目标 0）：推荐的产品必须存在于 Catalog。

## Trade-offs
- 多一层 stage、多一份数据集、多一处契约（当前 `product-candidates` 仍是 Skill 级 schema，canonical 化是已知技术债）。
- 资格判定依赖客户事实（如年龄），若上游缺失则候选全部 `ELIGIBILITY_UNKNOWN` → 正确地不推荐，但会降低「有推荐结果」的比率。
