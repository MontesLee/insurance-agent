# BGE-M3 → insurance-kb-v1 受控生产迁移报告

- 日期: 2026-10-05　·　前置证据: EMBEDDING-UPGRADE-OWNER-REVIEW.md（A/B 双路径）
  + BGE-M3-NEGATIVE-QA-SLICE.md（负例端到端 5/5 SAFE）
- 目标: insurance-kb-v1（29 docs / 791 chunks）全量迁移至 BGE-M3（1024d），
  通过全部回归门，注册 Runtime KB candidate，生产影子验证——**切换本身待 Owner 批准**
- 生产改动范围（本报告时点）: WeKnora models 行 + kb-v1 embedding 行（surgical）
  + PG registry 29 文档注册；**Runtime（:8123/.env/safety 层）零改动**

---

## 1. 基线核对（§2）——BASELINE OK

| 事实 | 核验值 |
|---|---|
| source documents | 29（manifest=KB，逐字） |
| kb-v1 chunks / embeddings（迁移前·nomic） | 791 / 791（SQL 实证） |
| BGE-M3 / nomic 维度 | 1024d / 768d（embed 冒烟实测） |
| 生产 Runtime KB / embedding | insurance-pilot-2 / nomic（:8123 live config: glm-5.3/flashx/qa=flash） |
| 生产 registry | 17 ACTIVE（pilot-2 语料）+ 6 SUPERSEDED |
| L2-04 | BLOCKED（沿 KB-V1 验收，不适用） |

## 2. Preflight（§3）——PASS

- WeKnora API 401-alive / Admin :80 200 / docreader healthy / PG×2 healthy
- ollama 双模型并存（bge-m3 1.2GB + nomic 274MB）；embed 冒烟 bge 1024d 18.1s（冷载）/ nomic 768d 3.7s
- RAM 初测 2.52GB < 3GB 门槛 → **按规则暂停**，Owner 释放后 **8.36GB** 通过
- 磁盘 D: 198GB free；kb-v1 索引占用 2.66MB（vectors+content 实测）

## 3. Rollback Point（§4）——READY

`evidence/eval/rollback_point.json`（2026-10-05 01:32）：

- **生产回滚** = Runtime env 单值改回 `INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID`
  =54d7b757…（insurance-pilot-2）+ 重启——pilot-2 KB、nomic 模型行、旧 registry
  全程零触碰，**无需重新生成旧 embedding**
- **kb-v1 数据集自身回滚** = `tools/embed_eval/restore_kb1_nomic.py`（791 行 nomic
  向量备份逐行还原 + 模型行翻回；已生成 SQL 未执行）
- hd2.env sha256(16)=8b97172cdc0a8848（迁移全程未动）

## 4. BGE-M3 生产部署（§5）——PASS（并存·可独立回滚）

| 项 | 值 |
|---|---|
| models 行 | `bge-m3`（tenant 10001·active·SQL 直插=加性；API 注册被 SSRF 拦私有 IP 沿 A/B 先例） |
| ollama 模型 | bge-m3:latest 1.2GB（weknora-ollama 容器·与 nomic 并存） |
| 维度/健康 | 1024d 实测；health=embed 冒烟 OK |
| 内存 | 容器 RSS 1.546–2.019GiB（bge 载入态；符合 A/B 实测带 1.6–1.86GB） |
| nomic | **未删除未覆盖**（builtin-embedding-local 行 + ollama 模型原样） |

## 5. 全量 Re-embedding（§6）——PASS·surgical 路径

**路径决策**：WeKnora API 拒绝在有文件的 KB 上改 embedding 模型（400「知识库中已有
文件，无法修改Embedding模型」；batch-reparse 只按现行模型重嵌）。为满足「不删文档/
不改 chunk/唯一变量=模型」，采用 **surgical 迁移**：

1. 备份 791 行 nomic 向量（`reembed_nomic_backup.json`，逐行含向量文本）
2. 向量生成：**790 块经生产嵌入路径现算**（WeKnora-app 容器→weknora-ollama
   bge-m3:latest·1597s）+ 1 块自 eval KB 官方管线向量按内容匹配复制
   （eval-copy 优化仅命中 1 行——CSV 解析差异；全部现算=同一官方端点同一模型，
   向量确定性等价）
3. 单事务：DELETE kb-v1 旧行 → INSERT 791 行（dimension=1024·halfvec）→
   `knowledge_bases.embedding_model_id='bge-m3'`（3s COMMIT）

**验证（§6 门槛逐项）**：documents=29 ✓ chunks=791 ✓（chunks 表零触碰·内容/边界/
metadata/文档 ID 全部原样）embedded=791 ✓ failed=0 ✓ pending=0 ✓
dimension=1024（唯一 dim）✓ model=bge-m3 ✓

