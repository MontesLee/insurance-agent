# Core Analysis E2E（Step 1）

验证核心业务决策链的 **数据链正确性**（Step 1 规格 §11 / §13 / §14）。

```text
ClientState/ClientProfile + RequirementAnalysis + RiskAssessment
   → coverage-gap-analysis（真实引擎）
   → solution（真实引擎）
```

> 本阶段**不实现 Orchestrator**（规格 §13）。上游 `RequirementAnalysis` / `RiskAssessment`
> 以 fixture 形式提供（由各自 Skill 的 eval 保障其真实性），Coverage Gap 与 Solution 两阶段调用真实引擎。

## 用例

| case | 场景 | 关键断言 |
|---|---|---|
| `case-001-complete` | 完整客户（30岁男性/已婚/0岁孩子/年收入50万/200万房贷/已有部分保险） | 全链成功；gap/solution 均 `COMPLETE`；无 UNKNOWN 缺口 |
| `case-002-insufficient` | 缺 `existing protection` | 必须为 UNKNOWN 缺口 + `NEED_MORE_INFORMATION`；**禁止猜测已有保障** |
| `case-003-conflicting` | 年收入冲突（50万 vs 80万） | 保留 `CONFLICTING_INFORMATION`；输出**不得**自行选定 500000 / 800000 |

## 每例通用断言（对应规格 §12 / §14）

- 各阶段输出通过 Canonical Contract 校验
- **可追溯性**：`solution.related_gap_ids → gap.gap_id`，`gap.related_risk_ids → risk.risk_id`，
  `gap.related_requirement_ids → requirement.requirement_id`，并回溯到 ClientState
  （均要求**非空且属于已知集合**，避免空列表导致假通过）
- 缺口层**不含任何金额类字段**（§6 禁止编造金额）
- solution 层**不含产品名 / 保险公司名**（§12-5/6）
- UNKNOWN 语义保持（§12-4）

## 运行

```bash
python test-cases/e2e/core-analysis/run_core_analysis_e2e.py
```

用例清单单一真源：`manifest.json`。当前 **41/41 ALL GREEN**。
