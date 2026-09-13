# 排序策略（Ranking Policy）

## 综合评分（外置权重，见 ranking.rules.json）
`final_score = semantic*W1 + keyword*W2 + domain*W3 + source*W4 + specificity*W5`

| 维度 | 含义 | 默认权重 |
|---|---|---|
| semantic | 语义相关（V0.1 取 dense；无 dense 时回退 sparse 归一） | 0.10 |
| keyword | 关键词/trigram 重叠（BM25 归一） | 0.35 |
| domain | 领域匹配（query 产品类型 == chunk 产品类型 → bonus，否则 penalty） | 0.20 |
| source | 来源等级质量（S/A/B/C/D 映射） | 0.25 |
| specificity | 特异性（有明确 `product_type` 的 chunk 更高） | 0.10 |

权重不必和为 1；各候选间做 min-max 归一后加权，结果再做阈值过滤。

## 为什么不能只看语义相似度
例：query「百万医疗险等待期」下，"保险等待期的通用定义"应低于"百万医疗保险等待期及等待期内出险处理规则"。
综合 `domain + specificity` 后后者排前，符合直觉。

## 调参
只改 `ranking.rules.json`，不碰引擎代码（确定性优先，AGENTS.md §5）。
