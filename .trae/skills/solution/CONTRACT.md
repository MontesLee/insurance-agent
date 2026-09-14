# Solution — Contract

## 1. 身份

| 项 | 值 |
| --- | --- |
| Canonical skill id | `solution` |
| Legacy / 物理目录 | `.trae/skills/solution/` |
| 层级 | V2 决策链第 5 层（Gap → Solution → Product） |
| 上游 | `coverage-gap-analysis`（权威）、`requirement_analysis`、`risk_analysis` |
| 下游 | `product-recommendation`、`knowledge-search`（Evidence 回环）、`report-generation` |

## 2. 输入契约

复合输入，每个 Artifact 可为 Canonical 信封（`{"payload": ...}`）或原始 dict：

| 字段 | 必需 | 用途 |
| --- | --- | --- |
| `coverage_gap_analysis` | ✅ | 权威驱动。`gaps[]` 每项需 `gap_id` / `domain` / `current_coverage.status` / `gap_level` |
| `requirement_analysis` | ❌ | 提供约束：客户已声明优先级、需求分析边界、分析状态 |
| `risk_assessment` | ❌ | 仅引用（溯源），不重算 |
| `client_profile` | ❌ | 仅溯源，策略层不使用 |

Schema：`schemas/input.schema.json`（宽松；只约束组合关系，不约束上游内部形态 —— 内部形态由各上游 Skill 自身的 eval 保证）。

## 3. 输出契约

`$ref` → `contracts/solution-plan.schema.json`（单一真源，见 `schemas/output.schema.json`）。

`payload` 结构：

```yaml
solutions:                 # 每个 Gap 一条策略，按 (priority, gap_level) 排序
  - solution_id            # SOL-001...（排序后分配）
    solution_type          # 策略类别，非具体产品
    objective
    coverage_direction
    priority               # P0..P3，由 gap_level 推导
    constraints[]          # {constraint, value, source}
    trade_offs[]           # {axis, option_a, option_b, chosen, reason}
    rejected_directions[]  # {direction, reason}
    related_gap_ids[]
    related_risk_ids[]
    confidence
    evidence_refs[]
objective:                  # == solutions[0].objective
coverage_direction:         # == solutions[0].coverage_direction
priority:                   # == solutions[0].priority
solution_type:              # == solutions[0].solution_type
constraints / trade_offs / rejected_directions:  # == solutions[0] 的同名字段
related_gap_ids:            # 全部被处理 Gap（有序）
information_gaps[]          # 覆盖未知、策略无法定稿的 Gap
status                      # COMPLETE / PRELIMINARY / NEED_MORE_INFORMATION / INSUFFICIENT_INFORMATION
```

## 4. 硬边界（binding）

| # | 约束 | 强制方式 |
| --- | --- | --- |
| B1 | 输出不得含具体保险产品名 / 保险公司名 | 全部文本来自规则模板；单测扫描 `forbidden_terms` |
| B2 | 不得重算 / 复制 `severity` `likelihood` `residual_risk` | 单测「禁止属性存在」断言 |
| B3 | 不得重判覆盖状态（不出现 `gap_level` 键） | 单测禁止键断言 |
| B4 | `coverage_direction` 必须等于规则模板组合 | 单测逐条比对 `prefix + body` |
| B5 | 每条策略必须引用 `gap_id` | 单测断言 |
| B6 | `priority` 由 `gap_level` 推导，不继承 risk priority | 引擎实现 + 数据集断言 |
| B7 | 顶层三元组由 `solutions[0]` 派生 | 单测断言 |
| B8 | 无策略时占位值仍满足 `minLength: 1` | 单测断言 |
| B9 | `solution_type` ∈ 规则 allowlist | 单测断言 |

## 5. 状态推导

```
无策略 且 Gap.status == COMPLETE        -> COMPLETE
任一 Gap 覆盖/等级 UNKNOWN              -> NEED_MORE_INFORMATION
Gap.status == PRELIMINARY               -> PRELIMINARY
Gap.status ∈ {NEED_MORE, INSUFFICIENT}  -> PRELIMINARY
无策略                                   -> INSUFFICIENT_INFORMATION
其余                                     -> COMPLETE
```

**阶段状态只加严，不放宽。**

## 6. Provenance

每条策略产出 `COVERAGE_GAP`（`related_gap_ids`）与 `RISK`（`related_risk_ids`）两类溯源记录，
支持 `ProductRecommendation → Solution → CoverageGap → Risk → ClientFact` 回溯。

## 7. 明确不做

- ❌ 推荐具体产品 / 保险公司（属 `product-recommendation`）
- ❌ 计算具体保额 / 保费（不创造事实；只给确定逻辑）
- ❌ 重算风险等级（属 `risk-analysis`）
- ❌ 重判覆盖状态（属 `coverage-gap-analysis`）
- ❌ 修改上游 Artifact（只读消费）

## 8. 与 `candidate_solutions` 断点的关系

Phase 0 审计 P1：`recommendation` 需要 `candidate_solutions` 但无生产者。
**`SolutionPlan` 就是 candidate solution 的 Canonical 来源。** Phase 5 将
`product-recommendation` 的输入改为消费 `SolutionPlan`，该断点即被根治。
