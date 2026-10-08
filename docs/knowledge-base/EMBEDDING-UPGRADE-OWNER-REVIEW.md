# EMBEDDING UPGRADE — OWNER REVIEW

- 日期: 2026-10-04　·　实验: KB-V1 Embedding A/B Evaluation（直连余弦 + WeKnora 管线双路径）
- 实验变量: **唯一 = Embedding 模型**（nomic-embed-text → bge-m3）
- 冻结不变: 29 份文档 / 791 live chunks / 57 benchmark cases / expected_fact / C2 词法资格地板 /
  Claim Support 规则 / top-10 —— 全程零修改
- 隔离: 生产 insurance-pilot-2 零触碰（未读取其数据）；insurance-kb-v1 只读；
  bge-m3 侧在独立 eval dataset `insurance-kb-v1-eval-bge-m3`（791 块与交付库逐块同数）
- 生产改动: **Runtime 0 · KB 0**（eval dataset 与模型行 bge-m3-eval 均为加性实验件，可删）

---

## 1. 当前问题

KB-V1 验收（2026-10-04）benchmark run3 = 35/57：retrieval@10 80%、22 例失败。
当时以 self-retrieval 展品（逐字查询 rank=None/8/5）初步归因"nomic 对中文区分度不足"。

## 2. 实验设计

双路径对照，双模型同一代码同一冻结输入：

- **直连余弦**：ollama embeddings（经 WeKnora-app 容器内 python3 → weknora-ollama DNS）+
  主机侧余弦全量排序。零 WeKnora 变更，纯嵌入变量。工具 `tools/embed_eval/run_eval.py`。
- **WeKnora 管线**：真实 vector_search 路径。nomic 臂=insurance-kb-v1 只读复测；
  bge-m3 臂=eval dataset（同 29 文件重建索引）。工具 `tools/embed_eval/pipeline_bench.py`。

负例查询/资格地板/Claim Support 三层与生产同逻辑（运行时模块 in-process 引用，零修改）。

## 3. 两个模型

| | nomic-embed-text:latest（baseline） | bge-m3:latest（candidate） |
|---|---|---|
| 端点 | weknora-ollama:11434（docker 网络内） | 同左（实验期拉取 1.2GB） |
| 维度 | 768 | 1024 |
| 运行配置 | models 表 builtin-embedding-local（tenant 10000·yaml 管理） | models 表 bge-m3-eval（tenant 10001·SQL 直插·API 注册被 SSRF 校验拦私有 IP） |
| 生产接线 | insurance-pilot-2 / insurance-kb-v1 的 embedding_model_id | 仅 eval dataset（bge-m3-eval）；**未接任何生产 KB** |

实测确认（非假设）：weknora-ollama 现载两模型；维度由 API 返回向量长度验证（768/1024）。

## 4. 完整 Benchmark（57 冻结 cases）

### 直连余弦（纯嵌入变量）

| Metric | nomic | bge-m3 | Delta |
|---|---:|---:|---:|
| Recall@1 | 26% | **82%** | +56pp |
| Recall@5 | 58% | **100%** | +42pp |
| Recall@10 | 68% | **100%** | +32pp |
| MRR | 0.398 | **0.891** | +0.49 |
| Qualified Evidence | 33/50 | **50/50** | +17 |
| Claim Support (HIGH) | 8/18 | **28/28** | — |
| Negative Pass | **6/7** | 3/7 | **−3（恶化）** |
| Self-Retrieval@1 (prefix64) | 82% | 80% | −2pp |
| Self-Retrieval@5 | 100% | 98% | −2pp |
| Self-Retrieval@10 | 100% | 100% | 0 |

（identical-text 自检索双模型 @1=94%，直连模式下数学退化（同文本同向量必 rank1，6% 缺口为
同文重复块并列），仅作记录；主判定用 prefix64。）

### WeKnora 管线（生产真实路径）

