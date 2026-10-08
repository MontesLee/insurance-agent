# Product Direction Audit — North Star Baseline

Date: 2026-09-24 · Phase 28.1（治理引导）第一份基线审计。
Evidence：本文件所有判断基于代码/测试/实际结构（Phase 27.7.7–28.0 五次
只读审计的 file:line 证据 + 本次 AGENTS.md/CLAUDE.md/docs 阅读复核），
不基于设计文档自我声明。设计文档与代码不一致处已显式标注。

**目标身份（North Star）**：Insurance-domain Chat-first Multi-Agent AI
System。本审计回答：今天离它多远、哪些漂移已在纠正轨道上、哪些无人认领。

---

## 1. Current Product Identity

**今天实际是什么**（一句话）：一个**治理优先的确定性保险规划管线**
（8 阶段 9 技能、eval 唯一门、修复环、审批/Review Card 闭环），外加
**一个真实的单 Agent 对话前端**（默认 chatMode="agent"，live glm 已配，
意图枚举在 prompt 内），以及**一套未接入生产路径的 4 专家多 Agent 层**。

**是否符合目标身份**：**部分符合，处于受控迁移中**。

| 目标身份要素 | 现状 | 判定 |
|---|---|---|
| Insurance-domain | ✅ 全栈保险域（prompt 硬边界"保险相关问题≠客户咨询任务" prompts.py:68-72；9 skill 全保险；知识 6 域 7 用途；33 案例全保险） | 符合 |
| Chat-first | ⚠️ 默认入口是 Chat（App 默认 mode=chat；chatMode 默认 agent, ChatLayout.tsx:30-32），但产物交付不完整、review 闭环不回链 chat、无 URL、按 case 发起 run 只在 Developer Mode | 部分符合（28.A/B/F/G 修复中） |
| Multi-Agent | ❌ 生产路径= 单 Agent（chat）或零 Agent（/api/runs 直调 orch.run, server.py:409）；4 专家+MessageBus 只在 demo/benchmark/审批恢复 | 不符合（28.B/D 修复中） |
| AI System | ✅/⚠️ live LLM 已配置且 chat 默认真实调用；确定性内核无 LLM；治理网关 LLMGateway 未接线 | 部分符合 |

身份结论不是"失败"，而是**迁移中段**：28.0 已把差距转为 ADR-019..024
+ 路线图。本审计的职责是把这些差距**固化为可周期复查的漂移清单**（§3），
防止"文档已批、实现漂走"。

## 2. Current User Journey（真实链路：存在 vs 设计）

```
User ──► Chat UI                 [存在 ✅ 默认入口]
  ↓
Intent                          [部分存在 ⚠️ prompt 内 5 枚举（schemas.py:20-25）
                                   + demo 模式前端关键词表（chatState.ts:22-31）；
                                   独立 Intent Layer = 仅设计（28.0 §4）]
  ↓
Router                          [不存在 ❌ 单 Agent 自选工具；无 intent→agent 表；
                                   设计=28.0 §6 纯查表]
  ↓
Agent                           [部分存在 ⚠️ chat 单 Agent 真实运行；QA/Planning
                                   作为独立 Agent = 仅设计（28.0 §5/§7）；
                                   4 专家存在但不在生产路径]
  ↓
Workflow                        [存在 ✅ 8 阶段 YAML 单图，eval/repair 门内环；
                                   但 workflow 归属=编排器而非"被路由的 Agent"（28.0 §12）]
  ↓
Artifact                        [存在 ✅ 9 类契约工件+血缘；仅最终报告有人类可读
                                   渲染；无 HTML/PDF/导出/深链（27.9 §7）]
  ↓
Response（Chat 内）              [部分存在 ⚠️ 文本+报告弹窗✅；QA 证据不进 LLM
                                   上下文（28.0 §7.1 结构性缺陷）；升级/审批结果
                                   不回链 chat]
```

链路判定：**两端真实、中间空心**——入口与工作流/产物已存在且被 eval/
治理保护；Intent→Router→Agent 三环是设计（已获 ADR 提案，未实现）。

## 3. Architecture Drift Detection

漂移定义：**偏离 North Star 的现存行为**。"尚未建成"不算漂移，"
建成后又长歪/长出平行物"才算；已列入 28.0 路线图的项标注归属阶段。

### 3.1 Chat-first drift

| 漂移 | 证据 | 级别 | 归属 |
|---|---|---|---|
| 按 case 发起 run 的唯一 UI 在 Developer Mode（非 Chat） | DeveloperMode.tsx:24-43（chat 亦可经 demo 映射/agent 工具发起，但"选 case 直跑"仅开发者面） | **P1** | 28.B/D |
| 产物交付不完整：仅最终报告进 chat；无导出/深链/多产物视图 | ArtifactCard.tsx:32-67；全库无 PDF/导出端点 | **P1** | 28.F |
| review/升级终态在 chat 只落文案，闭环发生在另一 mode | chatState.ts:207-218 | **P1** | 28.B（回链卡） |
| 无 URL 路由：案例/run 不可寻址不可分享 | App.tsx 4 localStorage 模式 | P2 | 28.G（承 27.8-A） |
| demo 关键词映射与 agent 模式并存，同一输入两种语义 | chatState.ts:22-31 | P2 | 28.A（降级为显式示例开关） |

