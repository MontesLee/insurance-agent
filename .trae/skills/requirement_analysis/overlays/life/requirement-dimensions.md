# 寿险需求 维度

## A. 必填事实维度

- `annual_income` 年收入
- `family_responsibility` 家庭责任
- `mortgage_balance` 房贷余额
- `children_info` 子女信息
- `spouse_income` 配偶收入

五项齐备（KNOWN / ESTIMATED / ASSUMED 均可分析，MISSING / UNKNOWN 阻断）才产出寿险结论。

## B. 需求口径与缺口计算

- 公式名：`life_income_x10_mortgage_children20w`
- 口径：年收入 ×10 + 房贷余额 + 子女数 ×20 万
- 已有保障取自 `existing_life_coverage`。

## C. 优先级档位

| 情形 | 档位 |
|------|------|
| 已有保障信息不可分析（缺失/未知） | P1_HIGH（先确认，不高于已确认的全额缺口） |
| 客户明确确认零保障 | **P0_CRITICAL**（已确认、完全未覆盖、可执行缺口） |
| 有保障且 ≥ 需求估算 | P2_MEDIUM |
| 有保障但 < 需求估算 | P1_HIGH |

## D. 本险种特有的边界红线

- 不计算或建议具体寿险保额。
- 不评价家庭责任轻重。
- 不指定或建议受益人，仅记录客户意向。