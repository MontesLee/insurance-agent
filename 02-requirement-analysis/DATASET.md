# Requirement Analysis Dataset

> 状态：Phase 7 Implemented
> 目标：建立可执行的 Requirement Analysis 数据集，并输出统一统计。

---

## 1. 数据集文件

- `02-requirement-analysis/tests/dataset/requirement-analysis.dataset.json`

当前数据集包含 `15` 个 case，覆盖：

- A. Complete Information: 3
- B. Missing Information: 3
- C. Multi-turn Information Collection: 2
- D. Conflicting Information: 2
- E. Unsupported Conclusion: 2
- F. Missing Risk: 1
- G. Product Boundary Violation: 1
- H. Complex Family: 1

---

## 2. 每个 Case 字段

每个 case 至少包含：

- `case_id`
- `category`
- `input`
- `expected_behavior`
- `expected_status`
- `key_information`
- `expected_risks`
- `expected_priority`
- `eval_requirements`

可选字段：

- `pre_update_expected_questions`
- `expected_questions`
- `expected_evidence`
- `forbidden_behavior`
- `updates`
- `mutation`

---

## 3. 运行脚本

- `scripts/run-requirement-analysis-dataset.ps1`

Runner 会自动处理三类 case：

1. 正常分析
2. 多轮补充后再分析
3. 先分析、再造错、再跑 eval

---

## 4. 输出统计

Runner 输出：

- `Overall Pass Rate`
- `Completeness`
- `Evidence Grounding`
- `Information Sufficiency`
- `Logical Consistency`
- `Product Boundary`

同时输出每个 case 的：

- `expected_status / actual_status`
- `expected_eval_status / actual_eval_status`
- `actual_issue_types`
- `actual_risks`
- `actual_question_fields`
