<!-- domain-pack: version=1.0 effective_date=2026-09-14 source_level=B code=general -->

# 保险险种分类（Canonical Taxonomy）

> 本文件是「保险」领域包的**险种分类唯一真相来源**，供所有 Specialist Skill、knowledge-search、evidence provider 引用。
> 它用于消除跨层命名漂移（例如 evidence 层用 `critical_illness`、rag 层用 `critical`）。

## 1. 为什么需要统一分类

保险 Agent 内部多个层各自维护险种名称会导致检索与映射错位：

- evidence-request 查询模板使用 `life / medical / critical_illness / accident / savings / general`；
- rag/store 内部 `product_type` 使用 `medical / critical / accident / life / health / claims`；
- 二者需通过 `alias_to_code` 对齐：`critical_illness → critical`。

本包 `pack.yaml` 的 `product_types` 与 `alias_to_code` 是上述对齐的权威声明。

## 2. 八大分类一览

| code | 展名 | 类型 | 核心关注 |
|---|---|---|---|
| medical | 百万医疗险 | 报销型 | 免赔额、社保目录内外、续保 |
| critical | 重大疾病保险（重疾险） | 给付型 | 等待期、轻中症、保额 |
| accident | 意外险 | 给付+报销 | 伤残分级、意外定义 |
| life | 定期寿险 | 给付型 | 保障期限、家庭责任匹配 |
| health | 核保/健康告知/既往症 | 通用 | 投保前健康评估 |
| claims | 理赔 | 通用 | 时效、材料、争议 |
| savings | 年金险 | 储蓄型 | 现金流、领取方式 |
| general | 通用保险知识 | 通用 | 保障、责任通识 |

## 3. 使用约定

- 任何 Skill 在引用险种时，优先使用 `code`（如 `critical`），而非展名或别名。
- 查询 evidence / knowledge-search 时若使用别名（如 `critical_illness`），应先经 `alias_to_code` 映射到 `code`，再用于 rag 过滤。
- 新增险种子类时，先在 `pack.yaml` 登记 `product_types` + `alias_to_code`，再补 `references/` 语料，最后重跑 `seed_rag.py` 与 `validate_pack.py`。
