# Recommendation — Usage Guide

## 调用形态

Recommendation 是确定性引擎，**不依赖 LLM**。上层 Agent / Orchestrator 按 Input Contract 组装四块结构化输入，调用引擎得到结构化输出。

### 直接运行（CLI）

```bash
python scripts/recommendation_engine.py examples/input_sample.json
# 带自定义规则：
python scripts/recommendation_engine.py examples/input_sample.json resources/config/recommendation.rules.json
```

### 作为模块

```python
from recommendation_engine import generate_recommendation, load_rules
out = generate_recommendation(input_dict, load_rules())
```

### 校验输出

```bash
python scripts/validate_output.py output.json
# 期望打印 OUTPUT_VALID，exit 0；否则 OUTPUT_INVALID + 错误列表，exit 1
```

## 输入组装要点

1. `requirement_analysis`：直接传入 requirement-analysis 的 `RequirementAnalysisOutput`（不要重做需求分析）
2. `risk_analysis`：直接传入 risk-analysis 的 `RiskAnalysisOutput`（risks 在 `risk_analysis[]` 或 `risks[]` 均可，adapter 兼容）
3. `candidate_solutions`：候选方案数组，每条至少含
   - `candidate_id`、`solution_name`
   - `coverage_structure`（覆盖的需求类型列表，如 `["medical","critical_illness"]`）
   - `coverage_partial`（可选，部分覆盖的类型）
   - `covers_risk_categories`（覆盖的风险域，如 `["R1","R2"]`）
   - `premium.annual`、`term.years`、`liquidity_impact`（low/medium/high）
   - `source_refs` / `evidence_refs`（指向 knowledge_search_results 的 chunk_id）
4. `knowledge_search_results`：knowledge-search 的输出，用于证据校验
5. `constraints`（可选）：`budget_max` / `term_min_years` / `liquidity_required`，由 orchestrator 从 client-intake 经 adapter 解析

## 不要做的事

- 不要在本 Skill 内重新跑 requirement-analysis / risk-analysis
- 不要凭记忆补产品条款——无 `source_refs` 命中的 coverage 会被标 `insufficient_evidence`
- 不要把 primary 推荐当成承保结论；`human_review_required=true` 时交人工

## 与 knowledge-search 的关系

Recommendation 不实现 RAG。若候选方案缺少证据，应先调用 `knowledge-search` 取得 `knowledge_search_results` 再传入本 Skill。详见 `CONTRACT.md` 与 `references/03-evidence-policy.md`。
