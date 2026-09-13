# 检索策略（Retrieval Policy）

## Pipeline
`Query → Normalize → Candidate Retrieval(over-retrieval) → RRF Fusion → Reranking → Evidence Filter → Structured Output`。

## Query Normalize
轻量处理：去口语 filler、保留保险专业关键词、必要时提取核心概念；**不得凭空增加用户未表达的事实**。
归一化结果用于检索；原始 query 原样保留在输出 `query` 字段（不污染用户意图）。

## Candidate Retrieval（Over-Retrieval）
- `final_k = 5`（默认返回条数），`candidate_k = 20`（先召回候选再重排），`candidate_k = final_k × over_retrieval_factor`。
- V0.1 仅 `SparseRetriever`（纯 Python trigram-BM25，CJK 友好，零依赖）。
- `DenseRetriever` 接口已留位（`dense_enabled=false`），未来装好 embedding 模型即插即用，无需改主逻辑。

## RRF Fusion
多路召回（sparse / dense）用 Reciprocal Rank Fusion 合并：`score += 1/(k+rank+1)`，`k=rrf_k`(默认 60)。
优先 RRF 而非直接加权重（除非两路分数已严格归一）。

## 召回评估（离线）
- **Recall@K**：gold evidence 是否进入 candidate set。
- **Precision@K**：top_k 中真正相关的比例。
- 见 `evals/eval-policy.md` 与 `scripts/run_knowledge_search_dataset.py`。

## Abstention（最重要）
所有候选 `final_score` 均低于 `min_relevance_score` → `status=insufficient_evidence`，返回空 `results`，**绝不**返回"可能相关"的猜测或让 LLM 自补。
部分达到阈值但 top 分数低于 `partial_threshold` → `status=partial_evidence`。
