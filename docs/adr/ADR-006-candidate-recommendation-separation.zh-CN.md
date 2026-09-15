> 🌐 **Language:** 🇺🇸 [English](ADR-006-candidate-recommendation-separation.md) · 🇨🇳 中文

<a id="adr-006-product-candidate-recommendation-separation"></a>
# ADR-006 · 候选产品 / 推荐分离

<a id="context"></a>
## 背景

在 V2 早期，`recommendation` 直接消费 `candidate_solutions`（由解决方案层生成）。问题在于：**策略中不含任何产品**——没有保费、没有期限、没有投保资格、没有证据。`recommendation` 实际上是在对一批“在任何产品目录中都不可能存在的对象”排序，这是一种自欺。

<a id="decision"></a>
## 决策

插入一个独立层：
`Product Catalog → product-candidate-provider → ProductCandidates → recommendation`。
- **候选提供者（Candidate Provider）只负责生成**：四类确定性检查（type / direction / eligibility / evidence），并打上标签（`admissible` 加原因码）；**不做排序、不选主推**。
- **推荐只负责选择**：消费来自产品目录（Catalog）的真实候选，并对任何未通过产品校验者硬拒绝；三种状态 `COMPLETE / INCOMPLETE_EVIDENCE / NO_CANDIDATES` 被明确区分。

<a id="alternatives"></a>
## 备选方案

- 保留策略级候选：最终被推荐的其实是一个概念，而非一款产品。
- 合并为单一“生成即推荐”阶段：单阶段内自我认证；无法被独立验证。

<a id="why"></a>
## 理由

只有将生成与选择分离，“候选是否合规”与“选择是否合理”才能被独立验证。这也使 `product_hallucination_rate` 成为一个可测试的硬性门禁（目标为 0）：每款被推荐的产品都必须存在于产品目录（Catalog）中。

<a id="trade-offs"></a>
## 取舍

- 多一个阶段、多一份数据集、多一份契约（目前 `product-candidates` 仍是 Skill 级 schema；规范化（canonicalization）是已知的技术债）。
- 投保资格依赖客户事实（例如年龄）；若上游缺失，所有候选都变为 `ELIGIBILITY_UNKNOWN` → 正确地不被推荐，但拉低了“有推荐”的比率。
