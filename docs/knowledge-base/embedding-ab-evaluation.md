# KB-V1 Embedding A/B Evaluation（直连余弦基准）

- 日期: 2026-10-04　·　实验变量: 唯一=Embedding 模型
- 冻结不变: 29 份文档 / 791 个 live chunks（与 insurance-kb-v1 逐块一致·SQL 提取） / 57 个 benchmark cases /
  expected_fact / 资格层(C2 词法地板) / Claim Support / top-10
- 隔离: 纯直连 ollama embeddings + 主机侧余弦排序——零 WeKnora 变更、零生产触碰；
  WeKnora 管线级复验（eval dataset insurance-kb-v1-eval-bge-m3）另行在案
- 双模型同一驱动同一批处理同一代码路径（tools/embed_eval/run_eval.py，可复跑）

## 模型与成本

| | nomic-embed-text (baseline) | bge-m3 (candidate) |
|---|---|---|
| dimension | 768 | 1024 |
| 模型体积 | 274 MB | 1.2 GB |
| 加载内存（容器 RSS 实测） | ~0.40 GB | 1.6–1.86 GB |
| GPU | 无（纯 CPU） | 无（纯 CPU） |
| 791 块索引嵌入 | 628 s（794 ms/块） | 1068 s（1351 ms/块） |
| 热查询单条时延（中位） | 0.29 s | 0.36 s |
| 向量存储（float32, 791 块） | 2.4 MB | 3.2 MB |

## 核心对照表（57 冻结 cases）

| Metric | nomic | bge-m3 | Delta |
|---|---:|---:|---:|
| Recall@1 | 26% | 82% | +0.56 |
| Recall@5 | 58% | 100% | +0.42 |
| Recall@10 | 68% | 100% | +0.32 |
| MRR | 0.398 | 0.891 | +0.49 |
| Qualified Evidence | 33/50 (66%) | 50/50 (100%) | +17 例 |
| Claim Support (HIGH-risk) | 8/18 | 28/28 | - |
| Negative Retrieval Pass | 6/7 | 3/7 | -3 例（恶化） |
| Negative FPR | 0.14 | 0.57 | +0.43 |
| Self-Retrieval@1 (prefix64) | 82% | 80% | -0.02 |
| Self-Retrieval@5 (prefix64) | 100% | 98% | -0.02 |
| Self-Retrieval@10 (prefix64) | 100% | 100% | +0.00 |

## 关键判读

1. **嵌入模型被确认为主要瓶颈（正例侧）**：nomic 27 例失败全部归因 RANKING（块可被自身前缀找回、
   但 case 查询语义匹配不上）；bge-m3 将正例失败清零（Recall@10=100%、资格 50/50、HIGH 风险 Claim 28/28）。
2. **KB 数据层与切分层被排除**：两模型失败矩阵 DATA_MISSING=0、CHUNKING=0——此前验收的 22 例失败
   中，expected_fact 全部逐字在库内；换模型后同一语料同一查询全部通过。
3. **『nomic 中文≈噪声』结论修正**：nomic 直连前缀自检索 @10=100%——纯嵌入可用；此前 WeKnora 管线
   自检索展品（rank=None/8/5）为**管线层伪影**（子块索引/父窗口展开），非嵌入本身失效。
4. **负例恶化是真实权衡**：bge-m3 FPR 0.14→0.57。其更强的中文语义把『驾驶证/门诊/年检/身份证』等
   近域查询忠实检索到共享词面的保险条款（交强险/疾病定义/中介登记），且冻结的词法资格地板放行。
   两模型挂的负例集不同（nomic 挂社保养老；bge-m3 反而正确空回）。生产实际边界=引用门+Claim Support
   （确定性·SEALED），检索噪声≠交付答案——但本实验未做端到端问答验证，此为管线复验项。
5. **无关文本基线相似度**：nomic 两段无关中文法条 cosine=0.742 vs bge-m3=0.440——bge-m3 区分度
   结构性更强，与全部指标一致。

## 术语阶梯判别（§15）

