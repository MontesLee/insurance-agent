# ADR Dependency Map — Phase 28.0.2

Date: 2026-09-25 · 正式 ADR 已落 `docs/adr/ADR-019..024`（Status 全部
PROPOSED）。本文件承载：Task 1 差距分析（提案→成文前后对照）、Task 3
依赖图与阻塞 ADR、编号对照与位置说明。

---

## 1. ADR Gap Analysis（Task 1）

对照九段结构（Status/Context/Problem/Decision/Alternatives/
Consequences/Implementation boundary/Migration strategy/Validation
criteria），提案态（migration-280 §20 表行）→ 成文态（docs/adr/）：

| ADR | 提案态缺失（成文前） | 成文后状态 |
|---|---|---|
| ADR-019 Intent Layer | ❌Status（无文件）❌Alternatives ❌Impl boundary ❌Migration ❌Validation；⚠️Problem/Context 散在审计 | ✅ 九段齐备（IntentResult schema+扩展字段；LLM propose / deterministic decide / Router 只消费 IntentResult 三规则成文） |
| ADR-020 Router Contract | 同上六缺 | ✅ 九段齐备（YES=intent→agent；NO=业务逻辑/workflow/知识检索/产品推荐四禁+置信度再评分与 LLM 永禁；import 白名单硬约束） |
| ADR-021 Agent Registry | 同上六缺；⚠️字段清单在迁移文档 §5 | ✅ 九段齐备（单一真源字段：id/capability/supported_intents/tools/workflow/output types+schema/risk/knowledge deps/internal；启动 fail-closed 校验） |
| ADR-022 Knowledge Grounding | 同上六缺；⚠️吸收了"WeKnora/Catalog 边界"主题后边界更大 | ✅ 九段齐备（WeKnora=regulations/concepts/clauses/cases；Catalog=products/parameters；LLM=reasoning/explanation/communication；无证据保险事实=FAIL CLOSED；四故障路径；AnswerContext+引用闭环门） |
| ADR-023 Chat Artifact Experience | **整案缺失**（原仅 28.F 路线行） | ✅ 九段齐备（User 面=Text+Artifact；markdown/HTML/PDF 矩阵【PDF=浏览器打印优先，服务端另案】；dev metadata 永不作主显示；渲染器唯一性） |
| ADR-024 Conversation Case Lifecycle | 同上六缺；❌card 键控/槽位两个破坏点未列 | ✅ 九段齐备（Conversation→Case→Run；continuation/modification/history/review linkage 四机制；card 键控与 RunManager 槽位列入边界） |

**结论**：六案九段全部齐备；遗留待批准时裁决项：ADR-022 §4 的
qa-answer artifact/卡面政策、ADR-021 开放项 O-1（Unified Runtime 是否
另立 ADR）、ADR-023 的服务端 PDF 另案。

## 2. 编号对照与位置说明

- 位置（实测）：**docs/adr/ 是本项目 ADR 原生家**——已有 ADR-001..007
  （Skill 时代创始决策，中英双语成对，含 ADR-002 orchestrator-over-
  pipeline、ADR-004 deterministic-eval、ADR-005 evidence-provenance）；
  本批 ADR-019..024 按规格落于此（单文件中文，命名沿 `ADR-NNN-slug.md`
  旧例）。**docs/production/ 存放 ADR-008..018**（生产化时代系列）。
  编号 007→008 跨了目录（历史形成）。建议未来统一回收索引，本阶段
  不动历史文件。
- 编号重排（vs migration-280 §20 临时编号）：临时 019（Unified
  Runtime）→ 未立案（O-1）；临时 020（Intent+Router）→ 拆为正式
  019+020；临时 021/022 → 正式 021/022；临时 023（WeKnora/Catalog）
  → 并入正式 022；正式 023 为新主题（原 28.F）；临时 024 → 正式 024。
  迁移文档 §20 已加声明指向本对照。
- 与创始 ADR 的关系：019-024 **不推翻** 001-007 任何决策——004
  （确定性评估）是 019/022 确定性优先的直接依据；005（证据溯源）是
  022 的底座；002（orchestrator over pipeline）与 021 的"workflow
  引用共享图"一致。

## 3. ADR Dependency Graph（Task 3）

```
ADR-019 Intent Layer                    （根：无 ADR 依赖）
  │ IntentResult 唯一输入
  ├──────────────► ADR-020 Router Contract
  │                   ▲ Registry 唯一 Agent 来源
  ├──────────────► ADR-021 Agent Registry（supported_intents ⊆ 019 分类）
  │                   │
  └───┬───────────────┴──► ADR-022 Knowledge Grounding
      │                       （QA Agent = 019+020+021 的首个消费者）
      │
      └───────────────────► ADR-024 Conversation/Case/Run Lifecycle
                              （modify_existing_plan 意义依赖 019；
                               agent 身份依赖 021）

ADR-023 Chat Artifact Experience ── 弱依赖 021（output types 声明）；
                                   无阻塞依赖，可独立批准/实施
```

批准顺序建议（与依赖一致）：**019 → 021 → 020 →（022、023、024
任意序）**。实施顺序另见 phase-28-implementation-plan.md §5.1
（28.A 同时落 019+020+021 契约）。

## 4. Blocking ADRs（阻塞关系）

| 阻塞者 | 被阻塞 | 语义 |
|---|---|---|
| **ADR-019** | 020/021/022/024 的实施 | 无 IntentResult 即无路由输入、无 supported_intents 词表、无 modify 意图 |
| **ADR-021** | 020 的实施 | Router 无表可查（无 registry 条目） |
| **019+020+021** | ADR-022 的实施（28.C） | QA Agent 需要被意图路由到 |
| **ADR-021** | ADR-024 的实施（28.E） | continuation 路由到已注册的 planning agent |
| ADR-023 | （无被阻塞者） | 独立；其深链功能被 URL 路由（28.G）阻塞——非 ADR 依赖 |
| 开放项 O-1（Unified Runtime 无 ADR） | 28.B/28.D 的**架构裁决** | 由 implementation-plan §5 + migration-280 §11 承载；若评审要求 ADR 化，须在 28.B 开工前补立 |

外部阻塞（非 ADR，运维/数据）：KB 语料（022 价值）、目录 schema+数据
（022 的 Scenario D）、行为等价门先建（021 实施前提之一）。
