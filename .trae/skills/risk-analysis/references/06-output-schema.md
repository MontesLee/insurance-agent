# 06 · Output Schema（Markdown 渲染契约）

> **状态**：引擎（`invoke-risk-analysis-analysis.ps1`）只产 `RiskAnalysisOutput` JSON，
> JSON 是**唯一事实源**；Markdown 报告是渲染层，**当前未内置渲染脚本**，由调用方按本文档渲染。
> 机器可读结构以 `schemas/risk-analysis-output.schema.json` 为准。

---

## 1. 总则

| 规则 | 说明 |
|---|---|
| 单一事实源 | 报告里每个数字都必须能在 JSON 里找到同名同值字段；不得在渲染时重算或四舍五入成不同量级 |
| 金额格式 | 统一用「万元」，`Format-RaWan` 口径：≥10000 才转万元，保留 1 位小数 |
| 状态可见 | 报告顶部必须显示 `analysis_status` 及其含义（见 §2） |
| 边界可见 | 报告必须含 §9 边界声明，**不得**省略 |
| 禁语 | 渲染层不得添加恐吓 / 夸大 / 产品名话术（同 Anti-Sales 词典） |

---

## 2. 第 1 节 · 概览

展示：`analysis_status`、`overall_confidence`、`sufficiency.sufficiency_status`、`analysis_scope`。

| `analysis_status` | 报告须明示的含义 |
|---|---|
| `FORMAL` | 五域信息充分，结论可直接使用 |
| `PRELIMINARY` | 可出结论，但部分域信息不完整，置信度已下调 |
| `NEED_MORE_INFORMATION` | 存在阻塞字段，**结论不完整**，须先看第 8 节 |
| `CONFLICTING_INFORMATION` | 存在取值冲突，本报告**未择一**，须先澄清 |
| `NEEDS_REVIEW` | Eval 连续修复仍失败，须人工复核 |
| `FAILED` | 引擎异常，报告不可用 |

---

## 3. 第 2 节 · 家庭风险画像

直接渲染 `family_risk_overview`（引擎按 `family_overview_template` 生成，已含：已识别 / 未识别 / 未决 / 最高优先级）。

**不得**在渲染时改写三态判定：`UNDETERMINED` 一律归入"未决"，**不**与"未识别"合并展示。

---

## 4. 第 3 节 · 风险清单

每个 `risks[]` 一条，字段与顺序固定：

```text
### R2-001 重大疾病风险 · P2
- 是否成立：成立（IDENTIFIED）
- 触发事件：……
- 暴露原因：……
- 潜在影响：财务 … / 生活方式 … / 家庭责任 …
- 影响估计：210.0 万元（区间 147.0–273.0，置信度 0.60）
- 现有保障可吸收：X 万元；剩余暴露：Y 万元
- 严重度 HIGH / 可能性 MEDIUM / 剩余风险 HIGH
- 推理：……
- 结论：……
- 证据：E001 家庭年收入约 120 万（client_state.financial_profile.household_income，ESTIMATED）
```

`risk_exists=false` 的风险**也要列出**（证明"已判定不成立"），但须标注"未识别"，且优先级封顶 P3。

---

## 5. 第 4 节 · 风险矩阵

渲染 `risk_matrix[]`：行 = severity（LOW→CRITICAL），列 = likelihood（LOW/MEDIUM/HIGH），格内放 `risk_id(priority)`。

`likelihood = UNKNOWN` 的单独放一行"可能性未知"，不得塞进 HIGH 列。

---

## 6. 第 5 节 · 优先级排序

渲染 `top_priorities[]`（`risk_id` / `priority` / `reason`）。

必须同时说明**优先级是怎么来的**：`priority_matrix[severity][likelihood]` + `priority_overrides`。
`priority_overrides` 中被 `enabled=false` 禁用的条目**不得**在报告里描述为"已生效"。

---

## 7. 第 6 节 · 现有保障与吸收能力

按 risk 渲染 `existing_resources`（每项标明 `status`）与 `coverage_assessment`。
`status ≠ KNOWN` 的资源必须标注状态，避免读者把估计值当确定值。

---

## 8. 第 7 节 · 未知与假设

- `unknowns[]`：字段 + 原因
- `assumptions[]`：字段 + 假设值 + 理由
- 两者**不得**合并展示；假设必须显式标为假设

---

## 9. 第 8 节 · 待补充信息

渲染 `next_information_needed[]`：问题 / 影响的风险域 / 优先级 / EIV。
按 EIV 降序，最多 3 条（追问上限，见 `references/05-questioning.md`）。

---

## 10. 第 9 节 · 边界声明

固定文案（对应 `guardrails`）：

```text
本分析只到风险层，不涉及任何保险产品推荐。
product_recommendation_included = false
sales_language_detected = false
```

另须列出 `missing_from_upstream[]`（上游缺失），说明哪些结论因此降级。