| 阶梯查询 | nomic 最近文档 | bge-m3 最近文档 |
|---|---|---|
| 保险销售 | L1-06 (0.8121) | L1-03 (0.7077) ✓ |
| 保险销售行为 | L1-12 (0.831) | L1-03 (0.782) ✓ |
| 保险销售行为管理 | L1-12 (0.8372) | L1-03 (0.7359) ✓ |
| 保险销售行为管理办法 | L1-12 (0.861) | L1-03 (0.7931) ✓ |
| 重大疾病 | L2-02 (0.702) | L2-02 (0.6231)  |
| 重大疾病保险 | L2-02 (0.8136) | L2-02 (0.7488)  |
| 重大疾病保险的疾病定义 | L2-02 (0.8695) | L2-01 (0.7814) ✓ |
| 重大疾病保险的疾病定义使用规范 | L2-02 (0.8742) | L2-02 (0.8272)  |

- 相邻阶梯术语相似度（不可分度）：nomic 销售『行为/行为管理』=0.996、重疾『定义/规范』=0.996 —— 近乎同一向量；
  bge-m3 同对 =0.915/0.887 —— 分得开。
- 销售阶梯 4 级 bge-m3 全部第一命中 L1-03《保险销售行为管理办法》；nomic 全部指错（L1-12/L1-06）。

## 分层自检索（prefix64@1 / @10）

| 层 | nomic @1/@10 | bge-m3 @1/@10 |
|---|---|---|
| 政策意见 (n=1) | 100% / 100% | 100% / 100% |
| 法律 (n=5) | 100% / 100% | 100% / 100% |
| 监管规章 (n=36) | 83% / 100% | 81% / 100% |
| 监管通知 (n=1) | 100% / 100% | 0% / 100% |
| 行业规范-疾病定义 (n=7) | 57% / 100% | 71% / 100% |

- 全层 @10 双模型均 100%。监管通知层 @1 样本极小（n≤2），@1 差异不具统计意义。
- identical-text 自检索（整段原文作查询）双模型 @1 均 94%（6% 为同文重复块的并列排序），
  数学上预期≈1，仅作退化性记录。

## 失败矩阵（正例失败归因）

| 类别 | nomic | bge-m3 |
|---|---:|---:|
| DATA_MISSING | 0 | 0 |
| CHUNKING | 0 | 0 |
| EMBEDDING | 0 | 0 |
| RANKING | 27 | 0 |
| QUALIFICATION | 0 | 0 |
| NEGATIVE_NOISE | 1 | 4 |
| UNKNOWN | 0 | 0 |

## 证据文件

- evidence/eval/eval_nomic.json / eval_bge-m3.json（全 case 全 ranking）
- evidence/eval/emb_*_index|queries|selfprefix|ladder_*.json（全部向量缓存，可复算）
- evidence/eval/chunks_791.json（冻结语料快照）
- self-retrieval-comparison.json（§12 逐块对照）
- tools/embed_eval/run_eval.py（评测器，双模型同路径）
## 管线级复验（WeKnora 真实检索路径·vector_search）

nomic 臂=insurance-kb-v1（只读复测）；bge-m3 臂=insurance-kb-v1-eval-bge-m3
（隔离 eval dataset·同 29 文件·791 块与交付库逐块同数（L2-01=35/L2-02=44））。

| Metric | nomic(管线) | bge-m3(管线) |
|---|---:|---:|
| Recall@1 | 22/50 (44%) | 42/50 (84%) |
| Recall@5 | 35/50 (70%) | 49/50 (98%) |
| Recall@10 | 40/50 (80%) | 50/50 (100%) |
| MRR | 0.560 | 0.907 |
| Qualified Evidence | 40/50 | 50/50 |
| Claim Support (HIGH) | 16/25 | 28/28 |
| 总 PASS | 35/57 | 52/57 |
| Negative Pass | 4/7 | 2/7（恶化） |

### 原自检索展品复测（KB-V1 验收失败根因的修复验证）

| 逐字查询 | nomic 管线(事实块rank) | bge-m3 管线 |
|---|---|---|
| 严重溃疡性结肠炎… | None（未进top-10） | **1** |
| …15日内作出处理决定 | 1 | **1** |
| …注册资本…二亿元 | 8 | **1** |
| …自2024年3月1日起施行 | 5 | **1** |

直连 A/B 与管线 A/B 结论一致；nomic 的管线自检索异常在 bge-m3 管线下全部归 1。
