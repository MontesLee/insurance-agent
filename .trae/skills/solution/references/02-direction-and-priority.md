# 02 — 保障方向与优先级推导

## 一、优先级：由 gap_level 推导，不继承 risk priority

```
CRITICAL -> P0
HIGH     -> P1
MEDIUM   -> P2
LOW      -> P3
UNKNOWN  -> P3
```

**为什么不用 risk 层的 priority？**

risk priority 回答的是"这个风险本身多严重"，而 solution priority 回答的是
"这个缺口现在多该被处理"。二者相关但不同：一个 severity=CRITICAL 的风险若已被充分覆盖，
根本不会进入 Gap 层；反过来，一个 risk priority=P1 的风险若缺口等级是 CRITICAL，
在策略层就应该被提到 P0。

直接继承 risk priority 会造成**层间语义泄漏** —— 下游读到的 priority 到底是谁的判断就说不清了。
因此策略层的 priority 只从**缺口层自己的结论**（`gap_level`）推导，保持每层判断可归因。

`UNKNOWN → P3` 的含义不是"不重要"，而是"信息不足，暂不能定为高优先"。
同时该缺口会进入 `information_gaps`，整体状态降为 `NEED_MORE_INFORMATION`。

## 二、保障方向：prefix + body 组合

```
coverage_direction = coverage_status_prefix[current_coverage.status]
                   + domain_coverage_direction[domain]
```

示例：

| 覆盖状态 | domain | 结果 |
| --- | --- | --- |
| NONE | life | `当前无覆盖，需以家庭责任（房贷、子女抚养、赡养）与收入替代缺口确定保障额度，保障期限覆盖主要责任期` |
| PARTIAL | critical_illness | `当前部分覆盖，需以收入替代与康复期支出确定保额，覆盖治疗及康复期间的家庭固定开支` |
| UNKNOWN | medical | `当前覆盖情况未知，待明确后以大额医疗支出敞口确定保额，优先覆盖社保目录外费用与免赔额以上部分` |

这样组合的意义：

- **覆盖状态决定动作性质**（从零建立 / 增量补差 / 先补信息）
- **domain 决定 sizing 逻辑**（按什么口径确定额度与期限）

两条维度正交，组合出完整方向，且完全可追溯到上游 Gap 层的判定。

## 三、domain → solution_type 映射

| domain | solution_type | objective |
| --- | --- | --- |
| `life` | `TERM_LIFE` | 建立家庭责任保障 |
| `medical` | `MEDICAL` | 建立大额医疗支出保障 |
| `critical_illness` | `CRITICAL_ILLNESS` | 建立重疾收入补偿保障 |
| `accident` | `ACCIDENT` | 建立意外伤残与意外医疗保障 |
| `savings` | `SAVINGS` | 建立长期确定性现金流储备 |
| `general` | `GENERAL` | 补充对应保障 |

`solution_type` 是**策略类别**，不是产品。用户示例中的"采用定期寿险"即 `TERM_LIFE` 这一类别，
而非某一款具体产品 —— 这正是策略层与产品层的分界。

## 四、约束的来源

约束必须**可溯源**，不能凭空生成。当前三类来源：

| 来源 | 字段 | 示例 |
| --- | --- | --- |
| 覆盖状态 | `current_coverage.status` | PARTIAL → "在现有保障基础上补足差额，避免重复配置" |
| 客户已声明需求 | `requirements[].priority` | "客户已声明的需求优先级：P0_CRITICAL" |
| 上游分析边界 | `requirements[].boundary` | "需求分析边界：requirement_only" |
| 上游分析状态 | `analysis_status` | "需求分析状态：PRELIMINARY" |

注意：约束里出现的是**上游原值**（如 `P0_CRITICAL`、`requirement_only`），
策略层不做同义改写 —— 改写就是隐式引入判断。

## 五、排序

```
sort by (priority_rank asc, gap_level_rank desc)
```

先按策略优先级，同级内按缺口严重程度降序。排序完成后才分配 `solution_id`（`SOL-001`…），
因此 id 稳定反映最终次序，与输入顺序无关。
