# 候选筛选规则（references/01）

> 全部映射与阈值在 `resources/config/candidate-provider.rules.json`。
> 本文只解释**为什么这样判定**，引擎只消费规则、不算规则。

## 1. 险种类型解析

```text
solution_type → product_types
MEDICAL → medical
CRITICAL_ILLNESS → critical_illness
ACCIDENT → accident
TERM_LIFE → life
SAVINGS → savings
GENERAL → 回退到 related_gap_ids 的 domain
```

**空类型列表 = 零候选**，不是"任意产品都可以"。
（早期实现在这里踩过：空列表让过滤条件短路，结果整个 Catalog 12 个产品全成了候选。）

## 2. 保障方向匹配

`SolutionPlan.coverage_direction` 是由规则生成的完整中文句，例如：

```text
life → "以家庭责任（房贷、子女抚养、赡养）与收入替代缺口确定保障额度，保障期限覆盖主要责任期"
```

产品侧声明关键词 `coverage_directions`（如 `["家庭责任","收入替代","房贷","责任期","身故"]`），
命中任一即 `MATCH`，全不命中为 `MISMATCH`。

方向为空或产品未声明方向 → `UNKNOWN`（不是 MATCH）。

> 类型为主判别，方向为二次确认。这样 P007（家庭责任）与 P008（储蓄/传承）
> 同为 `life` 类型，但只有 P007 能匹配寿险策略 —— 这正是"医疗缺口不能推储蓄险"的
> 同类型版本保障。

## 3. 投保资格

只校验 Catalog 显式声明且规则允许强制执行的规则（`age`、`occupation_class`）。

| 客户信息 | 结果 |
|---|---|
| 年龄在区间内 | `ELIGIBLE` |
| 年龄超出区间 | `INELIGIBLE`（硬拒） |
| 年龄未知 | `UNKNOWN`（第三态，绝不静默通过） |
| 职业未知 | 按 `unknown_occupation_skips_check` 跳过（不阻断） |

## 4. 证据可用性

产品声明 `required_evidence_domains` 与 `evidence_refs`。
命中条件是：证据的领域 ∈ 所需领域，**或**证据文档名 ∈ 声明的 `evidence_refs`。

```text
证据领域由文档名前缀判定，映射同样外置：
01 → medical    02 → critical_illness    03 → accident
04 → life       05/06/00 → general
```

检索到语料但不相关时，该产品的证据依然是 `MISSING` ——
"有检索结果"不等于"这个产品有依据"。

## 5. 为什么被拒的候选仍然输出

`MISMATCH` / `INELIGIBLE` 的候选会以 `admissible=false` + `reject_reason_codes` 输出，
而不是被静默丢弃。理由：

- 可审计：能回答"为什么没推荐 P008"
- 可追溯：`not_recommended` 里能看到具体拒绝原因
- 规格要求：§二十 明确要求这些产品"不得作为主推荐"——隐含前提是它们**出现过**并被拒绝

## 6. 不做的事

- 不按分数排序
- 不决定主推荐与备选
- 不生成客户可读的解释文案