### 3.2 Agent drift

| 漂移 | 证据 | 级别 | 归属 |
|---|---|---|---|
| **多 Agent 层存在但生产路径不使用**（本任务点名项） | /api/runs worker 直调 orch.run 绕过专家（server.py:409）；chat 不上 registry/MessageBus（tools.py:463-465）；专家仅 demos/benchmark（B011）+审批恢复 | **P0**（多 Agent 是 North Star 核心，双世界是 28.0 判定的根问题） | 28.B/D |
| 4 专家与 chat Agent 工具边界不一致（专家裁剪+越权拒绝 vs chat 全局 10 工具） | executor.py:89-96,158-168 vs agent.py:49-52 | P1 | 28.B（收编） |
| 7 个运行追踪存储并存，chat/PG 队列完全未链接 | 28.0 §1.2 表 | P1 | ADR-024 目标态 |

### 3.3 Workflow drift

| 漂移 | 证据 | 级别 | 归属 |
|---|---|---|---|
| 意图→工具选择（=路由+工作流知识）混在**同一个 prompt** 里 | prompts.py:12-41（每意图直接写死工具链） | **P1**（违反"Router 只路由/Agent 拥有工作流"的目标分层；今天无 Router 所以未"越权"，但该 prompt 就是未来的越权温床） | 28.A/B 拆解 |
| workflow 归属悬空：图属于 YAML/编排器，不属于任何注册 Agent | insurance-analysis.yaml:26；registry 无 workflow 字段 | P1 | 28.A（registry 契约） |
| （无 Router 存在，故"Router 含业务逻辑"今天未发生——正向基线） | grep 全库无 router 组件 | — 基线 | 28.A 保持为零 |

### 3.4 Knowledge drift（最严重类）

| 漂移 | 证据 | 级别 | 归属 |
|---|---|---|---|
| **LLM 可在无证据时输出保险知识答案（结构性）**：证据从不进入 LLM 上下文，工具只回 "N items stored"+artifact_id；答案文本零代码门禁，仅 prompt 自律 | tools.py:402-404; agent.py:232-237, 96-100; 工具描述还承诺返回 chunk 而实现不返回（schemas.py:163-165） | **P0**（直接违反"保险事实必须 grounded"；28.0 §7 判定为结构性缺陷） | 28.C（AnswerContext+引用闭环门） |
| 产品事实问答结构性不可答：check_catalog_product 只回 id/名称/公司，不回任何事实；等待期/免责/健康告知数据与 schema 双缺 | tools.py:420-422; catalog schema additionalProperties:false | **P0**（真实产品问答被阻塞；F27-02 延续） | 28.C/目录专项 |
| 治理网关 LLMGateway（ADR-011, Phase 23）未接线，Agent 路径 model.py 直连 | runtime/llm/gateway.py:78 仅测试引用 | P1 | 独立偿债 |
| agent 侧 lexical 重排丢弃 WeKnora 语义质量（dense 禁用） | engine.py:80-104 | P2 | 决策项 |

### 3.5 Developer Space drift

| 漂移 | 证据 | 级别 | 归属 |
|---|---|---|---|
| 无身份/门禁：Dashboard/Review/Developer 与 Chat 平铺同一 shell | App.tsx | **P1** | 28.G |
| 开发者标记泄漏到用户面：chat ArtifactCard 露 `artifactType · run {id}`；dashboard 原始枚举大字卡；GAP 注记上脸 | 27.8 §1.3 清单 | P1 | 28.G（承 27.8 L1-L4） |
| 内部 API 缺口文案直接面向终端用户 | DecisionPanel/FeedbackPanel 注记 | P2 | 27.8 原则 6 |

### 3.6 汇总

| 级别 | 数量 | 项 |
|---|---|---|
| **P0** | 3 | 多 Agent 层不在生产路径；LLM 无证据输出保险知识（结构性）；产品事实问答不可答（目录数据+schema 双缺） |
| **P1** | 9 | 发起入口错位 / 产物交付 / 回链缺失 / 工具边界不一致 / 存储碎片 / prompt 混层 / workflow 归属悬空 / 网关未接线 / 空间无门禁 / dev 标记泄漏 |
| **P2** | 4 | URL 路由 / demo-agent 双模认知 / lexical 重排 / GAP 文案上脸 |

全部 P0 均已被 28.0 路线图覆盖（28.B/28.C）——**本审计的作用是使其成为
周期复查的漂移基线**（/product-audit 首轮应能复现本表并观察其收敛）。

---

## 4. 结论

1. North Star 成立且与现有资产**不冲突**：确定性内核/eval/治理是 Multi-Agent
   系统的底座而非障碍；漂移集中在身份层（Intent/Router/Registry）与交付层
   （grounding/产物/空间），恰是 28.A→C→B→D→E 要建的。
2. 三项 P0 是未来一切对齐检查的**主哨兵**：任何新代码若加深其中任一项
   （例如再建一个绕过 registry 的执行入口、再开一条 LLM 直答通道），
   /product-audit 应直接判 P0 回归。
3. 本文件为**基线**：后续 /product-audit 与本文件 diff，漂移清单只应收敛
   不应增长。
