# Phase 27.9 — Chat-first Multi-Agent Product Architecture Audit

Date: 2026-09-24 · READ-ONLY audit（禁止修改代码/UI/schema/Agent/Runtime/Router/API，
本阶段零改动）。Evidence base: 3 次全库探索（chat 管线 / agent 架构 / artifact 链路，
全部 file:line）+ live API 实测（backend 127.0.0.1:8000，仅 GET）+ 真实 run 数据
（run_9de5882e / run_84f63c7c / B011 golden case）+ 前序审计（27.7.7 workspace-ia、
27.7.8 review-architecture、27.8 review-center-evolution）。

> **STATUS: Audit + Target Architecture + Roadmap only — STOP after this
> document. 未实施任何修改，等待下一步授权。**

---

## 1. Current Architecture

### 1.1 As-built 总图（全部实证）

```
                      Web UI (web/src/App.tsx:21-23, 4 localStorage 模式, 默认 chat)
                          │  无 URL 路由（27.8 已记录）
      ┌───────────────────┴────────────────────┐
      │ Chat 界面 (ChatLayout.tsx)             │  chatMode 默认 = "agent"
      │                                         │  (ChatLayout.tsx:30-32)
      │  [Mode B · agent, 默认]   [Mode A · demo, 可选]
      │   自由文本                  关键词映射→5个演示case
      │   Composer.tsx:36-43       chatState.ts:22-31 (mapPromptToCase)
      │        │                        │  ※用户文本不发送, 仅 case_id
      ▼        ▼                        ▼
  POST /api/chats/{id}/messages {text}   POST /api/runs {case_id}
  (server.py:975)                       (server.py:874, RunRequest 仅 case_id)
        │                                     │
        ▼                                     ▼
  create_agent_run (server.py:470-514)   _worker → orch.run()
  → _agent_worker 线程 (:516-617)       (server.py:406-416, 纯确定性, 无 LLM)
        │                                     │
        ▼                                     │
  run_agent_turn (runtime/agent/agent.py:36)  │
  单个 LLM Agent, MAX 12 步 (:22)             │
  意图优先 prompt (prompts.py:9-41)           │
  agent_decide: 5 意图枚举 (schemas.py:20-25) │
  10 个工具 (tools.py:491-507) ──┐            │
        │   stage 工具直接调用    │            │
        │   orch._execute_stage  ├────────────┘
        ▼   (tools.py:298)      ▼
     ┌──────────────────────────────┐
     │ 共享执行核心: insurance-analysis.yaml │
     │ 8 阶段 9 技能, CaseState 黑板,       │
     │ eval_engine 门 + repair 环 (≤2次)    │
     │ 数据链 FACT→…→REPORT (yaml:6)        │
     └──────────────────────────────┘
        │
        ├─ 9 类 artifact (JSON 规范信封; contracts/build_contracts.py:29-39)
        │    仅 insurance-report 额外带 rendered_report (Markdown)
        ├─ events → EventBus → SSE /api/runs/{id}/stream (server.py:948)
        │    → chat AgentActivity 实时阶段时间线 (useRunStream.ts:96-137)
        └─ 终态: completed / needs_review / failed

  ══ 与上面完全隔离的第二世界（不在任何产品入口路径上）══
  Harness 层: LongRunningHarness + Agent Registry 4 专家
  (runtime/agents/registry.py:15-121) + MessageBus A2A + 并行调度器
  (harness.py:1128) —— 仅 demos/benchmark (B011 四专家 golden) 与
  审批恢复路径 (server.py:1099-1110) 使用
```

### 1.2 两个"Agent"世界的精确边界

| | 世界一：Chat Agent（Mode B） | 世界二：Specialist 层（Multi-Agent V0.1） |
|---|---|---|
| 代码 | `runtime/agent/`（单数目录） | `runtime/agents/`（复数目录） |
| 形态 | 1 个 LLM Agent，prompt 内意图路由→选**工具** | 4 个专家 persona，task_type→agent **确定性映射**（registry.py:124-128 "NOT LLM-decided"） |
| 入口 | POST /api/chats/{id}/messages（chat UI 默认） | demos / benchmark / 审批恢复；`/api/runs` worker 直调 `orch.run()` 绕过它（server.py:409） |
| 工具边界 | 全局 10 工具，每轮全量提供（agent.py:49-52） | 按 agent 裁剪（executor.py:89-96）+ TOOL_NOT_AUTHORIZED（:158-168） |
| 通信 | 不上 MessageBus（tools.py:463-465 无 project_dir 即失败） | MessageBus 5 类消息（message_bus.py:30-36）但"NEVER starts an agent"（handoff.py:7） |
| LLM | live glm（.env，OpenAICompatProvider model.py:104；未配→503 fail-closed server.py:1163-1170） | 同一 provider 默认 live（executor.py:51-55），但所有 demo/benchmark 注入剧本假件（evals/benchmark/runner.py:51-55） |

