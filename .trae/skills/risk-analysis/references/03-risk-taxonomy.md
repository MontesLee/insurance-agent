# 03 · Risk Analysis — 风险分类与发现（Risk Taxonomy & Discovery）

> 深层规则文件。`SKILL.md` 只写 workflow，本文件写"风险域是什么、怎么判定它成不成立"。
> 机器可读规则：[`../resources/config/risk-discovery.rules.json`](../resources/config/risk-discovery.rules.json)
> 确定性引擎：[`../scripts/invoke-risk-analysis-discovery.ps1`](../scripts/invoke-risk-analysis-discovery.ps1)
> 上游阶段：[`02-sufficiency.md`](02-sufficiency.md)

```
taxonomy_version : 1.0
rules_version    : 1.0
```

**不使用 overlay**。分类是 Skill 内置的一等公民，新增 R6/R7 走 `taxonomy_version` 升级 + 回归检查影响面，
不提前建 overlay 机制（YAGNI）。升级时必须回答三个问题：
新域依赖哪些字段、是否改变既有域的 gate、既有 fixture 的结论是否翻转。

---

## 1. 风险域 ≠ 产品分类

分类表描述的是**家庭会遭遇什么**，不是"该买什么"。

| 风险域 | 触发的是 | 容易误滑向的产品说法 |
|---|---|---|
| R1 医疗 | 自付医疗支出 | ❌ "缺百万医疗险" |
| R2 重疾 | 收入中断 + 康复支出 | ❌ "缺重疾险" |
| R3 意外失能 | 长期收入能力损失 | ❌ "缺意外险" |
| R4 身故家庭责任 | 长期责任无法履行 | ❌ "缺定期寿险" |
| R5 长期财务 | 养老 / 教育 / 长期目标无法达成 | ❌ "缺年金险" |

**写到下游**：本层只输出 `residual_risk` 与 `priority`，
"用什么工具处理"是 `coverage-gap-analysis` 及之后的事。

---

## 2. R1–R5 定义

### R1 · Medical Risk（医疗支出风险）

| 项 | 内容 |
|---|---|
| 触发事件 | 家庭成员发生疾病或意外受伤，产生需要家庭自行承担的医疗支出 |
| 经济后果 | 自付医疗费、社保外用药与器材、陪护与交通的隐性支出 |
| 暴露来源 | **普适暴露**——任何家庭成员都可能发生医疗支出，与是否有收入无关 |
| 判据 | 只要掌握家庭成员基本事实（`person_facts` 组任一字段已知）即认定成立 |
| 放大因素 | 医保状态缺失、无商业医疗险、已知健康异常、有未成年子女或其他被扶养人 |
| 边界 | 康复期**收入损失**归 R2，不归 R1；一次性医疗支出不重复计入 R2 |

### R2 · Critical Illness Risk（重疾收入中断风险）

| 项 | 内容 |
|---|---|
| 触发事件 | 主要收入者确诊重大疾病，治疗与康复期间无法正常工作 |
| 经济后果 | 收入中断（或部分中断）+ 康复 / 护理 / 自费药支出 + 原有刚性责任不减 |
| 暴露来源 | **存在可被中断的收入**（`income_anchor` 组：本人年收入 / 家庭年收入 > 0） |
| 判据 | 收入基数已知且 > 0 → 成立；已知为 0（无收入）→ 不成立；未知 → UNDETERMINED |
| 放大因素 | 家庭责任规模大、收入稳定性差、现有重疾保障为 0、健康异常、可动用资产少 |
| 边界 | 只算**收入损失 + 康复支出**，不重复计算 R1 已计的住院医疗费 |

### R3 · Accident / Disability Risk（意外失能风险）

| 项 | 内容 |
|---|---|
| 触发事件 | 意外或疾病导致伤残 / 失能，长期或永久丧失部分收入能力 |
| 经济后果 | 收入能力永久性下降 + 可能的长期护理支出，责任期限通常**长于**重疾 |
| 暴露来源 | 可被中断的收入 **或** 高风险职业暴露（高空 / 建筑 / 驾驶 / 井下 / 机械等） |
| 判据 | `income_anchor` > 0，或职业命中高风险关键词 → 成立；收入已知为 0 且职业无高风险 → 不成立 |
| 放大因素 | 高风险职业、用工形态不稳定、无意外 / 伤残保障、家庭责任规模大 |
| 边界 | 与 R2 的差别在**持续时间与不可逆程度**；两者可以并存，不是二选一 |

### R4 · Death / Family Responsibility Risk（身故家庭责任风险）

| 项 | 内容 |
|---|---|
| 触发事件 | 家庭主要收入者身故，其承担的长期责任无法继续履行 |
| 经济后果 | 房贷 / 负债、子女抚养与教育、老人赡养等刚性责任失去资金来源 |
| 暴露来源 | **存在需要被履行的长期责任**（房贷、负债、教育、赡养、被扶养人） |
| 判据 | 责任组任一已知存在 → 成立；**全部**责任字段明确为"无 / 0"且无子女无被扶养人 → 不成立；任一未知 → UNDETERMINED |
| 放大因素 | 配偶无独立收入、责任期限长（子女年幼）、可动用资产少、现有人身保障为 0 |
| 边界 | 无责任则无此项风险——**不得因为"人总会死"就默认成立** |

