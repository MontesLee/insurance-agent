# BGE-M3 → insurance-kb-v1 生产切换验收报告

- 日期: 2026-10-05　·　迁移报告: BGE-M3-PRODUCTION-MIGRATION.md（§3-§12 全门禁 PASS）
- Owner 授权: 2026-10-05（AskUserQuestion 书面确认「授权切换+演练，终态保持 BGE」，
  含三步点名：①API key 作用域追加 kb-v1 ②hd2.env KB id 单值变更 ③重启 :8123）
- 前置证据: EMBEDDING-UPGRADE-OWNER-REVIEW（A/B）· BGE-M3-NEGATIVE-QA-SLICE（负例端到端）

---

## 1. Cutover（§13）——原子·可回滚·单配置变更·已执行

| 步骤 | 执行记录 |
|---|---|
| ① API key 作用域 | `tenant_api_keys` hd2-production-retrieval：knowledge_base_ids 追加 44af9ff2（1→3 KBs·加性·回滚=移除）；此前被权限系统拦截待 Owner 点名→授权后执行 |
| ② env 单值变更 | tmp/hd2.env `INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID` 54d7b757→44af9ff2；sha256(16) 8b97172cdc0a8848 → **9fd1e638da5652bb**（kb-v1 态）/ 8b97…（回滚态） |
| ③ :8123 重启 | 原 PID 39992（**FIX-3 Phase-12 authority 实验实例**·2026-10-03 起·其设计即 restart=移除·实验产物 tmp/obs/k29c_* 在盘保留可随时重启）停止 → 标准 strict controlled_pilot 启动（uvicorn runtime.server:create_app·hd2.env+hd2.key+hd2.pgpass+hd2-data.key+CLAIM_SUPPORT_ENABLED=1=生产灰度）→ **strict 预检 PASS → health 200** |

**切换前 §13 全条件核对：29/29 docs · 791/791 chunks · 791/791 bge embeddings · Self-Retrieval 4/4 rank1 ·
57-case 52/57（R@10 100%·HIGH 28/28·零回归）· 负例 QA 5/5（0 污染/0 逃逸/0 假支持/0 绕过）·
安全等价 PASS · Registry 29/29 ACTIVE(candidate) · Rollback READY · Shadow 30/30 PASS ·
RAM 8.36GB · latency PASS —— 全绿后才执行切换。**

## 2. Cutover Smoke（§14）——PASS（`cutover_smoke.json`·15 turns 真实 HTTP API）

- **Health**: Admin :80 200 · backend :8123 200 · embedding（ollama bge 冒烟 1024d）·
  runtime strict healthy · diagnostics（operator key）: controlled_pilot/weknora/registry=postgres ✓
- **Retrieval**: 15/15 turns 终态正常（QA 切片轮经**作用域 API key** 实检 kb-v1=切换闭环）
- **Safety 5 high-risk**: 5/5 诚实拒答（引用门族）——无数字/日期/法规错误输出
- **Safety 5 negative**: G2（受治理锚→QA 切片）引用门拒答；G1/G3/G4/G5（无锚 unknown→
  通用 agent 路径·**与嵌入无关的既有路由**）输出**纯常识回答**——全文零保险证据内容、
  零引用、零保险事实 → **EVIDENCE_POLLUTION = 0**（bge 检索噪声未进入任何答案）
