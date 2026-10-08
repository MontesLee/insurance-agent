# Phase 28.C Readiness Assessment — Insurance QA Agent + Knowledge Grounding

Date: 2026-09-25 · 性质：READ-ONLY 就绪评估（28.A-2 spec Step 5；**不实施
QA Agent，不改 WeKnora**）。评估对象：ADR-022（APPROVED，fail-closed
grounding 裁决）在 28.C 开工前的代码/数据/决策就绪度。

结论先行：**代码侧 GO-WITH-PREREQUISITES；数据侧两处外部阻塞（B2/B3，
不阻塞代码、阻塞用户价值）；三项人工决策未决（HD-2 / 目录 schema /
qa-answer 产物政策）。**

## 1. WeKnora 集成点（现成，无需改动）

- **KnowledgeService 已生产形态**：provider → governance → evidence 三段
  （knowledge/service.py:223-391），fail-closed K001-K004；治理 R1-R9 +
  PG 注册表 + 三锚点哈希 + 仅 ACTIVE 版本可 ground。
- **WeKnora transport 为纯检索**（weknora.py:175-431）：不用 LLM 总结，
  Ask/ReAct 结构性禁止——与 ADR-022 "WeKnora=证据，LLM=推理表达" 边界
  天然一致。
- **28.C 的集成缝**：AnswerContext 走 KnowledgeService **新接口**（证据
  chunk 正文+溯源戳进入 LLM 上下文），不碰 Provider Protocol / 治理层 /
  provenance / transport / mock-live 选择语义（ADR-022 冻结清单）。
- 运维已知项（Phase 24 记录）：embedding-model KB 构建易卡死、KB-scoped
  keys、tenant header——QA 联调环境需按此配置。

## 2. AnswerContext 缺口（28.C 核心工程量）

现状实证（2026-09-25 复核，行号仍准）：

| # | 缺陷 | 证据 | 28.C 动作 |
|---|---|---|---|
| 1 | 证据从不进入 LLM 上下文——`_knowledge_search` 只回报 "knowledge-evidence stored (N evidence items)" + artifact_id | runtime/agent/tools.py:402-404 | 新增 AnswerContext 受控通道（唯一取证入口） |
| 2 | 答案文本零代码门禁——无 tool call 的纯文本直接被接受为最终答案 | runtime/agent/agent.py:96-100 | 引用闭环门（cited⊆evidence、关键句带引用；失败拒答/降级） |
| 3 | 工具描述谎言——描述承诺 "Returns evidence chunks with document ids — cite them" 而实现不返回 | runtime/agent/schemas.py:163-165 vs tools.py | 描述与实现同步修正（ADR-022 附带修正 #1，修后冻结同步） |
| 4 | 无 LLM 调用治理网关接线——chat 路径绕过 ADR-011 网关 | 28.0.1 隐耦 #6 | 28.C 开工前裁决：QA LLM 走网关（推荐，偿清 R6）或显式记 debt |

## 3. 证据 grounding 边界（裁决已在，执行面就绪）

- 判定规则已定（ADR-022 §1）：事实型问题 → Catalog 查表优先，查不到
  **FAIL CLOSED**（"目录暂无该数据"），禁止 WeKnora/LLM 补位；知识型
  问题 → WeKnora 证据 grounding。
- 四类故障路径全部映射既有机制（retrieval failure / insufficient /
  conflicting / stale——冲突检测已内建等待期/免赔额/赔付比例）。
- 离线回归路径就绪：mock provider 全链可离线跑（ADR-022 迁移策略第一
  步），knowledge 离线 50+28 套件为回归基线。

## 4. KB 数据缺口（外部阻塞 B2 —— 不阻塞代码，阻塞价值）

- 现库仅 **10 份监管文本**；concepts/clauses/cases 三域覆盖薄。
- **HD-2（人工决策，未决）**：KB 数据集建设方向与投入。28.C 可先以
  现有 10 份文本上线灰度（拒答率会高——诚实代价），语料运营并行。
- Scenario A（"重疾险和医疗险区别"类）依赖 concepts 域语料。

## 5. Catalog 依赖（外部阻塞 B3 —— Scenario D 硬前提）

实证（2026-09-25）：`catalog/product-catalog.v0.1.json` 12 个 demo 产品，
字段 19 个，**waiting_period / exclusions / health_declaration 数据与
schema 双缺**；`check_catalog_product` 只返回 id/名称/公司/版本
（runtime/agent/tools.py:420-422 slim 字段）。

- 28.C 第一步 = **目录 schema 决策**（人工）：新增字段可选进 schema、
  生产模式必填（沿 catalog_governance.py:41-45 既有语义，demo 数据
  兼容）。
- 数据工程并行（不阻塞代码）；**数据不落地则 Scenario D（"等待期多久"）
  上市即 fail-closed 拒答**——诚实但无价值，需运营同步投入。

## 6. 依赖链核对（相对 28.A）

| 依赖 | 状态 |
|---|---|
| ADR-022 批准 | ✅ APPROVED（28.0.5） |
| IntentResult / Router / Registry 契约 | ✅ 28.A-0/A-1/A-2 已交付（shadow 运行中） |
| QA 意图切权威路由 | 28.C 范围内动作（ADR-020 迁移策略："28.C 起 QA 意图真实路由"）——切换前需 shadow 一致性报告达标（当前语料基线 22/22、100% legacy 映射一致） |
| qa-answer 是否成 artifact / 是否产 Review Card | ❌ **未决**（28.0.3 留待裁决；触发 eval.rules / risk-rules / contracts 联动 + 卡面诚实规则——28.0.1 隐耦 #8，必须在 28.C 开工前定案） |
| LLM 网关（ADR-011）接线或记债 | ❌ 未决（§2 #4） |
| HD-2 KB 数据集 | ❌ 未决（§4） |
| 目录 schema 决策 | ❌ 未决（§5） |

## 7. 就绪判定与开工前置清单

**判定：CONDITIONALLY READY** —— 代码侧前置（AnswerContext 缝、引用
闭环门、描述修正、故障路径）全部有明确落点与离线回归路径；开工前必须
完成：

1. 人工裁决 qa-answer artifact/Review Card 政策（阻塞卡面与 eval 联动）。
2. 人工裁决 QA LLM 调用走 ADR-011 网关 or 记 debt（推荐前者）。
3. 目录 schema 决策（第一步，数据工程并行）。
4. shadow 一致性报告在真实流量上复核（服务器重启后积累；当前 live 8 条
   尚无 annotated legacy 记录——annotate 覆盖率列入 28.C 切换验收）。
5. HD-2 KB 数据集方向（不阻塞代码开工，阻塞灰度开答范围）。

（本文件仅为就绪评估；任何 WeKnora/Catalog/knowledge 代码改动均属 28.C
授权范围，本阶段未触碰。）