### R5 · Long-term Financial / Savings Risk（长期财务风险）

| 项 | 内容 |
|---|---|
| 触发事件 | 养老、子女教育或其他长期财务目标在既定时间内无法达成 |
| 经济后果 | 退休后生活水平下降、教育计划被迫降级、长期储蓄被风险事件侵蚀 |
| 暴露来源 | 存在收入基数 / 已知年龄（有时间跨度）/ 有明确教育财务目标 |
| 判据 | 任一成立 → 成立；收入、年龄、教育目标全未知 → UNDETERMINED |
| 放大因素 | 结余率低、收入不稳定、资产不足、责任挤占储蓄能力 |
| 边界 | **常态为 P3**。它几乎总是存在，但极少是当下最该处理的——优先级由 Phase 5 打分决定，不由域名决定 |

---

## 3. 三态判定（禁止二值化）

```text
gate.any_of 信号逐条求值 → MATCHED / ABSENT / UNRESOLVED

  ∃ MATCHED        → IDENTIFIED      (risk_exists = true)
  ∄ MATCHED ∧ ∃ UNRESOLVED → UNDETERMINED  (risk_exists = null)
  ∄ MATCHED ∧ ∀ ABSENT     → NOT_IDENTIFIED (risk_exists = false)
```

| 状态 | `risk_exists` | `status` | `evidence` |
|---|---|---|---|
| `IDENTIFIED` | `true` | 按证据最弱环节（KNOWN > ESTIMATED/ASSUMED > INFERRED） | ≥ 1 |
| `NOT_IDENTIFIED` | `false` | 同上 | ≥ 1（**消极证据也是证据**） |
| `UNDETERMINED` | `null` | `UNKNOWN` | 允许 0（无事实可引） |

**为什么不是"有 / 无"二选一**：缺信息时强行二值化，等于在 `true` 和 `false` 之间抛硬币。
`UNDETERMINED` 是合法且常见的中间态，它会把缺失字段推入 `unknowns` 与
`next_information_needed`，而不是推成一个假装确定的结论。

### 信号求值语义

| op | MATCHED | ABSENT | UNRESOLVED |
|---|---|---|---|
| `status_satisfied` | 字段已满足（状态属已满足集且值非空） | 值明确为负向（无 / 0 / 否 / none） | UNKNOWN 或值空 |
| `status_absent` | 值明确为负向 | — | 其他情况 |
| `numeric_gt/gte/lt/lte/eq` | 解析成功且条件成立 | 解析成功但条件不成立且 `absent_when_false=true`；或值为负向 token | 解析不出数字且非负向 token |
| `string_in` | 值归一化后命中词表 | `absent_when_false=true` 且未命中 | 其他 |
| `string_contains` | 值包含词表任一项 | 同上 | 其他 |
| `group_*` | 任一成员 MATCHED | 全部成员 ABSENT | 其他 |

数值解析支持 `60万` / `1,200,000` / `约 50 万` / `3.5w`，单位表外置于规则文件。

---

## 4. 禁止创造事实（最高优先级）

| ❌ 禁止 | ✅ 正确 |
|---|---|
| `responsibility_scale` 全 UNKNOWN 时默认"有责任" | `UNDETERMINED` + 字段进 `unknowns` |
| 客户说"关注收入中断"就认定重疾风险成立 | 需求层关注只写进 `exposure` 备注，**不得**单独构成 gate 命中 |
| 把 `existing_*_coverage = 0` 当作"风险不存在" | 那是**放大因素**（无对冲），不是暴露的否定 |
| `children_count = 0` 就判 R1 不成立 | R1 普适暴露，子女数量只是放大因素 |
| 冲突字段取较大值后继续 | 冲突字段状态锁 `UNKNOWN`，域判 `UNDETERMINED` |
| 用"该风险大家都有"跳过 gate | 每个域必须走 gate，R1 的普适性也仍需一条家庭事实 |

**`UNKNOWN > fabricated certainty`。** 宁可输出 `UNDETERMINED`，不得假装知道。

---

## 5. 冲突处理

`client_state.conflicts[]` 中的字段，在求值时**强制视为 UNRESOLVED**：

- 即使它的 `value` 非空、状态是 `KNOWN`，也不得用于判定暴露
- 该字段进入对应风险对象的 `unknowns`，reason 标注 `CONFLICT_UNRESOLVED`
- 因此相关域自然落到 `UNDETERMINED`（除非有其他独立 gate 信号命中）

例：`household_income` 同时出现 100 万与 50 万 → R2/R3/R5 若仅依赖收入锚点，则全部 `UNDETERMINED`。

---

## 6. 证据与溯源

发现阶段生成的每条 evidence 必须指向 ClientState 的真实事实：

