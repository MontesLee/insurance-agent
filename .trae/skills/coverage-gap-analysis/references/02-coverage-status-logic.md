# 02 · 覆盖状态判定逻辑（Coverage Status Logic）

`current_coverage.status` 有四种取值，判定优先级如下。

## 1. 主信号：`risk-analysis.coverage_assessment`
上游 `risk-analysis` 已给出每个风险的 `protected_amount` / `unprotected_amount`：

| 条件 | status |
|---|---|
| `protected > 0` 且 `unprotected <= 0` | **SUFFICIENT**（已充分覆盖 → 不产生缺口，跳过） |
| `protected <= 0` 且 `unprotected > 0` | **NONE**（无任何覆盖） |
| `protected > 0` 且 `unprotected > 0` | **PARTIAL**（部分覆盖） |
| 两者均为 0 / 缺失 | 退化为关键词扫描 |

## 2. 退化信号：关键词扫描 `existing_protection` 文本
当金额信号不可用时，扫描风险级 `existing_protection` 自由文本：

1. 命中**否定词**（`无 / 没有 / 未配置 / 未购 / 没买 / 无保险` 等）→ **NONE**。
2. 命中**覆盖词**（`已有 / 已配置 / 已购 / 保单 / 社保 / 百万医疗 / 重疾 / 寿险 / 意外 / 年金 / 医疗险 / 商业保险` 等）→ **PARTIAL**。
3. 两者皆未命中 → **UNKNOWN**（信息不足，不得臆测）。

## 3. `gap_level` 映射
`SUFFICIENT` 不产生缺口。其余按 `gap_level_matrix[priority][status]`：

| priority \ status | NONE | PARTIAL | UNKNOWN |
|---|---|---|---|
| P0 / P1 | CRITICAL | HIGH | UNKNOWN |
| P2 | HIGH | MEDIUM | UNKNOWN |
| P3 | MEDIUM | LOW | UNKNOWN |

- `UNKNOWN` 覆盖状态强制 `gap_level = UNKNOWN`，并记入 `information_gaps`。
- 整体 `status`：存在任何 `UNKNOWN` 缺口 → `NEED_MORE_INFORMATION`；
  否则 `risk-analysis` 为 `FORMAL` → `COMPLETE`，为 `PRELIMINARY` → `PRELIMINARY`。

## 4. 置信度
`confidence = min(overall_confidence, coverage_assessment.confidence)`；`UNKNOWN` 状态再 ×0.5。
