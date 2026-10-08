# Phase 28.C-3 · QA Knowledge Coverage

Date: 2026-09-28 · ≤20 分钟时限·只读探针+写入路径审计（写入 BLOCKED·零
KB 变更·零 runtime 改动）。

## Status

**28.C-3 BLOCKED**（在「真实 KB 写入」一步：WeKnora admin JWT 不在库
且 28.H 会话凭据已过期。其余全部就绪：BEFORE 探针已建已跑、语料已
定位并验证、解封 runbook 已写。）

## 1. Problem Confirmed

A 型 G-1（概念题 0 命中→insufficient_evidence 快拒）经 10 问探针实证
[MEASURED·tools/qa_concept_hit_probe.py]。

## 2. Existing HD-2 Coverage

- WeKnora KB insurance-pilot-2 + PG registry 16 条 ACTIVE：
  10 部 pilot 法规（knowledge/pilot/documents/pilot_law/reg_*）+
  fixtures 城市级保障知识（项目自测语料）。
- **概念类生产语料在库但未入 KB**：`domain/insurance/references/`
  7 篇（00 产品分类/01 百万医疗/02 重疾/03 意外/04 寿险/05 健康核保/
  06 理赔·共 ~11KB），头部带 `domain-pack: version=1.0
  effective_date=2026-09-14 source_level=B code=*` 权威生产语料标记
  （非测试数据）+ 配套治理表 fixtures/domain_sources.json（7 条）。
- 结论：**不是"缺知识"而是"已有权威语料未接入 pilot KB"**。

## 3. Missing Concept Coverage（探针 BEFORE·2026-09-28）

total 10 · hits 7 · misses 3 · hit_rate 70%（见 §7 质量校正后实际更低）：
- **零命中 3**：医疗vs重疾区别 / 免赔额 / 定期vs终身寿险——恰为
  01/02/04 域文档主题
- **弱相关命中**：意外险→健康保险管理办法（法规边缘）；保额vs保费→
  互联网保险业务监管办法（边缘）——法规语料对概念题支撑力不足
- 有效命中：等待期/犹豫期（健康保险管理办法）·现金价值/受益人
  （人身保险产品信息披露管理办法）

## 4. Corpus Added

**NONE（写入 BLOCKED）**。已验证就绪的语料=既有 7 篇域文档（§六 来源
要求满足：项目权威生产语料+version/source_level 头，非模型记忆编写）。
文档身份：`domain/insurance/references/0[0-6]_*.md`。

## 5. Retrieval Probe

`tools/qa_concept_hit_probe.py`（可重复·真实生产路径
KnowledgeService→WeKnora→治理·无 LLM·无门改动·只读）。
判定：HIT=治理后 evidence≥1 且 substance 对题（snippets 列供人工复核）；
MISS=0 命中或明显无关——不把 HTTP 200 当 HIT。

## 6. Before / After Evidence

BEFORE [MEASURED]：见 §3（tmp/obs/c3_probe.json）。AFTER：N/A（写入
BLOCKED）。

## 7. Hit Rate

形式 hit_rate=70%；**实质质量校正**：3 零命中 + ≥2 弱相关（意外险/
保额保费）→ 有效概念支撑率约 50%。如实记录，不美化。

## 8. Remaining Misses

全部 3 个零命中 + 2 个弱相关将在域文档入库后复测（probe 一键重跑）。

## 9. Citation Gate Status

**NOT TOUCHED**（gate/markers/prompt/模型/重试零改动；B 型校准=28.C-4）。

## 10. Product Catalog Status

**NOT TOUCHED**（DEFAULT OFF 维持；本阶段语料不含任何具体产品/推荐）。

## 11. Tests

- `pytest tests/runtime/test_k22_qa_streaming.py -q` → **6 passed**
- 探针实跑 1 次（10 问·只读）

## 12. Remaining Blockers

**KB_WRITE_BLOCKED**：`knowledge/pilot/ingest_registry_pg.py`（Phase 24A
既有幂等管道 prepare→INGESTED→REGISTERED→VALIDATED→ACTIVE）需要
`INSURANCE_AGENT_WEKNORA_JWT`（admin 会话）——不在库、28.H 会话已过期。
**解封 runbook**（Owner/管理员执行，约 10 分钟）：
①将 7 篇域文档纳入 pilot 语料表（knowledge/pilot/registry/
pilot_sources.json 增 7 行·source_level=B·复用 domain_sources.json 元数据）
②导出 WeKnora admin JWT 至环境 ③`python knowledge/pilot/ingest_registry_pg.py`
（幂等）④复跑 `python tools/qa_concept_hit_probe.py` 取 AFTER。
不新增第二套导入机制。

## 13. Recommendation

Owner 提供 admin JWT（或指认持有者）→ 按 runbook 执行 ④ 后本阶段即
COMPLETE（预期零命中 3 问全部转 HIT）。随后进 28.C-4（B 型引用校准·
先观测违规分布）。

---

## KB Ingest Unlock（28.C-3R · 2026-09-28 执行记录）

**28.C-3R STATUS: BLOCKED**（KB_WRITE_BLOCKED 维持）

- §三 JWT 检查：`INSURANCE_AGENT_WEKNORA_JWT` **不存在于当前 shell
  环境**（tmp/ 亦无 JWT 文件——仅核对文件名，未读内容）。
- 按任务书规则：不询问粘贴·不写文件·STOP。零 ingest·零 KB 变更·
  零 probe 重跑（无 BEFORE→AFTER 变量产生）。
- 解封方式（不变）：在**启动本 Claude Code 会话的终端**设置
  `INSURANCE_AGENT_WEKNORA_JWT` 环境变量（JWT 由 WeKnora admin 登录
  会话取得）后重新执行 28.C-3R——子进程才能继承该变量。
- Citation Gate：NOT TOUCHED · Production Runtime：NOT TOUCHED。