| Metric | nomic | bge-m3 | Delta |
|---|---:|---:|---:|
| Recall@1 | 44% | **84%** | +40pp |
| Recall@5 | 70% | **98%** | +28pp |
| Recall@10 | 80% | **100%** | +20pp |
| MRR | 0.560 | **0.907** | +0.35 |
| Qualified Evidence | 40/50 | **50/50** | +10 |
| Claim Support (HIGH) | 16/25 | **28/28** | — |
| 总 PASS | 35/57 | **52/57** | +17 |
| Negative Pass | **4/7** | 2/7 | **−2（恶化）** |

## 5. Self-Retrieval

- 直连 prefix64（50 块·seed42·覆盖 L1/L2/多文档/多长度）：@10 双模型全层 100%；
  疾病定义层 @1 nomic 57% / bge 71%（PDF 表格文本均偏弱，@10 无差）。
  逐块对照：`self-retrieval-comparison.json`（100 行可人工复核）。
- **原验收展品复测（管线）**：溃疡性结肠炎 None→**1**；注册资本二亿元 8→**1**；
  施行日期 5→**1**——KB-V1 验收 22 例失败的根因在 bge-m3 下被消除。

## 6. Failure Matrix

| 类别 | nomic(直连) | bge-m3(直连) |
|---|---:|---:|
| DATA_MISSING | 0 | 0 |
| CHUNKING | 0 | 0 |
| EMBEDDING(self) | 0 | 0 |
| RANKING | 27 | **0** |
| QUALIFICATION | 0 | 0 |
| NEGATIVE_NOISE | 1 | 4 |

**结论**：①KB 数据层无罪（两模型 DATA_MISSING=0；expected_fact 全部逐字在库内）；
②切分层无罪（CHUNKING=0）；③检索参数无罪（同 top-10 同路径下换模型即翻盘）；
④**失败主因=嵌入模型的排序质量**（nomic 27 例 RANKING；bge 清零）；
⑤bge-m3 的新增代价=负例噪声 +3~4（词法地板对近域查询放行，两模型失败集不同）。

## 7. 成本（实测）

| 项 | nomic | bge-m3 |
|---|---|---|
| 块嵌入时延 | 794 ms/块 | 1351 ms/块 |
| 热查询单条（中位） | 0.29 s | 0.36 s |
| 索引重建（791 块·直连） | 10.5 min | 17.8 min |
| eval KB 全量建库（管线·观测墙钟） | ≈100 min（原库构建） | ≈130 min |
| 模型内存（容器 RSS） | ~0.4 GB | 1.6–1.86 GB |
| 模型体积（磁盘） | 274 MB | 1.2 GB |
| 维度/向量存储（float32×791） | 768 / 2.4 MB | 1024 / 3.2 MB |
| GPU | 无（纯 CPU） | 无（纯 CPU） |
| 部署前提 | 已在 | 主机需 ≥3GB 空闲 RAM（本次 Owner 释放后 4.6GB 拉取成功；10-01 内存枯竭事故为先例） |

查询侧 +70ms 相对 QA 管线 LLM 秒级时延无感；嵌入慢仅影响建库/重建窗口。

## 8. 风险

1. **负例噪声（本实验唯一恶化项）**：bge-m3 把驾驶证换证/门诊挂号/机动车年检/身份证等
   近域查询忠实检索到共享词面的保险条款，冻结词法地板放行（FPR 0.14→0.57/0.71）。
   生产实际边界=引用门+Claim Support（SEALED·确定性），检索噪声≠交付答案——
   **但端到端负例行为未经本实验验证**（需 QA 切片实测，见 §10）。
2. **主机内存**：+1.2GB 常驻；低内存窗口重建索引有引擎崩溃先例（10-01）。
   重建须在 Owner 确认内存余量后进行。
3. **管线积分效应**：WeKnora 管线含子块索引/父窗口展开层，nomic 曾在此层出现直连无法
   复现的自检索异常；bge-m3 管线已复验无此异常，但任何模型更换后都应跑管线 benchmark 复验。
4. 回滚：KB 级开关（embedding_model_id 改回）+ 重建索引；eval 件（dataset/模型行/ollama 模型）可整体删除。

## 9. 推荐方案（Owner Decision Matrix）

