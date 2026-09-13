# 05 · Questioning（EIV 追问协议）

> 描述**已实现**的追问机制。参数真源：`resources/config/risk-sufficiency.rules.json#eiv`、
> 模板真源：同文件 `question_templates` / `fallback_question_template`。
> 实现：`scripts/invoke-risk-analysis-sufficiency.ps1`（生成）、`...discovery.ps1` / `...analysis.ps1`（去重与继承）。

---

## 1. 立场

缺信息时**不得**靠猜、不得用默认值补、不得为了出结论而假设。正确动作是**问**——
但一次最多问 3 个，且必须说明为什么问。

追问不是"把缺失字段列一遍"，而是按**信息价值**排序后取头部。

---

## 2. EIV（Expected Information Value）

```
raw = tier_weight × blocking_multiplier × spread × status_factor + conflict_bonus
EIV = min(raw / normalizer, 1.0)
```

| 因子 | 取值来源 | 含义 |
|---|---|---|
| `tier_weight` | `tier_weights`：required 1.0 / important 0.6 / optional 0.2 | 字段在依赖图里的层级 |
| `blocking_multiplier` | `eiv.blocking_multiplier` = 2.0（非阻塞 1.0） | 阻塞字段价值翻倍 |
| `spread` | `min(cross_domain_base + step × (受影响域数 − 1), cap)` | 跨域影响越广价值越高 |
| `status_factor` | UNKNOWN 1.0 / ESTIMATED 0.6 / ASSUMED 0.6 / INFERRED 0.5 / **KNOWN 0.0** | 已知字段不再问 |
| `conflict_bonus` | 0.5 | 冲突字段额外加分 |
| `normalizer` | 4.0 | 归一并 cap 1.0 |

实测排序（回归基线）：跨域 2 域 blocking 0.625 > 单域 blocking 0.5 > 非阻塞 important 0.15 > optional 0.05。

**优先级**：`EIV ≥ 0.75 → HIGH`，`≥ 0.45 → MEDIUM`，否则 `LOW`。
排序键：`EIV desc, field asc`（并列时按字段名，保证确定性）。

---

## 3. 输出结构

```jsonc
{
  "question_id": "Q001",
  "question": "配偶的年收入大概是多少？",
  "why_needed": "配偶收入是家庭收入中断时最重要的替代来源……",
  "affects_risks": ["R3", "R4"],
  "priority": "HIGH",
  "expected_information_value": 0.82
}
```

**硬要求**：

- 每轮 **≤ `max_questions_per_round`（3）**
- `why_needed` **必填**——没有理由的追问等于骚扰
- 字段级模板来自 `question_templates.<field>`；无模板时用 `fallback_question_template`（含 `{field}` 占位）
- 追问项**不得**包含 `value_status=UNKNOWN` 的字段（会静默跳过阻塞项，历史坑）

---

## 4. 各阶段职责

| 阶段 | 产出 | 规则 |
|---|---|---|
| Sufficiency（Phase 3） | 主追问清单 `next_information_needed` | 基于依赖图 blocking 字段 |
| Discovery（Phase 4） | 补充追问 | `UNDETERMINED` 候选**不提升为 Risk**，而是进 `unknowns` + `next_information_needed` |
| Analysis（Phase 5） | 合并去重 | 按字段名去重后合并上游清单，不覆盖上游的问题文本 |

**去重口径**：按 `field` 去重，先出现的优先（sufficiency → discovery → analysis 顺序合并）。

---

## 5. 与 analysis_status 的联动

| 充分性结论 | 追问行为 |
|---|---|
| `NEED_MORE_INFORMATION` | 必须产出追问清单，且不出正式量化结论 |
| `CONFLICTING_INFORMATION` | 追问以**澄清**为目的，禁止择一后继续 |
| `PRELIMINARY` | 可出结论，同时列出可提升置信度的字段 |
| `FORMAL` | 通常无追问 |

---

## 6. 机检落点

- 单测：`test-risk-analysis-sufficiency.ps1`（EIV 排序、每轮上限、UNKNOWN 不入 answered_fields）
- 集成：`test-risk-analysis-discovery.ps1` 验证"传入 sufficiency 产物 → 追问去重"
- Eval 2/5：结论用到的字段不得处于"待追问"状态却被当成已知