---

## 2. Product Position Analysis

**目标产品**：Chat-first 多 Agent 保险智能助手（自然语言 → 意图识别 → 路由 →
Agent 工作流 → 过程可见 → 文本/HTML/PDF 产物返回）。

**当前产品实际是什么**：一个**治理优先的确定性保险规划管线**（Mode A：
case_id → 8 阶段 → 9 artifact → eval/repair 门 → 审批/升级），外加一个
**真正的单 Agent 对话入口**（Mode B：默认开启、意图优先、可调用全部阶段工具、
跨轮记忆 ~8 轮 server.py:544-557），以及一套**只在 demo/benchmark 里运行的
4 专家多 Agent 层**。

**Q1 判定：表面 Chat-first，实质是 "Chat-first 壳 + 双世界运行时"。**

- ✅ Chat 是默认一级体验：App 默认 mode=chat（App.tsx:21-23），chat 默认
  chatMode=agent（ChatLayout.tsx:30-32），自由文本直达真实 LLM Agent。
- ✅ 过程可见：AgentActivity 由 SSE 事件流 100% 驱动（无硬编码进度）。
- ❌ 但三个"实质"未达成：**(a) 意图识别只存在于单 Agent 的 prompt 内部**，
  不是独立契约/路由器；**(b) "多 Agent"只在 harness 世界存在**，chat 世界
  与它永不相遇；**(c) 产物返回不完整**——chat 只露最终报告（Markdown 弹窗），
  无 HTML/PDF/下载/深链；review 升级结果在 chat 内不可见。

**Q2 判定（对照目标流程图）**：

| 目标环节 | 现状 | 判定 |
|---|---|---|
| User → Chat UI | chat 为默认模式 | ✅ |
| Intent Recognition | prompt 内 5 意图枚举（agent_decide, schemas.py:20-25）；demo 模式=前端 5 路关键词映射（chatState.ts:22-31） | ⚠️ 存在但非独立层，无置信度字段，demo 兜底=静默映射到基准 case（已披露） |
| Router 分发 Agent | **不存在**。单 Agent 选工具；4 专家为确定性 task_type 映射且不在产品路径 | ❌ |
| QA Agent | 不存在独立 QA Agent——QA 是 chat Agent 的意图分支（GENERAL_KNOWLEDGE/GUIDANCE/PRODUCT_LOOKUP, prompts.py:14-41） | ❌（以意图分支形态覆盖） |
| Insurance Planning Agent | 规划=共享管线（chat 工具命令式调用 `orch._execute_stage`，或 `/api/runs` 整跑） | ⚠️ 有管线无"被路由的 Agent" |
| Workflow 执行 | 8 阶段 9 技能 YAML 单图，eval+repair 门 | ✅ |
| 用户看到执行状态 | SSE 阶段时间线（AgentActivity.tsx:55-86） | ✅ |
| 返回文本/HTML/PDF 产物 | 文本✅；Markdown 报告弹窗✅；HTML❌（仅 tmp 一次性脚本）；PDF❌（全库 0 命中）；下载/导出❌ | ⚠️ |

---

## 3. Chat-first Gap Analysis

