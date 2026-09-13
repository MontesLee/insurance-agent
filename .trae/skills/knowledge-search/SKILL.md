---
name: knowledge-search
description: >
  Retrieve grounded insurance knowledge from the knowledge base. Use when the agent
  needs factual insurance knowledge (product-category explanations, policy concepts,
  underwriting rules, claims rules, waiting periods, pre-existing conditions, etc.).
  Returns structured evidence with provenance — NOT a client-facing answer.
---

# Knowledge Search

## 何时调用
仅当 Agent 需要外部保险知识支撑时调用，例如：
"百万医疗险和重疾险有什么区别？"、"等待期是什么？"、"既往症怎么认定？"、"医保外用药一般怎么赔？"。
**不用于**：寒暄、采集客户事实（client-intake）、需求分析（requirement_analysis）、风险判断（risk-analysis）。

## 输入
见 `schemas/knowledge-search-input.schema.json`。核心字段：
- `query`（必填）
- `top_k`（默认 5）
- `filters`（预留：product_type / topic / source_level 等）
- `min_relevance_score`（默认 0.55，来自 rules）
- `debug`

## 输出
见 `schemas/knowledge-search-output.schema.json`：
- `status`: `success` | `partial_evidence` | `insufficient_evidence` | `retrieval_error`
- `results[]`：每条带 `chunk_id / document_id / document_name / source_level / section / content / score`
- `conflict`：来源冲突时置 `true`（保留双方证据，不自动合并）
- `retrieval_metadata`：`candidate_count / returned_count / retrieval_method / reranker`

## 核心工作流
`Query → Normalize → Sparse Retrieve(over-retrieval) → RRF → Rerank(加权) → Evidence Filter → 结构化输出`。
检索引擎在独立基础层 `rag/`（Retriever / Reranker 可替换；V0.1 仅稀疏检索）。

## 失败 / 边界处理
- 无足够可靠知识 → `status=insufficient_evidence`（**绝不**凭 LLM 自补事实）
- 仅有部分知识 → `status=partial_evidence`
- 来源冲突 → `conflict=true`，保留双方证据，交上层判断
- 本 Skill **不**生成面向客户的答案、不推荐产品、不修改上游 Skill

## References（渐进加载，勿全塞进本文件）
- `references/01-retrieval-policy.md` — pipeline / over-retrieval / RRF / 召回
- `references/02-source-policy.md` — S/A/B/C/D 来源等级、冲突、时效
- `references/03-ranking-policy.md` — 语义/关键词/领域/来源/特异性 加权
- 权重与阈值：`resources/config/ranking.rules.json`、`resources/config/retrieval.rules.json`（外置，引擎只读）

## Eval
见 `evals/eval-policy.md`；运行 `scripts/run_knowledge_search_dataset.py`。
