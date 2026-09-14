# Solution — Eval Policy

## 原则

1. **可机检才判 PASS。** `MANUAL` / `NOT_EXECUTED` 不计通过。
2. **清单单一真源**：`evals/cases/manifest.json`。运行器与契约校验脚本都读它，
   不在代码里另写一份用例列表。
3. **负例用单点变异 + 反向断言**：除目标检查 FAIL 外，其余检查必须仍 PASS。
4. **阶段状态只加严不放宽**：上游 `PRELIMINARY` 时，本层不得输出 `COMPLETE`。

## 用例集（5 例）

| case | 场景 | 验证点 |
| --- | --- | --- |
| `case-01-multi-gap` | 多缺口完整场景 | 每 Gap 一条策略；按 gap_level 降序；Primary 取最高优先级 |
| `case-02-life-only` | 单一寿险缺口 | `TERM_LIFE`；拒绝"终身寿险"；含"保障期限"取舍 |
| `case-03-unknown` | 覆盖未知 | 未知缺口降 P3；整体 `NEED_MORE_INFORMATION`；登记 `information_gaps` |
| `case-04-no-actionable-gap` | 无可执行缺口 | 不产出策略；占位值仍满足 `minLength: 1`；不伪造 objective |
| `case-05-preliminary` | 上游 PRELIMINARY | 产出策略但整体 `PRELIMINARY`，不加严为 COMPLETE |

## 检查维度

### 契约校验（每条用例都跑）

输出经 `adapters.base.make_envelope` 包成信封后，用
`contracts/solution-plan.schema.json` 做 `Draft7Validator` 校验。任一 error 即 FAIL。

### 业务断言

`expected_status` / `min_solutions` / `max_solutions` / `expect_solution_types`（**有序全等**）/
`expect_priorities`（有序全等）/ `primary_solution_type` / `require_information_gaps` /
`deny_information_gaps` / `expect_rejected_direction_contains` / `expect_trade_off_axis`。

### 架构不变量（`scripts/test_solution.py`，反向断言）

| # | 不变量 |
| --- | --- |
| 1 | 输出任意字符串不含 `forbidden_terms` 中的品牌词 |
| 2 | 不含 `severity` / `likelihood` / `residual_risk` / `risk_priority` / `gap_level` 键 |
| 3 | `solution_type` ∈ 规则 allowlist |
| 4 | 每条策略都有 `related_gap_ids` |
| 5 | `coverage_direction == prefix[覆盖状态] + body[domain]`（未发明文本） |
| 6 | `priority ∈ {P0,P1,P2,P3}` |
| 7 | `confidence ∈ [0,1]` |
| 8 | 顶层三元组 == `solutions[0]` 同名字段（单一真源） |
| 9 | 无策略时 `objective` / `coverage_direction` / `priority` 仍非空 |

## 运行

```bash
python scripts/run_solution_dataset.py   # 5 例契约 + 业务断言
python scripts/test_solution.py          # 架构不变量
```

两者均为 ALL GREEN 才算通过；退出码非 0 表示存在失败。

## 反橡皮图章

判定映射外置在 `resources/config/solution-mapping.rules.json`，引擎提供 `-RulesPath`。
负向测试可注入篡改后的规则副本，确认输出随之变化 —— 证明测试确实在驱动引擎，
而非引擎输出被写死。**探针跑完必须重跑基线**，避免 tmp 产物污染后续校验。