| # | Gap | 证据 | 级别 |
|---|---|---|---|
| G-279-01 | **双世界割裂**：chat Agent 与 specialist/harness 层互不触碰（chat 不上 MessageBus tools.py:463-465；`/api/runs` 直调 orch.run 绕过专家 server.py:409） | 架构级 | P0 |
| G-279-02 | **无独立 Intent 层**：意图=单 Agent prompt 内部枚举，无 intent schema 契约、无置信度、无确定性预路由、无 fallback 策略契约 | prompts.py:9-41 | P0 |
| G-279-03 | demo 模式关键词映射削弱自然语言入口（5 case，默认落基准 case；披露在欢迎页/Composer 但属语义静默兜底） | chatState.ts:22-31 | P1 |
| G-279-04 | **无 QA 运行类**：33 个 case 全部是规划类目（complete/insufficient_information/conflicting/low_risk/high_risk/no_candidates/insufficient_evidence/adversarial/repairable），QA 只能作为 chat 意图分支发生，无独立 run/产物形态 | /api/cases 实测 | P1 |
| G-279-05 | **产物交付碎片化**：仅 insurance-report 进 chat；无 HTML/PDF/导出端点（全库无 Content-Disposition/FileResponse 下载路由）；同一 rendered_report 在 4 处重复取数渲染（ArtifactCard / Conversation.ReportBlock / ArtifactInspector / ReviewWorkspace）；无 artifact 深链 | server.py:915-930; ArtifactCard.tsx:64-67 | P0 |
| G-279-06 | 无 URL 路由（承 27.8 Phase A）：案例/run/产物不可寻址不可分享 | App.tsx | P1 |
| G-279-07 | **review/升级结果在 chat 不可见**：needs_review 的 run 在 chat 里只落到终态文案，人工审批/Review Card 闭环发生在另一个 mode | chatState.ts:207-218 | P1 |
| G-279-08 | 无身份/角色边界：Developer 控制台（唯一能按 case 发起 run 的地方）对所有人可见 | App.tsx 4 模式平铺 | P1 |
| G-279-09 | web 事件契约只声明 22/~40 类型：planner/multi-agent/approval/handoff 事件后端有词表、前端未声明 → harness 驱动的 run 无法被完整可视化 | runtime.ts:22-44 vs events.py:27-64 | P2 |
| G-279-10 | Phase-23 治理 LLMGateway（runtime/llm/gateway.py:78 "single governed path"）**未接线**：实际路径走 model.py OpenAICompatProvider | 仅测试引用 | P2（治理债） |
| G-279-11 | 无数字进度：事件无百分比字段（阶段原子粒度，UI 可从 stage_order 推导但未做） | events.py FIELDS | P2 |
| G-279-12 | chat 会话仅内存（ChatManager runtime/agent/chats.py:19-30）：重启即失，跨轮记忆依赖同进程；前端以 localStorage 续 runId | server.py:963 | P2 |

---

## 4. Intent Router Audit

### 4.1 现状：`User Message → ?` 的两个真实答案

**Agent 模式（默认）——意图存在于 Agent 肚子里：**

```
User Message (text)
  → POST /api/chats/{id}/messages (server.py:975)
  → _start_agent_turn: 数据政策门(451)/空文本(422)/provider 未配(503 fail-closed)/
    chat 忙(409)  (server.py:1149-1175)
  → run_agent_turn: system prompt 第一步=意图分类 (prompts.py:9-12)
  → agent_decide 工具: intent ∈ {GENERAL_KNOWLEDGE, GENERAL_GUIDANCE,
    CLIENT_ADVISORY, PRODUCT_LOOKUP, TASK_EXECUTION} (schemas.py:20-25)
  → 首个决策记为 state.intent (agent.py:106-110) → 事件与 AgentOutcome
  → 按意图选「工具」(非 Agent): QA 意图→knowledge_search; TASK_EXECUTION→
    阶段工具 (orch._execute_stage, tools.py:298)
```

**Demo 模式——意图是前端关键词表：**

```
User Message (text)
  → mapPromptToCase (chatState.ts:22-31): 意外/磕碰/摔→单意外case;
    医疗…→单医疗case; 高风险/体检/结节/血压→高风险case; 证据/知识库→失败演示case;
    其余(含一切长尾)→基准家庭case
  → POST /api/runs {case_id}  ※文本本身从不发送
```

### 4.2 与目标的差距

目标：`text → Intent Classification {intent, confidence} → Router → Agent`。

| 目标组件 | 现状 | 缺失 |
|---|---|---|
| intent schema（一等契约） | ❌（枚举藏在 agent_decide 工具参数里） | 独立 intent-result 契约（intent/confidence/evidence/fallback_reason） |
| intent classifier | ⚠️ LLM prompt 内分类（无独立可测单元）+ 前端关键词表 | 可独立测试的确定性预路由（规则优先），LLM 仅辅助（承 ADR-004 确定性精神） |
| router | ❌（无任何 intent→agent 分发表；grep 全库仅错误分类/队列分类同名词） | 路由决策落事件流（可审计） |
| fallback 机制 | ⚠️ demo 静默落基准 case（已披露）；agent 模式 ask_user | 明确的 fallback 契约：低置信→追问（ask_user），绝不静默替换语义 |

---

## 5. Agent Architecture Audit

### 5.1 Agent 清单（§五 表）