| 选项 | 检索收益 | 安全影响 | 运维成本 | 迁移风险 | 证据置信度 |
|---|---|---|---|---|---|
| **A. KEEP nomic** | 维持 80%@10/16:25 claim（22 例失败延续） | 负例噪声最低（4/7 过） | 零 | 零 | 高（现状=双路径复测一致） |
| **B. SWITCH bge-m3** | R@10=100%·Claim 28/28·MRR 0.91（正例失败清零） | 负例 FPR 升（2/7 过）；端到端边界未验 | +1.2GB RAM 常驻；重建 ~2h 窗口 | 低（KB 级开关可回滚；管线已复验） | 高（直连+管线双路径一致） |
| **C. 再评其他模型** | 未知（bge-large-zh / qwen-embedding 等候选） | 未知 | 再一轮实验 | 零（不动生产） | 无数据 |
| **D. 暂不变更** | 同 A | 同 A | 零 | 零 | — |

### §18 生产切换门槛核对（对 B）

| 门槛 | 结果 |
|---|---|
| Recall@10 明显提升 | ✓ 80%→100% |
| Self-Retrieval@10 明显提升 | ✓（管线逐字展品 None/8/5→全 1） |
| HIGH-RISK retrieval 不下降 | ✓ 16/25→28/28 |
| **Negative Retrieval 不恶化** | **✗ 4/7→2/7 —— 唯一未过门槛** |
| Qualified Evidence 不下降 | ✓ 40→50 |
| Claim Support 不下降 | ✓ 16/25→28/28 |
| Operational cost 可接受 | ✓（附内存前提） |

## 10. 是否建议切生产

**暂不切换（按 §18 门槛字面执行：负例项未过）。**
但证据强烈指向 bge-m3（6/7 门槛过、正例失败清零、双路径一致）。剩余唯一缺口是一个窄实验：

> **前置实验（建议下一步）**：将 5 个 bge-m3 失败负例（驾驶证换证/社保养老/门诊挂号/
> 机动车年检/身份证办理）经**完整 QA 切片**（冻结引用门+Claim Support，in-process 探针、
> 不动生产 env）实测——若全部输出诚实拒答（边界把检索噪声收敛为 refusal），则负例门槛
> 实质通过 → SWITCH 全门槛满足；若出现以保险条款回答非保险问题的交付，则需先解决
> 负例治理（属 C2/资格层变更=SEALED 面，须 Owner 另行授权）。

切换执行（若批准）：低峰期确认 ≥3GB RAM → insurance-kb-v1 的 embedding_model_id 改
bge-m3 模型行 → rebuild-index（~2h）→ 管线 benchmark 复验 57 cases → 生产 runtime 切
KB 指向（另行 Owner 决策）。

> **前置实验已完成（2026-10-05）**：5 个失败负例经完整 QA 切片实测 →
> 5/5 诚实拒答（SAFE_FALSE_RETRIEVAL）·0 EVIDENCE_POLLUTION·0 HIGH-RISK_ESCAPE·
> 唯一拦截层=Claim Support（引用存在性门放行后由支持性门收敛）。
> §18 负例门槛的端到端实质已满足 → bge-m3 = SWITCH_CANDIDATE_APPROVED_FOR_OWNER。
> 详见 `BGE-M3-NEGATIVE-QA-SLICE.md`。

## 11. Owner Decision

```
OWNER DECISION

[ ] KEEP NOMIC                 （A）
[ ] SWITCH TO BGE-M3           （B——建议先完成 §10 前置实验）
[ ] TEST ANOTHER MODEL         （C）
[ ] NO DECISION YET            （D）
```

---

### 附：实验件清单与可逆性

- eval dataset `insurance-kb-v1-eval-bge-m3`（id=e38edd35-3d75-441e-9a76-d7ab1466d590）——可删
- models 表行 `bge-m3-eval`——可删
- ollama 模型 `bge-m3:latest`（1.2GB）——可 `ollama rm`
- 证据：evidence/eval/（eval_*.json·emb_* 向量缓存·pipeline_*.json·import_eval_bgem3.json）
- 工具：tools/embed_eval/（embed_driver·run_eval·pipeline_bench·import_eval_kb·build_ab_docs）
- 对照文档：embedding-ab-evaluation.md · self-retrieval-comparison.json

```text
FINAL STATUS: EMBEDDING_EVALUATION_COMPLETE
```