```jsonc
{
  "evidence_id": "E001",
  "fact": "本人年收入：600000",
  "source": {
    "layer": "client_state",
    "field": "financial_profile.annual_income",
    "origin": { "skill": "client-intake", "field": "annual_income" },
    "status": "ESTIMATED"
  }
}
```

| 规则 | 说明 |
|---|---|
| 一字段一证据 | 同一字段被多个信号引用，只生成一条 evidence（按首次出现顺序编号 `E001`…） |
| 状态如实透传 | 事实是 `ESTIMATED`，证据就是 `ESTIMATED`，不得升格为 `KNOWN` |
| 无源不生成 | `UNRESOLVED` 信号**不生成**证据，只进 `unknowns` |
| 需求层引用 | 匹配域的 `REQ-###` 写进 `reasoning_evidence_refs`，但**不构成** gate 命中 |

`status` 取证据状态的最弱环节：`KNOWN > ESTIMATED / ASSUMED > INFERRED`。
`UNDETERMINED` 直接置 `UNKNOWN`。

---

## 7. 与其他阶段的接口

```text
Phase 3 sufficiency（信息够不够）  ──►  Phase 4 discovery（风险成不成立）
        │                                        │
        │ -SufficiencyJsonPath（可选）            ▼
        │   · 继承 analysis_status（按 precedence 取更严重者）   Phase 5 scoring
        │   · 追问去重：已在充分性阶段问过的字段不再重复问         （多大、多急、什么优先级）
        └─────────────────────────────────────────────────────►
```

- 发现阶段**不产出** `severity` / `likelihood` / `residual_risk` / `priority` /
  `impact_estimate` / `coverage_assessment` / `potential_impact`——那是 Phase 5 的活
- 阶段产物里的对象叫 `risk_candidates`，不是最终 `risks`；**不允许填占位值**
- `UNDETERMINED` 的候选对象**不提升为最终 `Risk` 对象**：它没有可引事实，
  强行补齐 `evidence` / `reasoning_evidence_refs` 就是伪造。它的归宿是
  `unknowns[]` + `next_information_needed[]`，等待信息补齐后重跑本阶段
- 充分性判 `INSUFFICIENT` 的域照常发现：信息不足影响的是**置信度**，不是"要不要看这个域"

---

## 8. 追问：只问能改变结论的字段

发现阶段的追问解决的是"**这个风险到底成不成立**"，与充分性阶段的"信息够不够量化"不同。

```
resolution_value = min(weight × spread / normalizer, 1.0)
  weight  = 信号权重（gate 信号恒为 1.0）
  spread  = min(1 + 0.5 × (受影响域数 − 1), 2.0)
```

| 场景 | 计算 | 优先级 |
|---|---|---|
| 只阻塞 1 个域 | `1.0 × 1.0 / 2.0 = 0.50` | MEDIUM |
| 阻塞 2 个域 | `1.0 × 1.5 / 2.0 = 0.75` | HIGH |
| 阻塞 3 个以上域 | `1.0 × 2.0 / 2.0 = 1.00` | HIGH |

每轮 ≤ 3 个；若传入充分性阶段产物，已问过的字段自动去重。
问题文案复用 `risk-sufficiency.rules.json` 的 `question_templates`（单一真源，避免两处漂移）。

---

## 9. 产物与校验

- 规则：`resources/config/risk-discovery.rules.json`
- 引擎：`scripts/invoke-risk-analysis-discovery.ps1 -InputJsonPath … -OutputJsonPath … [-RulesPath …] [-SharedRulesPath …] [-SufficiencyJsonPath …]`
- 单测：`scripts/test-risk-analysis-discovery.ps1`
- 契约：`scripts/verify-contract.py` §5 对 `risk_candidates[]` / `unknowns` / `assumptions` /
  `next_information_needed` / `missing_from_upstream` 按
  [`schemas/risk.schema.json`](../schemas/risk.schema.json) 的定义做子结构校验

### 阶段产物形态

```jsonc
{
  "stage": "discovery",
  "stage_version": "1.0",
  "rules_version": "1.0",
  "taxonomy_version": "1.0",
  "analysis_status": "PRELIMINARY",
  "discovery": {
    "method": "risk_dependency_graph_v1",
    "identified":     ["R1", "R2"],
    "not_identified": ["R4"],
    "undetermined":   ["R3", "R5"]
  },
  "risk_candidates": [ /* … */ ],
  "unknowns": [ /* … */ ],
  "assumptions": [ /* … */ ],
  "next_information_needed": [ /* … */ ],
  "guardrails": { /* 恒为 false */ }
}
```

### 版本升级检查清单（taxonomy_version 变更时）

1. 新增 / 删除风险域是否改变既有域的 gate 信号
2. `analysis_scope` 默认值是否需要同步
3. 全部 discovery fixture 的 `identified / not_identified / undetermined` 是否发生非预期翻转
4. `requirement_type_to_domain` 映射是否需要补条目
5. 下游 `coverage-gap-analysis` 消费的 `residual_risk` 语义是否变化