| Agent | 是否存在 | 入口 | 输入 | 输出 |
|---|---|---|---|---|
| Chat Agent（单体，意图路由） | ✅ | POST /api/chats/{id}/messages → run_agent_turn (agent.py:36) | 用户文本 + 聊天历史（~8 轮回放 server.py:544-557） | AgentOutcome（ask_user/finish）+ 经工具产出的 artifacts |
| insurance_analyst（客户/需求/风险/缺口/方案） | ✅ registry.py:16-49 | Harness.run→executor (harness.py:756-780) | task + CaseState 快照 | client-profile / requirement-analysis / risk-assessment / coverage-gap-analysis / solution-plan |
| knowledge_specialist | ✅ registry.py:50-71 | 同上（task_type=knowledge_search） | solution-plan | knowledge-evidence |
| product_specialist | ✅ registry.py:72-99 | 同上（product_candidates, recommendation） | gaps/solution/evidence | product-candidates、product-recommendation |
| report_specialist | ✅ registry.py:100-121 | 同上（report_generation） | 上游 artifacts | insurance-report |
| Question Answer Agent（独立 QA） | ❌ | —（QA=chat 意图分支 + knowledge_search 工具） | — | — |
| Customer Analysis Agent（独立） | ❌（=analyst 的 task 集合/管线阶段） | — | — | — |
| Report Generation Agent（独立） | ❌（=report_specialist 仅 harness 路径 / chat 的 report_generation 工具） | — | — | — |
| LLM Planner | ✅ planner.py:41 | Harness replan / demo 脚本 | 用户请求 | TaskGraph（仅 9 种固定 task_type, planner/schemas.py:14-16） |
| 确定性管线（无 LLM） | ✅ | POST /api/runs (server.py:874) | case_id（demo 种子） | 9 类 artifacts + report |
| 队列 worker（"agent-run"） | 代码✅ 生产路径❌（仅测试调用） | TaskQueueStore.enqueue→AgentTaskWorker | 队列 task | case run settle（run_control.py:117 单一 task_type） |

### 5.2 隔离矩阵（§八）

| 隔离维度 | specialist 层 | chat Agent |
|---|---|---|
| system prompt | ✅ 每 agent 独立（registry.py 各条目；executor.py:113 使用） | ✅ prompts.py:9 |
| skills/工具集 | ✅ allowed_tools 裁剪（executor.py:89-96）+ 越权拒绝（:158-168） | ❌ 全局 10 工具每轮全量（agent.py:49-52） |
| workflow | ❌ 共享同一张 8 阶段线性图（insurance-analysis.yaml:26；executor.py:83-84 经 planner registry） | ❌ 无自己的图——命令式驱动共享图 |
| 输出 schema | ✅ expected_artifacts 契约校验（executor.py:82, 212-219；contracts/*.schema.json；例外：product-candidates 无契约，yaml:89 "deliberate debt"） | ✅ 工具内 `_validate_contract`（tools.py:129） |

### 5.3 通信矩阵（§八）

| 模式 | 支持 | 证据 |
|---|---|---|
| sequential | ✅ DAG 依赖顺序执行（harness.py:1128 `_run_parallel`，max_concurrency 默认 1=串行 :357/391） | |
| shared context | ✅ CaseState artifacts 黑板；stage consumes/produces 声明（yaml）；orchestrator.build_stage_input (orchestrator.py:109) | |
| handoff | ⚠️ 有形无神：MessageBus 5 类消息（TASK_HANDOFF 等，message_bus.py:30-36），但"transport only — NEVER starts an agent"（handoff.py:7），发送不触发执行（tools.py:434-436），harness 调度后才消费确认（harness.py:574/845/879） | |
| agent→agent LLM 对话 | ❌ 消息只引用 artifact_id（message_bus.py:9）；chat Agent 完全不参与总线（tools.py:463-465） | |

**多 Agent 能力实证**：运行时确实能跑多 Agent DAG——B011 四专家 golden
（analyst+knowledge+product+report，8 task 带 dependencies，
evals/benchmark/cases/B011_four_agent_golden.json）由 demos/demo_four_agent.py
一键跑通。但这是 benchmark 世界：产品两条入口路径（/api/runs 直调 orch.run；
chat 单 Agent）都不经过它。

**结论（§八）**：本系统 = **单 Agent 管线 + 确定性 task→专家映射**，不是
intent→Agent 路由的多 Agent 平台。四个专家是"同一张图上的角色分工"，不是
可被路由选择的独立执行体；两个世界（chat vs harness）在代码、工具、通信、
入口上全部 disjoint，统一它们正是本提案的核心工程量。

### 5.4 LLM Provider 现状

- chat 与 specialist 共用 OpenAICompatProvider（model.py:104，httpx 直连
  /chat/completions）；当前 .env 已配置 live glm（/api/agent/config 实测
  `configured:true, provider:glm, model:glm-5.3`）→ **chat 默认模式在本机
  可真实运行**；未配置时 503 fail-closed，绝不静默降级到 demo
  （server.py:1163-1170）。
- 但治理网关 LLMGateway（Phase 23，runtime/llm/gateway.py:78）未接线到任何
  运行路径（仅测试引用）——治理债 G-279-10。
- 所有 demo/benchmark/回归注入剧本 provider（ScriptAgentExecutor/
  TaskScriptProvider, evals/benchmark/runner.py:51-55）→ 确定性可复现，
  与 live 路径物理分离（这是特性也是割裂源）。
- 知识检索默认 mock provider（knowledge/provider/__init__.py:28）。

---

## 6. Workflow Visualization Audit（§六）

### 6.1 事件模型能否驱动 Chat UI？——能，且已经在驱动

事件契约（runtime/events.py）字段：`event_id, run_id, timestamp, event_type,
stage, skill, status, case_id, artifact_id, eval_id, repair_attempt, message,
data`（:73-76）；"METADATA ONLY，不带 artifact 内容"（:9-12）。

chat 路径事件全表（live 实测 run_84f63c7c 直方图）：
run_started/completed · stage_started/completed/failed · eval_started/
passed/failed · repair_started/completed/exhausted · artifact_created ·
checkpoint_created · tool_started/completed · agent_step_started/
agent_decision/agent_step_error · agent_stream_delta（瞬态，不入历史
server.py:559-576）。后端词表另含 planner_*/agent_*/handoff_*/approval_*
约 18 类（events.py:27-64）——仅 harness 路径发射。

