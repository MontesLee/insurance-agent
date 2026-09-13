# Eval Policy（评估唯一真源）

可机检断言才判 PASS；自然语言断言记 `MANUAL` 且不计入通过（AGENTS.md §6）。

## 维度与接受标准
1. **Retrieval Recall**：gold evidence 进入 candidate set → PASS
2. **Top-K Precision**：top_k 中相关比例 ≥ 阈值（默认 0.6） → PASS
3. **Ranking**：相关结果高于弱相关 → PASS
4. **Source Priority**：同内容下 official/internal > 普通 → PASS
5. **Abstention**：知识库无对应知识 → `insufficient_evidence` → PASS
6. **Conflict Detection**：构造 A=30天 / B=90天 → `conflict=true` → PASS
7. **Metadata Filter**：`product_type=medical` 不得返回 life 作为主要结果 → PASS

## 负向自检
注入污染（如伪造高 `source_score` 但语义不匹配的 chunk）→ 不得排到顶部 → 复绿。
运行：`scripts/run_knowledge_search_dataset.py`（全量回归）+ `scripts/test-knowledge-search.py`（单测）。
