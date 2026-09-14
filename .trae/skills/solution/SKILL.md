---
name: solution
description: 将已判定的保障缺口（CoverageGapAnalysis）转化为解决策略（SolutionPlan）。只回答"应该采用什么解决策略"，不推荐具体产品、不重算风险、不重新判定缺口。当需要把 Gap 转成可执行的保障方向与取舍时使用。
---

# Solution（解决策略层）

## 定位

V2 决策链第 5 层：

```
CoverageGap  →  Solution（本 Skill）  →  ProductRecommendation
   "现在缺什么"      "应该采用什么解决策略"      "哪些产品可实现该策略"
```

**本 Skill 只回答一个问题：针对已判定的缺口，应采用什么解决策略？**

## 输入 / 输出

| 项 | 内容 |
| --- | --- |
| 输入 | `coverage_gap_analysis`（**权威驱动**）、`requirement_analysis`（约束）、`risk_assessment`（仅引用） |
| 输出 | `SolutionPlan` —— 契约见 `contracts/solution-plan.schema.json` |
| 形态 | 每个 Gap 产出一条策略，写入 `payload.solutions[]` |

## 硬边界（违反即架构错误）

1. **Solution ≠ Product**：禁止出现具体保险产品名称、保险公司名称。所有输出文本均由
   `resources/config/solution-mapping.rules.json` 模板生成 —— 结构上不可能产生自由文本产品名。
2. **Solution ≠ Risk**：不重算、不复制 `severity` / `likelihood` / `residual_risk`。只通过
   `related_risk_ids` 引用风险。
3. **Solution ≠ Coverage Gap**：不重新判定覆盖状态，直接消费 Gap 层的判定结论。
   `priority` 由 **gap_level** 推导（缺口层判断），不继承 risk 层 priority。
4. **禁止创造数量**：`coverage_direction` 只说明"如何确定额度与期限"的逻辑，不编造具体金额。
5. **全覆盖**：每个 Gap 必须有对应策略；SUFFICIENT 的缺口不会进入 Gap 层，因此也不会出现在此。

## 输出语义

| 字段 | 含义 |
| --- | --- |
| `solution_type` | 策略类别（如 `TERM_LIFE`），**不是**具体产品 |
| `objective` | 解决目标 |
| `coverage_direction` | 保障方向 / 额度与期限逻辑 |
| `priority` | 由 `gap_level` 推导：CRITICAL→P0, HIGH→P1, MEDIUM→P2, LOW/UNKNOWN→P3 |
| `constraints` | 约束（增量补差 / 客户已声明优先级 / 上游分析边界） |
| `trade_offs` | 取舍（含 `chosen` 与 `reason`） |
| `rejected_directions` | 不采用的方向及理由 |

顶层 `objective` / `coverage_direction` / `priority` / `solution_type` **由 `solutions[0]` 派生**
（单一真源，避免双写漂移）。无可执行缺口时使用规则占位值，不伪造 objective。

## 运行

```bash
python scripts/invoke-solution.py --input input.json        # 单条
python scripts/run_solution_dataset.py                      # 数据集（5 例）
python scripts/test_solution.py                             # 架构不变量单测
```

规则外置：判定映射全部在 `resources/config/solution-mapping.rules.json`，引擎留 `-RulesPath`
供负向注入。改判定不碰引擎。

## 状态

`COMPLETE` / `PRELIMINARY` / `NEED_MORE_INFORMATION` / `INSUFFICIENT_INFORMATION`。
任一缺口覆盖未知 → `NEED_MORE_INFORMATION`；上游 `PRELIMINARY` → 只能 `PRELIMINARY`
（阶段状态只加严，不放宽）。

## References（按需加载）

- `references/01-strategy-methodology.md` —— 策略层方法论与边界
- `references/02-direction-and-priority.md` —— 保障方向与优先级推导
- `references/03-tradeoffs-and-rejections.md` —— 取舍与被否方向的设计依据

## Evals

`evals/eval-policy.md`；用例清单单一真源 `evals/cases/manifest.json`（5 例）。
可机检才判 PASS；`MANUAL` / `NOT_EXECUTED` 不计通过。