### 6.2 现状清单对照（§六 检查项）

| 要求 | 现状 | 证据 |
|---|---|---|
| Agent 名称 | ⚠️ chat 显示"Agent 活动"而非具名 Agent；阶段中文名映射表 stageZh（activity.ts:10-19，如 report-generation→"分析报告"） | AgentActivity.tsx:25-30 |
| 当前 Skill | ✅ stage+skill 字段逐事件携带；工具→阶段映射高亮 TOOL_TO_STAGE（runReducer.ts:86-97）；当前工具中文 zhTool（activity.ts:84-98） | |
| 当前阶段 | ✅ 服务端 run.current_stage（server.py:252-256 每阶段更新）+ 前端 ordinal 阶段表 | |
| execution timeline | ✅ SSE 实时 + 断线游标恢复（?after_event_id/Last-Event-ID, server.py:952-953）+ 重启后确定性重放（:901-913） | |
| progress（✓✓●○ 式） | ✅ 形态已达成：stage_order 序数状态表（✓完成/●进行/待办）+ 修复徽章（"修复 {n}"）+ 事件计数 + 质量校验 X/Y + 实时 LLM 流（StreamPanel 思考中/正在输出） | AgentActivity.tsx:55-86,116-140 |
| 数字百分比 | ❌ 无字段也无人推导（可由 stage_order 客户端推导，Phase C 项） | |

**判定**：规格书里的目标体验（✓分析家庭情况 ●计算风险覆盖 ○生成方案报告）
**今天已经存在**于 chat 的 AgentActivity——且是事件驱动非硬编码
（runReducer TRANSITIONS 显式状态机 :121-228，"表外事件不得变更管线状态"）。
缺口是覆盖面而非机制：①web 契约仅 22 类（harness 事件不可视化，G-279-09）；
②agent 模式循环事件仅时间线不进状态机（runReducer.ts:145-148）；③无百分比；
④stage_completed 只带 artifact_id 不带类型（前端靠 stage_order 约定反查）。

---

## 7. Artifact Delivery Audit（§七）

### 7.1 现状链路

```
Agent/阶段 → artifact（9 类, JSON 规范信封: artifact_type/skill/legacy_skill/
  schema_version/generated_at/payload/provenance）
  → 注册表 lineage（artifact_registry.py:46-78, ART-NNN, content_ref,
    input_artifacts, evidence_refs）
  → GET /api/runs/{id}/artifacts（元数据）/ …/{type}（全文, application/json）
     (server.py:915-930)  ← 唯一交付通道, 无下载/导出/深链端点
  → 4 个互不复用的前端表面各自取数渲染:
     chat ArtifactCard 弹窗 / 主视图 ReportBlock / Developer ArtifactInspector
     (JSON+lineage) / Review Workspace 交付物区
```

