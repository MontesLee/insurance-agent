# Reference 01 — Report Schema（输入 / 输出契约）

本文件描述 `report-generation` 的输入与输出 JSON 结构。引擎与校验器均依据此契约工作。

## 一、输入契约（`schemas/report-input.schema.json`）

| 字段 | 必填 | 说明 |
|------|------|------|
| `client_profile` | 是 | CanonicalClientState（`risk-analysis/schemas/client-state.schema.json`）：`family_profile` / `employment_profile` / `health_profile` / `responsibility_profile` / `existing_protection` / `financial_profile`，每字段为 `factValue{value,status,source,confidence}` |
| `requirement_analysis` | 是 | RequirementAnalysisOutput：`analysis_status` / `requirements[]{requirement_id,requirement_type,summary,priority}` / `coverage_gaps[]` / `information_gaps[]{field,importance,reason}` / `guardrails` |
| `risk_analysis` | 是 | RiskAnalysisOutput：`risks[]{risk_id,risk_category,risk_name,residual_risk,priority,severity,likelihood,trigger,exposure,potential_impact,coverage_assessment,existing_protection,conclusion,reasoning_evidence_refs}` / `next_information_needed[]` / `unknowns[]` |
| `knowledge_search` | 否 | KnowledgeSearchOutput（参考用，V0.1 仅在 provenance 中透传，不进成稿主体） |
| `recommendation` | 否 | RecommendationOutput：`status` / `primary_recommendation{candidate_id,fit,reason_codes,provenance[]}` / `alternatives[]` |

- `additionalProperties: false`，仅接受上述五块。
- `knowledge_search` / `recommendation` 可为 `null`（缺失 → 在 `metadata.warnings` 标 `MISSING_UPSTREAM_RESULT`）。

## 二、输出契约（`schemas/report-output.schema.json`）

| 字段 | 说明 |
|------|------|
| `skill` / `version` | 固定 `"report-generation"` / `"0.1"` |
| `status` | `success` / `INSUFFICIENT_INPUT` |
| `structured_report` | 8 固定章节（见下表） |
| `rendered_report` | 8 章节 Markdown 文本 |
| `validation` | `{passed, errors[], warnings[], conflicts[]}` |
| `metadata` | `{source_skills[], upstream_status{}, conflicts[], warnings[]}` |
| `provenance[]` | `{claim, source, confidence}` 关键陈述溯源 |

### `structured_report` 八章节

| 章节 | 字段 | 来源 |
|------|------|------|
| `client_profile` | `{fields[]{label,value,status,source}, note}` | client_state 全部 profile |
| `financial_profile` | `{table[]{item,value,status,source}, note}` | client_state.financial_profile |
| `risk_exposure` | `{R1..R5{present,risk_category,risk_status,risk_name,description,severity,impact,existing_protection,coverage_gap,conclusion,source}}` | risk_analysis.risks |
| `coverage_gaps` | `[{risk_category,current_protection,main_gap,priority,source}]` | risk_analysis + requirement_analysis |
| `requirement_priorities` | `[{requirement_id,type,summary,priority,priority_label,source}]` | requirement_analysis |
| `recommended_directions` | `[{rank,candidate_id,fit,rationale,covered_requirements,covered_risks,notes,source}]` | recommendation |
| `information_gaps` | `[{field,importance,category,reason,source}]` | requirement_analysis + risk_analysis + client_state |
| `next_actions` | `[{action,reason,priority,dependency}]` | 由 information_gaps 推导 |

## 三、adapter 契约（`scripts/upstream_results_adapter.py`）

`normalize_input(input_dict, rules)` 返回：
```
{client_state, requirement_analysis, risk_analysis, knowledge_search, recommendation,
 missing_core, all_core_missing}
```
- 任一核心块为 `None`/缺字段 → 对应子项 `missing=True`。
- `all_core_missing`：三路必填全部缺失 → 引擎返回 `INSUFFICIENT_INPUT`。
- adapter 为**只读**：绝不修改入参字典，缺失降级为 `missing`，不反向写入上游。
