# 调用指南（Usage Guide）

## 作为脚本运行
```bash
python scripts/invoke-knowledge-search.py --query "百万医疗险和重疾险有什么区别" --top-k 5
python scripts/invoke-knowledge-search.py --query "..." --debug          # 输出候选分数
python scripts/invoke-knowledge-search.py --query "..." --min-relevance 0.6
```
输出为 `knowledge-search-output.schema.json` 结构的 JSON（写入 `tmp/` 并回显）。

## 作为库调用（其他 Skill / Orchestrator 复用 rag/ 基础层）
```python
import sys; sys.path.insert(0, "<repo-root>")
from rag.store import KnowledgeStore
from rag.engine import KnowledgeSearchEngine
import json
rules = json.load(open(".../retrieval.rules.json"))
rules.update(json.load(open(".../ranking.rules.json")))
store = KnowledgeStore(); store.ingest_dir("<kb_dir>")
engine = KnowledgeSearchEngine(store, rules)
result = engine.search("百万医疗险和重疾险区别")
print(result.to_dict())
```

## 上层 Agent 用途
Knowledge Search 输出的是"**证据**"，不是"**答案**"。上层基于 `results[]` 生成最终回答；
无证据 / 部分证据时由上层决定改写 query、换工具或告知用户资料不足。
