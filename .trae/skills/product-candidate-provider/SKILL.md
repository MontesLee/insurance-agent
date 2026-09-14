---
name: product-candidate-provider
description: 从 Product Catalog 中筛出可能符合解决策略的保险产品候选。当需要把 Coverage Gap / Solution 转成具体产品候选、或需要校验产品存在性与投保资格时使用。它只做候选生成，不做推荐。
---

# Product Candidate Provider

## Identity

Skill ID: `product-candidate-provider`
Stage: `PRODUCT`（候选生成子层）
Version: 0.1

## Trigger

- 已有 `SolutionPlan`（+ `CoverageGapAnalysis` / `ClientProfile` / `KnowledgeEvidence`）需要转成产品候选
- 需要校验某个产品是否真实存在于 Catalog、是否符合投保资格
- **不**用于最终推荐（那是 `product-recommendation` 的职责）

## Input

`schemas/input.schema.json`

| 字段 | 必填 | 说明 |
|---|---|---|
| `solution_plan` | 是 | 决定需要什么险种与保障方向 |
| `coverage_gap_analysis` | 否 | `GENERAL` 策略时提供缺口域兜底 |
| `client_profile` | 否 | 仅用于 eligibility（年龄 / 职业） |
| `knowledge_evidence` | 否 | 缺失则该产品 `EVIDENCE_MISSING` |
| `requested_product_ids` | 否 | 不在 Catalog 中的 id 一律 `PRODUCT_NOT_IN_CATALOG` |

## Workflow

1. `solution_type` → `product_types`（规则外置；`GENERAL` 回退缺口域）
2. 过滤 Catalog：**类型不匹配直接不是候选**
3. 逐个候选计算三类判定：
   - `coverage_direction_match` —— 保障方向关键词是否命中
   - `eligibility` —— `ELIGIBLE / INELIGIBLE / UNKNOWN`
   - `evidence` —— 是否有该领域知识证据
4. 输出 `candidates[]` + `admissible_candidate_ids[]` + `rejected[]`

## Output

`schemas/output.schema.json` —— `candidates / admissible_candidate_ids / rejected / unknowns / next_information_needed / catalog / provenance`

状态：`COMPLETE` | `NO_CANDIDATES` | `INSUFFICIENT_INPUT` | `INVALID_PRODUCT`

## Boundary（禁止越界）

- ❌ 不排序、不选主推荐 —— 那是 `product-recommendation`
- ❌ 不创造产品：候选只能来自 `catalog/`，`product_id` 必存在于 Catalog
- ❌ 不把 `EVIDENCE_MISSING` 静默提升为准入
- ❌ 不把 `eligibility=UNKNOWN` 当作通过（UNKNOWN 是独立第三态）
- ❌ 不写回任何上游产物

## References

- `references/01-candidate-selection.md` —— 筛选规则与判定顺序
- `CONTRACT.md` —— 与上下游的契约

## Eval

`evals/eval-policy.md` 为唯一真源。运行：

```bash
python .trae/skills/product-candidate-provider/scripts/test_product_candidate_provider.py
python test-cases/e2e/product-recommendation/run_product_recommendation_e2e.py
```

## Demo 数据警告

`catalog/product-catalog.v0.1.json` 中 `is_demo = true`，全部为**虚构演示产品**，
保费为 `demo_reference` 参考值。不得作为真实可投保产品呈现给客户。