### 7.2 格式盘点

| 类型 | 格式 | 备注 |
|---|---|---|
| insurance-report（最终报告） | JSON（structured_report 14 节）+ **Markdown**（rendered_report，模板渲染，report_generation_engine.py:735-933，"No LLM: pure template"） | 唯一有人类可读格式的 artifact |
| 其余 8 类（client-profile … product-recommendation、knowledge-*） | 仅 JSON | 结构化，无渲染版 |
| HTML | ❌ 无（仅 tmp/build_family_report.py 一次性演示脚本，未接线） | |
| PDF | ❌ 全库 0 命中（无 weasyprint/wkhtmltopdf/print 管线） | |
| 下载/导出 | ❌ 无任何 Content-Disposition/FileResponse 路由 | |

chat 内产物发现是**约定式**：终态事件时从 run.stage_order 找
report-generation 阶段的 produces 字段（ChatLayout.tsx:71-74）→ 只展示最终
报告一张卡（ArtifactCard，含内部标识 `artifactType · run {id}` 泄漏，27.8
已记）；中间 8 类产物只在 Developer/Review 表面可见。前端渲染用自研安全
Markdown 组件（Markdown.tsx:9-12，"never dangerouslySetInnerHTML"），无
markdown 依赖库——安全但能力有上限（无导出/打印）。

**判定（§七）**：`Agent → Artifact → ???` 的 ??? = 一个 JSON GET 端点 + 四处
重复的前端取数。距离目标（文字 + 附件 PDF + 查看 HTML）缺：统一渲染表面、
导出端点（.md 先行）、HTML 渲染（或浏览器打印）、artifact 深链、chat 内
多产物清单。

---

## 8. Developer/User Boundary（§九）

### 8.1 功能权限表

| 功能 | 当前入口 | 目标权限 |
|---|---|---|
| Chat（对话/过程/报告） | 顶栏"对话"（默认 mode） | **User**（所有人） |
| Dashboard | 顶栏"Dashboard" | **Operator/Developer**（运营） |
| Review Queue / Approval / Review Workspace | 顶栏"审核队列"三级状态链 | **Operator**（保险审核员；27.8 的 Escalation 收件箱） |
| Evaluation（离线套件） | 无 UI（命令行 evals/） | Developer（保持无 UI 可） |
| Trace / Run Detail | Developer 检查器 + Review 折叠区 | Developer（L4 审计） |
| Supervisor | 无页面（alerts 端点存在，0 条实测） | Operator/Developer |
| Developer Mode（唯一按 case 发起 run 处） | 顶栏"Developer" | **Developer** |
| Artifact Viewer | Developer/Review 钻取 | Developer + User 的"查看详情"降级版 |

### 8.2 页面定位表（§四，含"是否应该普通用户可见"）

| 页面 | 当前定位 | 目标用户 | 普通用户可见？ | 调整建议 |
|---|---|---|---|---|
| Chat UI | 默认一级体验（agent 默认/demo 可选） | 终端客户/顾问 | ✅ 应该，且应成为**唯一业务入口** | 意图结果透明化（"识别为：方案执行"）；run 的全部产物进 chat；review 升级状态回链 Review Center；demo 模式降为"示例"开关 |
| Review Workspace | 人类可读决策工作台（27.7.7 九区） | 审核员 | ❌ | 并入 Operator Space 的 Review Center（27.8 提案） |
| Dashboard | 只读运营总览 | 试点运营 | ❌ | Operator Space；状态卡→可点链接（27.8 §6） |
| Review Queue | 审批+卡片列表（须手输 project_id） | 审核员 | ❌ | Escalation 收件箱（27.8） |
| Approval Detail | 记录视图跳板 | 审核员/审计 | ❌ | 降为决定记录 tab（27.8） |
| Developer Mode | 案例·运行控制台（唯一 POST /api/runs 面板） | 工程师 | ❌（当前实际人人可见） | Developer Space 门禁（Phase E） |
| Supervisor | 不存在（数据有类型无页面） | 运营/工程 | ❌ | 并入 Review Center 技术详情（27.8 §4） |
| Artifact Viewer | JSON 钻取/lineage | 工程/审计 | ⚠️ 仅"查看报告详情"降级版 | L4 保留；User 侧仅报告渲染视图 |

**Chat UI 是否应该成为唯一业务入口？——是（方向性结论），且它已具备五项
能力中的四项半**：