- **User-visible**: 15/15 非空答案 · 泄漏扫描 0（无 run_id/ART-/chunk/L1-xx/[E#]）·
  拒答文案=固定模板（无错误事实）· 无异常空答案
- 观察项（既有·非切换回归·如实记录）：①9/10 正常与高危题=引用门拒答（D-04 校准
  天花板·pilot-2 生产同签名）②S-N5（偿付能力）agent 环 3×RuntimeError→needs_review
  （tool_calls=0·零检索参与·K.12 首真用户同族签名）

## 3. Rollback Rehearsal（§15）——PASS（双向实证·`kb_probe.py`+WeKnora 请求日志）

```text
bge / kb-v1（基线探针+smoke·WeKnora 日志见 44af9ff2 请求）
  ↓ env 单值还原（sha 回 8b97172cdc0a8848）+ 重启（~30s）
nomic / pilot-2（health 200·探针轮正常完成·WeKnora 日志实证 54d7b757 请求）
  ↓ env 复位 44af9ff2（sha 9fd1e638da5652bb）+ 重启（~30s）
bge / kb-v1（终态·health 200·探针完成·WeKnora 日志实证 44af9ff2）
```

- 回滚**不依赖任何重嵌入/重下载**（pilot-2+nomic 全程未动；kb-v1 数据集级还原脚本
  restore_kb1_nomic.py 另行就绪）
- 验证方法说明：拒答模板无法区分两库（pilot-2 的 17 文档语料+评分阈值对判别查询同样
  放行少量证据）→ 以 **WeKnora 请求日志中的 knowledge_base_id** 为权威实证
- QA/safety 健康：回滚态探针轮全走完且 fail-closed

## 4. Performance（§16·实测）

| 项 | 值 |
|---|---|
| embedding RSS（weknora-ollama） | 1.546–2.019 GiB（bge 载入态·符合 A/B 带 1.6–1.86GB） |
| 嵌入期 CPU | ~400%（多线程 CPU 推理） |
| 检索延迟 | p50 **633ms** · p95 **876ms** · max 1115ms（影子 30 查询·治理全链） |
| QA 轮 E2E（真实 API） | 9–75s（中位 ~20s·LLM 生成主导·与切换前同族） |
| rebuild duration | **1600s**（790 块生产路径现算）+ 3s SQL 事务 ≈ **27min**（surgical 路径；对照 batch-reparse 全管线 ~2h） |
| index size | 2.66MB（791×1024 halfvec+content） |
| container restart | 迁移零重启；切换/回滚各 1 次 :8123 重启（~14s 就绪） |
| 资源匹配 | 生产=实验同机同容器（无 mismatch） |

## 5. Hard Stops（§18）——0 触发（全程）

HS-01 文档未变（SQL 实证）· HS-02 791 逐位 · HS-03 全嵌 · HS-04 1024 唯一 ·
HS-05 自检索 4/4 rank1 · HS-06 零回归 · HS-07 28/28 · HS-08-11 全 0 ·
HS-12 等价 PASS · HS-13 回滚双向实证 · HS-14 影子 30/30 · HS-15 RAM 8.36GB ·
HS-16 git tracked-modified 基线 347 全程不变（本任务产物均在未跟踪 docs/knowledge-base
/tmp/.agent spans；生产代码/safety 层零改动）。

## 6. 最终生产状态

```text
Production Runtime KB : insurance-kb-v1 (44af9ff2-ecef-445e-87c6-cb1458cd4d44)
Embedding            : bge-m3 (1024d · models 行 bge-m3 · ollama bge-m3:latest)
Runtime              : :8123 strict controlled_pilot · CLAIM_SUPPORT_ENABLED=1（灰度沿袭）
Registry             : PG registry·29 kb-v1 文档 ACTIVE（+pilot-2 17 既有 ACTIVE）
Rollback             : env 单值还原+重启（~30s·已演练）；kb-v1 数据集级 nomic 还原脚本就绪
```

## 7. Phase16 状态

```text
Phase16 REAL_USER_CONTROLLED_COHORT: NOT RESUMED
```

未恢复 Phase16 · 未开启 Authority（FIX-3 实验实例已按其设计随重启移除·可另行重启）·
未开启 Hybrid · 未开启 S2/Batch-2 · 未恢复任何真实用户流量。

## 8. 遗留与建议（不阻塞·Owner 备忘）

1. D-04 引用校准天花板仍是答案侧主约束（切换后 9/10 知识题诚实拒答）——杠杆在
   prompt/模型档/结构豁免线（既有 Owner 决策项），与嵌入无关。
2. S-N5 类 agent 环 RuntimeError→needs_review 签名（K.12 首真用户同族）值得后续归因。
3. FIX-3 Phase-12 authority 实验实例随切换重启移除（其实验产物在盘）；恢复实验=重启
   其 launcher，需考虑与 kb-v1 新基线的关系。
4. kb-v1 数据集级 nomic 还原脚本已就绪未执行（生产回滚不需要它）。

```text
FINAL STATUS: PRODUCTION_SWITCHED_AND_VERIFIED
（cutover + smoke + rollback rehearsal 全部通过；Owner 已于 2026-10-05 授权；
  生产现跑 insurance-kb-v1 + bge-m3；等待 Owner 最终确认存档）
```
