# CONTRACT — knowledge-search

## 边界
- **输入**：`query`（+ 可选 `filters` / `top_k` / `min_relevance_score` / `debug`）
- **输出**：结构化 `evidence`（带 provenance），`status` 四态之一
- **不**：生成面向客户答案、推荐产品、判断风险、修改 `client-intake` / `requirement_analysis` / `risk-analysis`

## 上游不可变
不修改既有 Skill 任何文件；如需上游数据，走 adapter，不在上游加字段（AGENTS.md §4）。

## 共享基础层
检索实现位于仓库根 `rag/`（独立于本 Skill），所有 Skill 可复用。
本 Skill 只消费 `rag/` 提供的接口，不把检索逻辑塞进自身脚本。