| 能力 | 判定 | 证据 |
|---|---|---|
| 创建任务 | ✅ 两模式皆可（demo: case→POST /api/runs；agent: 文本→create_agent_run） | ChatLayout.tsx:117-135 |
| 展示 Agent 状态 | ✅ SSE 全量驱动，无假进度 | AgentActivity.tsx:13-103 |
| 展示 workflow | ✅ 阶段表+工具映射+修复徽章+LLM 流 | AgentActivity.tsx:55-86 |
| 展示 artifact | ⚠️ 仅最终报告 Markdown 弹窗；无中间产物/下载/深链 | ArtifactCard.tsx:32-67 |
| 继续追问 | ⚠️ agent 模式✅（跨轮记忆+TASK_EXECUTION"根据我刚才提供的信息生成报告" prompts.py:39-40；一 chat 一 run 并发锁 409）；demo 模式❌（每次重新映射，runId 重置 chatState.ts:139-146） | |

不迁入 chat 的：治理动作（审批/反馈/质量台）——属 Operator Space，chat 只
需**回链**（"该方案已进入人工复审 → 查看"），不内嵌决策 UI（ADR-017 精神）。

---

## 9. Target Architecture

### 9.1 信息架构（§十）

```
Application
├─ User Space（默认, URL /…）
│   └─ Chat（唯一业务入口）
│       ├─ Conversation（多轮, 服务端持久化目标态）
│       ├─ Agent Timeline（现有 AgentActivity 演进: 意图→路由→阶段/工具/修复）
│       └─ Artifacts（全部 9 类业务视图 + 报告渲染 + 导出 md/打印 PDF + 深链）
└─ Operator / Developer Space（门禁, URL 隔离）
    ├─ Review Center（27.8 五区提案: 收件箱/Case Overview/AI Review/
    │   Escalation/Decision/Feedback）
    ├─ Dashboard（运营）
    ├─ Evaluation（离线, 无 UI）
    ├─ Trace / Run Detail（L4 审计, Developer）
    └─ Runtime / Developer 控制台（案例·发起·检查器）
```

### 9.2 目标数据流（§十一）

```
User Message
  → Conversation Service（chat 持久化: 现为内存 ChatManager, 目标态 PG）
  → Intent Layer（新增, 确定性优先: 规则预路由 + LLM 辅助分类[advisory];
     intent-result 契约 {intent, confidence, evidence, fallback_reason};
     决策落事件流可审计; 低置信→ask_user, 绝不静默换义）
  → Router（确定性分发表: intent→执行世界）
     ├─ QA 意图 → Chat Agent 直答（knowledge_search 引证）→ 文本回复
     └─ 规划/执行意图 → 统一执行核心（现有 insurance-analysis 图 + eval/repair 门;
        specialist 层可选启用, 与 /api/runs 同一世界——消灭双世界割裂）
  → Events Stream（现有 EventBus/SSE 不变; 契约补全 22→全量）
  → Chat UI（Agent Timeline 实时呈现 + 意图/路由透明）
  Artifact Store（现有注册表/lineage 不变）
  → Artifact Renderer（统一一个表面: 业务视图+报告渲染+导出）
  → Chat Response（文字 + 产物卡[md 渲染/导出 .md/浏览器打印 PDF] + 深链）
```

### 9.3 设计约束（承既有 ADR，不推翻）

- **确定性优先（ADR-004 精神）**：Intent Layer 的路由决策必须确定性可测
  （规则优先、LLM 仅辅助与建议），决策记录为事件；LLM 永不翻转 eval 门。
- **治理不动（ADR-017）**：chat 只回链 Review Center，不内嵌审批控制。
- **反馈=证据（ADR-018）**：chat 内反馈采集同样只作证据。
- **统一写入路径**：chat 的 TASK_EXECUTION 与 /api/runs 必须收敛到同一执行
  核心与同一 artifact 写入路径（现状已共享 _execute_stage，需正式化为契约
  而非实现巧合）。
- 新增 Intent Layer 与（可选）specialist 上产品路径 → **需要新 ADR**（本
  阶段不写，留待授权）。

---

## 10. Migration Roadmap（§十四）

> 与 27.8 Roadmap（review/人机协同轨）互补而非替代：27.9-A ⊇ 27.8-A（URL
> 路由/信息层级共享）；27.9-E 与 27.8-B 同属空间拆分，可合并执行。排序由
> 用户决定。