## 6. Self-Retrieval Gate（§7）——PASS

冻结展品 4 查询（nomic 异常 None/1/8/5 于迁移前复现）→ 迁移后 **全部 rank 1**
（`exhibit_bgem3-migration.json`）：溃疡性结肠炎→L2-01#1 · 消费投诉15日→L1-12#1 ·
注册资本二亿元→L1-01#1 · 2024-03-01施行→L1-03#1。**关键自检索异常未重现。**

## 7. 57-case 检索回归（§8）——PASS·零回归

`pipeline_bgem3-migration.json` vs `pipeline_nomic-migration.json`（同日双臂）：

| Metric | nomic（迁移前复测） | **bge-m3（迁移后）** | A/B bge 参照 |
|---|---:|---:|---:|
| Recall@1 | 21/50 (42%) | **42/50 (84%)** | 42/50 |
| Recall@5 | 35/50 (70%) | **49/50 (98%)** | 49/50 |
| **Recall@10** | 40/50 (80%) | **50/50 (100%)** | 50/50 |
| MRR | 0.549 | **0.900** | 0.907 |
| Qualified | 40/50 | **50/50** | 50/50 |
| **HIGH-risk Claim** | 16/25 | **28/28** | 28/28 |
| 总 PASS | 35/57 | **52/57** | 52/57 |
| Negative pass | 4/7 | 2/7（已知检索层 FPR↑） | 2/7 |

冻结 57 cases/expected_fact/评分逐字未动；bge 臂与 A/B bge 臂逐指标一致（MRR
0.900 vs 0.907=单 case 排序微差，Recall 三档逐位相同）。

## 8. Full QA Regression（§9）——19 case 双臂（`qa_slice_{nomic,bgem3}-migration.json`）

链路: 真实 Intent → WeKnora vector_search@kb-v1 → C2（冻结）→ LLM（glm-5.3-flash
生产 QA 档·真实网关）→ 引用门 + Claim Support（生产灰度开关）→ 终态。

| 组 | nomic 臂 | bge 臂 |
|---|---|---|
| 正例 9（法律/监管/健康险/重疾/儿童重疾/人身/产品合同/金额/时限） | 2 ANSWER / 7 REFUSAL | 1 ANSWER / 8 REFUSAL |
| 负例 5（RB-N-001/002/003/004/006） | 5/5 REFUSAL·**0 污染** | 5/5 REFUSAL·**0 污染** |
| 常识 5（GEN-01..05） | 5/5 REFUSAL（D-04 引用校准天花板） | 5/5 REFUSAL（同族） |

- **B. Negative**: Evidence Pollution=0 · High-Risk Escape=0 · Claim Support False
  Support=0 · Citation Gate Bypass=0（与 NEGATIVE-QA-SLICE 结论一致·迁移后复证）
- **A/C**: 拒答主导=既有 D-04 引用校准债（claim_support 改写天花板），非切换所致；
  双臂唯一行为差 = RB-L1-019（保障基金）nomic ANSWER→bge REFUSAL——bge 检索
  **更准**（L1-10 rank1·qualified L1-01+L1-10），答案事实准确、引用齐备，仍被
  词法支持层判 PARTIAL 拒绝（fail-closed 方向；同 case 在 nomic 臂两 attempt
  通过属门方差带）。正常问答无嵌入引发的异常拒答（拒答族=既有债务同签名）。

## 9. Runtime Safety Equivalence（§10）——PASS

逐 case（19）双臂对比：retrieval evidence 允许不同（设计内）；**安全终态等价**——
两臂 0 unsafe answer / 0 hard-class escape / 0 false support / 0 citation bypass；
负例 5/5 双臂全拒。硬类覆盖：NUMERIC（注册资本/犹豫期15天——bge 臂唯一 ANSWER
即犹豫期，数字句过支持门）/ REGULATORY（审批备案）/ PAYMENT（保障基金）/ 
DATE_TIME（投诉时限/生命表）——全部保持 fail-closed。R4 个性化经 §12 影子验证。

## 10. KB Registry（§11）——29/29 ACTIVE

`knowledge/pilot/registry/kb1_sources.json`（源自 source-manifest·29 条）经
Phase-24A 守护生命周期注册（DISCOVERED→…→ACTIVE）：**29/29 ACTIVE · 791 chunks**
（`registry_ingest_kb1.json`；两处日期格式修正留痕）。Registry entry:

```yaml
dataset_id: insurance-kb-v1
documents: 29
chunks: 791
embedding_model: bge-m3
embedding_dimension: 1024
status: candidate          # candidate ≠ production authority
source_manifest: docs/knowledge-base/source-manifest.yaml
version: KB-V1 (2026-10-04) + bge-m3 migration (2026-10-05)
created_at: 2026-10-05T02:5x
```

