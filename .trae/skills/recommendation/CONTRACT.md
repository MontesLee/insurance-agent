# CONTRACT — recommendation

## 边界

- **输入（V2，Phase 5 起默认）**：`requirement_analysis` + `risk_assessment` +
  `coverage_gap_analysis` + `solution_plan` + `knowledge_evidence`（可选 `constraints`）。
  见 `schemas/product-recommendation-input.schema.json`。
  **`candidate_solutions` 不是输入，且被契约 `not: {required: [...]}` 明确禁止**；
  候选由 `solution_to_candidates.py` 从 `solution_plan.solutions[]` 派生。
- **输入（V1 legacy）**：`requirement_analysis` + `risk_analysis` + `candidate_solutions` +
  `knowledge_search_results`（可选 `constraints`）。仅保留用于既有 11 case 回归基线。
- **输出**：结构化 `evidence-backed recommendation`（见 `schemas/recommendation-output.schema.json`）
- **不**：重新做客户访谈 / 重新做 Risk Analysis / 修改上游 Skill / 推荐具体产品条款凭记忆 / 生成销售话术 / 代表保险公司做承保决定

## 上游不可变（AGENTS.md §4）

- 不修改 `client-intake` / `requirement-analysis` / `risk-analysis` / `knowledge-search` 任何文件
- 上游数据缺失或不兼容 → 在 adapter（`scripts/recommendation_engine.py` 的 `adapt_*`）内归一化并标记 `MISSING_FROM_UPSTREAM` / 降级为 `UNKNOWN`，**严禁反向给上游加字段**
- 上游 `guardrails.product_recommendation_included` 必须为 `false`（requirement-analysis 契约）；若上游越界携带推荐，本 Skill 拒绝采信并在 `uncertainties` 标注

## 共享基础层

- 知识检索复用 `knowledge-search`（`rag/` 基础层）；本 Skill 不重新实现 embedding / vector DB / reranker
- 当 `knowledge_search_results` 缺失时，候选证据的 `evidence.status` 一律降级为 `insufficient`，绝不自行补全产品事实

## 确定性优先（AGENTS.md §5）

- 适配判定、分级、优先级、硬约束拦截全部由 `resources/config/recommendation.rules.json` 驱动，引擎只读不算，零 LLM 依赖，可离线回归
- 所有结构化断言由 `scripts/validate_output.py` 做确定性校验（schema + 业务不变量）