| | **Phase A** Chat-first Foundation | **Phase B** Intent Router + Agent Registry | **Phase C** Workflow Visualization | **Phase D** Artifact Experience | **Phase E** Console Separation |
|---|---|---|---|---|---|
| 目标 | Chat 成为唯一业务入口的地基 | 意图层与路由成为一等契约；消灭双世界割裂 | 过程可见全覆盖 | 产物交付完整（目标形态） | 用户/运营/开发空间隔离 |
| frontend | URL 路由骨架（承 27.8-A）；chat 内：run 全产物清单区、review 状态回链卡、demo 模式降为"示例"开关；L1-L4/空态标准落地 | 意图透明 chip（"识别为：方案执行·置信度"）；fallback 追问 UI（ask_user 已有） | web 事件契约 22→全量；%进度（stage_order 推导+agent 步数/12）；阶段时长/产物 chip；agent 循环事件入时间线 | 统一 ArtifactViewer（收编 4 处重复渲染）；导出按钮；报告打印样式 | 空间拆分+导航门禁+角色切换（无真实 auth 前为显式开关） |
| backend | 无（现有端点足够） | intent-result 契约+确定性预路由（规则优先, LLM advisory）；路由决策事件化；chat→执行核心正式化（单写入路径文档化+断言） | 无（事件已足）；可选 stage_completed 附 artifact_type | 导出端点 `GET …/artifacts/{type}?format=md`（Content-Disposition）；HTML=确定性模板复用报告引擎 | 身份 who-am-I（承 27.8 §8 缺口）；角色头 |
| schema | 无 | intent-result schema（新）；agent registry 升为产品契约（含 product-candidates 补契约=还 yaml:89 旧债） | 无（或事件字段增量） | 无（rendered_report 已有；html_render 可选增量） | 无 |
| runtime | 无 | specialist 层可选接线到统一执行核心（开关默认关，行为等价）；**需新 ADR** | 无 | 无 | 无 |
| tests | vitest：URL 恢复/产物清单/回链卡；后端零改动回归 | 意图路由金标单测；registry 契约测试；chat↔管线单写入路径 e2e | reducer 新事件类型；SSE 重放 | 导出 content-type/disposition；渲染统一 vitest | 角色门禁 vitest；身份端点测试 |
| 前置 | 无 | A（URL/结构先定）；新 ADR | A | A（深链依赖 URL） | A；与 27.8-B 协调 |

依赖：A → (B、C、D 可并行) → E；B 是架构关键路径（双世界统一 + 新 ADR）。
每阶段维持 STOP-and-wait 授权节奏。

### 真实 Run 验证（§十二）

| Run 类 | 实例 | 从 Chat 进入 | 分发 Agent | 展示过程 | 返回产物 | 判定 |
|---|---|---|---|---|---|---|
| 普通问答 | **不存在该 run 类**（33 case 全规划类目；QA=chat 意图分支） | 代码级✅（agent 模式 QA 意图→直答）；live agent-run 实证缺失（chat 仅内存+bus runs:0 重启后；本阶段禁 POST） | n/a | n/a | n/a | ❌ 类缺失（G-279-04） |
| 保险方案 | run_9de5882e（50 事件/9 artifacts/lineage 完整/restored） | ✅ demo 映射 bm-complete-001 族已验证；agent 模式 TASK_EXECUTION 同图 | ⚠️ 无路由——直入共享管线 | ✅ 阶段时间线全量 | ✅ 报告卡（仅最终报告） | 通（无路由语义） |
| report 生成 | 非独立 run 类——report-generation 为规划 run 第 8 阶段（ART-009 insurance-report, JSON+MD 实测） | 同上 | 同上 | ✅ 阶段可见 | ✅ Markdown 弹窗；❌ 导出/PDF | 通（形态为阶段产物） |
| review 失败 | run_84f63c7c（needs_review；eval_failed×3、repair×2+exhausted 实测直方图） | ✅ demo 映射 bm-noev-001（"证据不足(失败演示)"case） | 同上 | ✅ 失败/修复过程全在事件流 | ⚠️ chat 只落终态文案；升级闭环在 review mode（G-279-07） | 通但断在 chat 语义 |

---

## STOP

本阶段完成：Audit（Q1/Q2 + §四~§十二 全部交付项）+ Target Architecture
（§9）+ Migration Roadmap（§10，Phase A-E）。未修改任何代码/UI/schema/
Agent/Runtime/Router/API。等待下一步授权（实施顺序：27.9-A/B/C/D/E 与
27.8-A..D、27.7.8-R1 的合并排序由用户决定）。