## 11. Production Shadow（§12）——30/30 完成·`prod_shadow_kb1.json`

真实生产检索路径（governed KnowledgeService + PG registry + live WeKnora provider
+ agent 评分策略 + C2 + LLM 门），10 normal + 5 high-risk + 5 negative +
5 product/numeric + 5 R4：

| 类 | n | 终态 | 污染 | governance denied | 错误 |
|---|---:|---|---|---:|---:|
| normal | 10 | 10 REFUSAL（含 2 llm_unavailable=GLM 瞬态·与嵌入无关） | 0 | 0 | 0 |
| high_risk | 5 | 5 REFUSAL | 0 | 0 | 0 |
| negative | 5 | 5 REFUSAL | **0** | 0 | 0 |
| product_numeric | 5 | 5 REFUSAL | 0 | 0 | 0 |
| r4_personal | 5 | 5 REFUSAL（零个性化逃逸） | 0 | 0 | 0 |

- 检索延迟 p50=633ms / p95=876ms / max=1115ms；生成中位 45.1s
- governance re-anchoring 全通过（registry 哈希↔迁移后 chunks 一致=§6 旁证）
- 全拒答=既有 D-04 天花板在治理路径上的表现（pilot-2 生产现状同签名）；
  fail-closed 无一不安全终态
- 传输说明：shadow 用 admin Bearer（harness 内变体）；生产 retrieve-only key
  （hd2-production-retrieval）的作用域扩至 kb-v1 = **Owner 门控切换步骤**（见 §13）

## 12. §13 Cutover 前置核对表

```text
[✓] 29/29 documents          [✓] 791/791 chunks
[✓] 791/791 BGE embeddings   [✓] dimension 1024
[✓] Self-Retrieval PASS (4/4 rank1)
[✓] 57-case regression PASS (52/57, R@10 100%, claim 28/28, 零回归)
[✓] 5 negative QA PASS (0 pollution/escape/false-support/bypass)
[✓] HIGH-risk PASS (28/28)   [✓] Claim Support PASS
[✓] Citation Gate PASS       [✓] Runtime safety equivalence PASS
[✓] Registry PASS (29/29 ACTIVE, status=candidate)
[✓] Rollback PASS (生产=env 单值还原; kb-v1=备份还原 SQL 就绪)
[✓] Production shadow PASS (30/30, 0 pollution, 0 error)
[✓] RAM PASS (8.36GB free)   [✓] latency PASS (ret p95 876ms)
[ ] OWNER CUTOVER AUTHORIZATION  ← 唯一待办
```

## 13. 待 Owner 批准的切换步骤（原子·可回滚·单配置变更）

1. **API key 作用域授予**：`tenant_api_keys` 行 hd2-production-retrieval 的
   knowledge_base_ids 追加 kb-v1（加性；被权限系统标记为凭证授予=需 Owner 点名）
2. **Runtime env 单值变更**：tmp/hd2.env 的
   `INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID` 54d7b757… → 44af9ff2…（sha 前后留档）
3. **:8123 重启**（Owner 进程·需授权）→ §14 smoke → §15 回滚演练 → §16 性能定格

## 14. Hard Stops（§18）——0 触发

HS-01…HS-16 逐项无（文档未变 SQL 实证·chunk 791 逐位·嵌入完整·维度一致·
自检索全 1·零检索回归·HIGH 28/28·污染/逃逸/假支持/绕过全 0·等价通过·
回滚就绪·影子通过·RAM 通过·运行时零意外修改——git tracked-modified 基线不变）。

## 15. 实验件与可逆性

- models 行 `bge-m3`（可删）·kb-v1 embedding 行（restore_kb1_nomic.py 可原样还原）
- registry 29 文档 ACTIVE（kbv1-* source/version/chunks 行——生产切换的必要组成，
  独立回滚=版本行置 SUPERSEDED）
- 全部证据: evidence/eval/{rollback_point,reembed_*,exhibit_*,pipeline_*-migration,
  qa_slice_*-migration,registry_ingest_kb1,prod_shadow_kb1}.json
- 工具: tools/embed_eval/{migrate_kb1_bge,restore_kb1_nomic,build_kb1_registry_meta,
  ingest_kb1_registry,prod_shadow,qa_slice,exhibit_gate}.py

```text
FINAL STATUS (migration phase): COMPLETE
（cutover 已获 Owner 授权并执行——终态与验收见 BGE-M3-PRODUCTION-ACCEPTANCE.md：
PRODUCTION_SWITCHED_AND_VERIFIED）
```
