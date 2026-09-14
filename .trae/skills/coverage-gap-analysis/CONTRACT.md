# CoverageGapAnalysis — Binding Contract（Skill 04）

> 本文件是 `coverage-gap-analysis` 的**绑定契约**。引擎输出必须可机检满足
> `contracts/coverage-gap-analysis.schema.json`，否则视为违反契约。

## 1. 输入 Artifact（只读，不得修改）

| Artifact | 来源 Skill | 本 Skill 使用的关键字段 |
|---|---|---|
| `ClientProfile` | client-intake | `existing_protection`（补充证据，非主信号） |
| `RequirementAnalysis` | requirement-analysis | `requirements[].requirement_type`（关联需求 id） |
| `RiskAssessment` | risk-analysis | `risks[]`（`risk_id/risk_category/existing_protection/coverage_assessment/priority/severity/likelihood/residual_risk/reasoning_evidence_refs`）、`overall_confidence`、`analysis_status` |

输入契约见 `schemas/input.schema.json`（三项均为 object，宽松；上游 Artifact 已由各自 Skill + Adapter 保证结构）。

## 2. 输出 Artifact

`CoverageGapAnalysis`（严格结构，见 `contracts/coverage-gap-analysis.schema.json`）：

```
CoverageGapAnalysis:
  gaps[]:
    gap_id                 # "GAP-<risk_id>"
    domain                 # medical|critical_illness|accident|life|savings|general
    subject
    related_requirement_ids[]
    related_risk_ids[]     # 必须引用上游 risk_id（Risk != Gap）
    current_coverage:
      status               # NONE|PARTIAL|SUFFICIENT|UNKNOWN
      evidence_refs[]
    target_coverage:
      direction            # 覆盖方向（策略级，非产品名）
      rationale
    gap_level              # CRITICAL|HIGH|MEDIUM|LOW|UNKNOWN
    confidence             # 0..1
    evidence_refs[]
  priorities[]             # 排序后的前 N 个缺口
  information_gaps[]       # 覆盖未知 / 需求无对应风险
  status                   # COMPLETE|PRELIMINARY|NEED_MORE_INFORMATION|INSUFFICIENT_INFORMATION|FAILED
```

## 3. 硬性不变量（Eval 强约束）

1. **Risk ≠ Gap**：输出中**不得出现** `severity / likelihood / residual_risk / risk_priority`
   等风险层字段（单测 `_walk_forbidden` 强制）。
2. 每个 `gap` 必须 `related_risk_ids` 非空。
3. `current_coverage.status == SUFFICIENT` 的风险**不得**生成 gap。
4. `confidence ∈ [0,1]`。
5. 出现任一 `gap_level == UNKNOWN` → 整体 `status` 必须为 `NEED_MORE_INFORMATION`。

## 4. 非目标（Non-goals）
- 不产出具体产品 / 保险公司名（属 `product-recommendation`）。
- 不制定解决策略细节（属 `solution`）。
- 不重算或修正风险量化（属 `risk-analysis`）。

## 5. Provenance
每个 gap 的 `related_risk_ids[0]` 作为 `RISK` 溯源；`evidence_refs` 透传上游 `reasoning_evidence_refs`。
可向上回溯：`CoverageGap → Risk → ClientFact / Requirement`。
