# Phase 28.E-0 — Consumer Surface Design & Boundary Audit 报告

Date: 2026-09-26 · 性质：**READ-ONLY AUDIT + DESIGN**（Zero Product Code
Change；工作树与 M5-C.2 完全一致，PRE_EXISTING_CHANGES=YES=既有
M 系列 span，未触碰）。

## 1. Executive Summary

- **判定：`B — REFACTOR_EXISTING_SURFACE`**。现状不是"差几个开关"
  （A 不成立——信息架构以 Runtime 执行为中心），也不必从零建（C 过
  重）——chat 中列（会话流/输入/活动卡/产物卡）+ `activity.ts` 用户
  中文映射层 + SSE 续传 hook + 单一 API client 是**真实可复用基础**；
  需要的是明显的 UI 重构：空间隔离、消费者 IA、终态呈现层、模板
  缺陷修复、demo 二元性移出用户路径。
- 后端**授权机制存在**（runtime/auth.py，Phase 13 R-06：API key +
  OWNER/REVIEWER/OPERATOR + 端点角色声明 + CORS 白名单），当前灰度
  未配置（dev loopback）→ **AUTHORIZATION_GAP = 部署状态**；且角色
  模型**无 CONSUMER 档**（Owner 决策项）。
- 全部设计基于现有 Runtime/Event/Artifact 契约——零新 Runtime、零
  新事件/产物类型、零后端改动即可实现 E-1..E-7 的绝大部分。

## 2. Current UI Inventory（源码级调用链）

```text
App.tsx（单壳 4 mode，React state + localStorage["webui:mode"]，无 URL 路由）
├─ chat      → ChatLayout
│   ├─ ChatSidebar（会话列表=localStorage chats v1 信封 + demo 种子）
│   ├─ Conversation（Welcome / Message[user|assistant] / AgentActivity
│   │               / ArtifactCard / 冲突横幅[含 Run: id] / stream-error）
│   ├─ Composer（Agent|演示 Demo 切换；demo 分支=mapPromptToCase
│   │           关键词映射 + bm-* 下拉；agent 分支=原样文本）
│   ├─ AgentActivity（activity.ts 中文阶段名 + 8 阶段清单 +
│   │               "Portfolio Demo Mode · {caseId}" 标签[无条件]）
│   └─ AgentInspectorPanel（xl+ 默认渲染；= RuntimeInspector，与
│       Developer Mode 同组件：Run 元数据[run_id/case_id 行] /
│       Pipeline / Eval / Trace[原始事件名]）
├─ review    → ReviewQueue / ApprovalDetail / ReviewWorkspace
│              （27.5-27.7.7 治理面；approvals API；viewModel 适配层）
├─ dashboard → PilotDashboard（只读快照/近期/快捷入口）
└─ developer → DeveloperMode（Phase-2 cases/runtime 控制台）

API（web/src/api/client.ts，组件零直接 fetch）：
  /api/health · /api/cases · /api/agent/config
  /api/chats[POST] · /api/chats/{id}[GET] · /api/chats/{id}/messages[POST]
  /api/runs[POST] · /api/runs/{id} · /events[?after_event_id] ·
  /artifacts[.ts] · /review-card · /stream（SSE，Last-Event-ID 续传）
  /api/projects/{id}/approvals|supervisor · /api/approvals/{id}[|approve|reject]

事件流：useRunStream——SSE + 游标续传；live/replay 同 reducer
（刷新重建一致状态；stop=仅断开视图，无假取消）✓ 消费者级质量。
```

## 3. Current Surface Map

| Surface | Route | Entry | Current User | Internal Data | Intended Space |
|---|---|---|---|---|---|
| Chat（对话 tab） | 无 URL（state） | 顶栏恒可见 | 所有人（无门控） | 内嵌 Inspector/事件名/demo 标签 | **Consumer（目标）** |
| Runtime Inspector | 无 | chat 面 xl+ 默认 + Developer 面 | 所有人 | run_id/case_id/Pipeline/Eval/Trace | Developer |
| Dashboard | 无 | 顶栏恒可见 | 所有人 | 运行快照/系统状态 | Developer/Operator |
| Review（队列/审批/工作台） | 无 | 顶栏恒可见 | 所有人 | approval_id/run_id/risk | Operator |
| Trace / Eval / Run Detail | 无 | Inspector/Developer 内嵌 | 所有人 | 原始事件/eval 结论 | Developer |
| Demo 模式（POST /api/runs） | 无 | chat 头部切换恒可见 | 所有人 | bm-* case、前端关键词路由 | Developer（演示） |

## 4. Consumer / Operator / Developer 边界（现状）

**现状：边界不存在**——四入口单壳无条件渲染；chat 面无条件内嵌
Developer 同款 Inspector；无 URL 路由（无 deep link，也无 route
guard 概念）；后端角色机制在位但未配置（dev loopback），且角色集
（OWNER/REVIEWER/OPERATOR）无消费者档。

## 5. Current Consumer Surface Finding

```text
判定 = B — REFACTOR_EXISTING_SURFACE
（M5-C.2 的 USER_SPACE_EXISTS=NO 指"无可分离产品面"——本节按 §25
口径评估改造路径：chat 核心可复用，IA/边界/终态需重构）
```

可复用基础（实测+源码）：中列会话流（自然语言交付已实测：拒答/
澄清/进度/产物卡）· Composer agent 分支（纯后端路由）·
useRunStream（SSE 续传）· **activity.ts（既存用户侧映射层）** ·
chatState 服务端会话绑定（serverChatId）· ArtifactCard+ReportModal
（Markdown 渲染）· api client 单一出口。

必须重构：壳与导航（空间隔离）· Inspector 内嵌 · demo 二元性 ·
QA 终态罐头模板 · 卡片/横幅 ID 泄漏 · "分析结束（waiting）"类
内部状态词 · 会话列表持久化形态。

## 6. Current Chat Runtime Path（Agent 模式，实测 M5-C.1）

```text
Composer → POST /api/chats/{id}/messages（原样文本）
→ :8000 _agent_worker → intent(rule) → Router(authority) → registry
→ qa/product/planning agent → 既有脊柱 → grounding → 交付
```
无前端路由/无直选 Agent/无第二 Runtime ✓。**违例仅 Demo 分支**
（mapPromptToCase + POST /api/runs legacy 直跑，用户可选可见）。

## 7. Current Internal Data Exposure（§21 Boundary Violation）

前端直接消费内部对象：`types/runtime.ts` 的 `Run`/`RuntimeEvent`
经 runReducer 直达 chat 组件（Inspector/AgentActivity）——
**BOUNDARY VIOLATION（无 Consumer DTO 层）**。最小迁移建议：
新增纯展示映射 `consumerView(state)`（presentation adapter，同
27.7.7 viewModel 模式），chat 面只绑定 consumer 字段。

## 8. Internal-ID Exposure（Observed / Potential / Not present）

| 字段 | 状态 | 证据 |
|---|---|---|
| run_id | **Observed** | RuntimeInspector.tsx:39；ArtifactCard.tsx:29（截断）；Conversation 冲突横幅:51 |
| case_id | **Observed** | RuntimeInspector.tsx:40；demo 下拉/标签（AgentActivity.tsx:99） |
| artifact_type（裸类型名） | **Observed** | ArtifactCard.tsx:28-29、Modal 头:91 |
| raw event_type | **Observed** | Inspector Trace 列表 |
| 内部 status 词（waiting 等） | **Observed** | activity.ts:46 "分析结束（{status}）" |
| eval_id / approval_id / trace_id | **Potential**（review/developer 面 Observed；chat 面未 observed） | ReviewQueue 卡片（Operator 空间合法） |
| agent_id（insurance-planning-agent） | **Not present**（chat 面未见；Developer 面存在） | — |
| tool_name/skill_name | **Not present**（经 zhTool/activityLabel 已中文化） | activity.ts:84-98 |
| provider/model/prompt/stack trace | **Not present**（chat 面） | — |

## 9. QA_REFUSED / Error Exposure

- 后端契约：`qa_answered.grounding_status=refused` +
  `run_completed(status=completed, result_status=QA_REFUSED,
  message=诚实拒答文案)`——**文案本身消费者级**（实测）。
- 前端缺陷（M5-C.1 实测 + 源码）：`ChatLayout.finalizeAgent` 对任何
  `completed` 终态硬编码报告卡标题（:71-93）+ `chatState.ts:210`
  罐头"分析完成。我整理了一份《客户保险需求分析报告》…" →
  **QA_REFUSED 被包装成虚构报告模板 = User-Space contract violation**
  （记录未修）。错误面：503/409/网络各有友好文案 ✓；
  stream-error 直显 error 字符串（需消费者化）。

## 10. Artifact Delivery Audit

1. **类型清单**（9，B4 基线实证）：client-profile ·
   requirement-analysis · risk-assessment · coverage-gap-analysis ·
   solution-plan · product-candidates · product-recommendation ·
   knowledge-evidence · insurance-report。
2. **user-friendly 渲染**：仅 insurance-report（rendered_report →
   Markdown modal）达标；其余无消费者渲染（v1 仅报告需交付）。
3. **insurance-report 交付**：ArtifactCard→Modal→
   GET /artifacts/insurance-report→Markdown ✓（运行时原产物，不重生成）。
4. **卡片泄露**：是（artifact_type + 截断 run_id，§8）。
5. **deep link**：无（modal 局部状态；无 URL）。
6. **export/download**：无（future scope）。
7. **future**：导出/深链/历史产物列表（需 Owner 授权，涉及后端）。

## 11. Agent Activity Audit

`activity.ts` = **既存 Consumer Activity Mapping 雏形**（纯函数可
测试；阶段动词化"正在了解家庭基本情况"；checkpoint 判为噪音隐藏；
tool→中文名）。缺口：`intent_classified`→null（隐藏 ✓ 但缺"正在
理解你的需求…"可选映射）；QA 系事件未映射（`qa_answered`→null；
reserved `grounding_started/completed`→null）；终态映射缺失
（run_completed 的 completed 一律"分析完成"；`分析结束（waiting）`
泄内部词）。**结论：扩展而非新建。**

## 12. Route / Authorization Audit

- **URL/Route：完全不存在**——mode=React state+localStorage；
  无 deep link、无 route guard、"边界"= conditional render。
- **后端授权**：`runtime/auth.py`（Bearer key；OWNER/REVIEWER/
  OPERATOR；approve/reject=REVIEWER，runs/control=OPERATOR；
  production 模式无 key 拒启动；CORS 白名单）。当前 .env 无
  INSURANCE_AGENT_API_KEYS → dev loopback，**未激活**。
- **AUTHORIZATION_GAP = YES（部署态）**+ **无 CONSUMER 角色档**
  （chat 端点未设最低角色——消费者开放前需 Owner 决策：公开 chat
  或新增消费者角色/入口策略）。

## 13. Target Consumer IA（v1）

```text
Consumer（独立空间，任务中心）
├── 会话
│   ├── 会话列表（今天/昨天/更早；标题+摘要；无任何 id）
│   ├── 消息流（用户/助手/产物卡/系统安全状态条）
│   └── 输入区（仅自然语言输入+发送；无模式切换/无 case 选择）
├── 助手进度（当前活动行 + 阶段进度点 + 完成态）
└── 产物交付（报告卡[标题+日期，无类型/id] → 查看[Markdown] →
    （future）导出）
```
不做（§32）：多 Agent 选择、模型/工具选择、debug inspector、
dashboard、社交、workflow designer。

## 14. Target Surface Architecture

```text
                Web App
                   │
      ┌────────────┴────────────┐
 Consumer Space            Internal Space（门控入口+独立路由）
  会话/消息/产物/进度            ┌────────┴────────┐
  consumerView(DTO)            Operator         Developer
  activity mapping(扩展)       Review/Approval   Dashboard/Trace/
  chat state(服务端会话)        Feedback/Escal.   Eval/Inspector/Debug
      │                            │                  │
      └────────────┬───────────────┴──────────────────┘
                   ↓
   Shared（唯一 Runtime）：API(/api/chats·messages·artifacts·stream)
   · SSE 事件脊柱 · Conversation/chat 服务 · Artifact 服务 ·
   Intent/Router/Registry/Agents/Grounding（零改动复用）
```
原则：**UI 面可分离，Runtime 不分裂**；Internal 面可继续共用
Inspector（Developer 资产保留，不删除）。

## 15. Target Runtime Flow

```text
Consumer Message → Conversation(agent 分支原样文本)
→ POST /api/chats/{id}/messages → Intent(rule) → Deterministic Router
→ Agent Registry → Agent → 既有脊柱 → Events(SSE)
→ Consumer Activity Mapping(扩展 activity.ts)
→ Grounding/Artifact → Consumer Delivery(终态映射+报告卡)
```
禁止且不存在：consumer→new runtime；consumer→frontend routing；
consumer→direct agent selection。Demo 模式移出 Consumer 空间
（Developer 保留）。

## 16. Consumer State / Terminal State Matrix（§18/§19）

| Consumer 状态 | 触发（后端既有字段，零契约改动） | 用户文案（示例） |
|---|---|---|
| SUCCESS | run_completed.completed 且 result_status 无拒答语义 | 答案正文/「已为你整理好分析报告」+报告卡 |
| USER_CLARIFICATION | status=waiting / agent_decision.ask_user | 「为了继续帮你规划，我还需要了解：…」（正文即问题） |
| SAFE_REFUSAL | qa_answered.refused（citation/insufficient/catalog_missing）| 「我目前没有足够可靠的依据，先不直接下结论。你可以换一种问法，或提供更多细节。」（正文=后端 message） |
| HUMAN_REVIEW_REQUIRED | needs_review / repair_exhausted | 「这个结果需要人工核实后才能给你，我先为你保留当前进度。」 |
| TEMPORARY_SERVICE_ERROR | llm/provider 失败、timeout、run_failed、SSE error | 「服务暂时不可用，请稍后再试。」+保留草稿 |
| PROVIDER_UNAVAILABLE | 503 agent-unavailable | 「智能服务暂时不可用，请稍后再试。」（去掉"切换演示模式"入口） |

禁止直显：QA_REFUSED/NEEDS_REVIEW/INTERNAL_ERROR/trace_id/原始
异常。实现层=前端 presentation mapping（读 result_status/
grounding_status → 文案），**后端 status 契约零改动**。

## 17. Implementation Plan（建议 E-1..E-7，均需 Owner 逐段授权）

| 阶段 | 内容 | DoD |
|---|---|---|
| E-1 Consumer Shell + 导航边界 | 消费者壳（无内部入口）；Internal 入口独立（路由/门控占位） | 消费者视口零内部入口；internal 面可达但隔离；web 回归+tsc 绿 |
| E-2 会话/消息消费者渲染 | consumerView DTO；QA 终态模板修复（去罐头报告/分析完成）；ID 清除（卡片/横幅）；demo 移出 | 快照/文本断言无 §20 字段；拒答/澄清/答案正确呈现 |
| E-3 Activity Mapping 扩展 | activity.ts 增 QA/grounding/终态映射；去内部状态词 | 单测覆盖新映射；实测四路径文案自然 |
| E-4 Artifact Delivery | 报告卡消费者化（标题+日期）；Modal 消费者头；export=future 明示 | 卡片零类型/id；报告查看不回归 |
| E-5 Safe Terminal States | §16 矩阵全实现 | 六状态各≥1 测试；错误文案无内部词 |
| E-6 Operator/Developer 隔离 | Internal 空间门控（含 auth 消费者档决策落地） | 越权访问测试；AUTHORIZATION_GAP 关闭或 Owner 豁免记录 |
| E-7 Consumer E2E + 回归 | §18/29 矩阵 + 全量回归 | E2E 绿；729/729+web+tsc+B4/M4/M3 绿 |

顺序依赖：E-1→E-2→(E-3,E-4,E-5 可并行)→E-6→E-7。

## 18. Test Strategy

- **Consumer 流**：开应用/新建会话/发送/流式/刷新恢复/历史/报告
  查看/错误/拒答/澄清（每态≥1 用例）。
- **泄漏**：consumer 可见面 DOM 文本断言不含 §20 全字段（含
  insurance-planning-agent/bm-/run_/case_/evt_ 模式 grep）。
- **路由**：consumer 无 Agent/workflow/tool/case 选择器；network
  白名单仅 /api/chats·messages·artifacts·stream。
- **架构**：不出现第二 runtime（无新 origin/端点类）；事件词汇表
  契约测试维持（28.B 双端）。
- **边界（§30）**：consumer→developer/operator 路由访问测试
  （route guard 实装后）；无 authorization 期间标记
  AUTHORIZATION_GAP 用例 skip+记录。

## 19. Risks / Open Questions

1. **AUTHORIZATION_GAP**（部署态）+ 无 CONSUMER 角色——真实用户
   前必须决策（E-6）。
2. **PERSISTENCE_STATUS = 部分**：服务端有 chat 对象（按
   chat_id），但**无用户维度会话列表 API**——会话列表=浏览器
   localStorage（换设备/清缓存即失）。多端/长历史需后端工作
   （新授权，非 E-1..E-7 范围）。
3. 高拒答率（citation model-fit）将主导消费者体验——E-5 只能诚实
   呈现，不能降低拒答（gate 冻结）；缓解依赖 Owner 的 ④ 决策。
4. 冲突横幅/stale-activity 文案需消费者化重写（E-2 内）。
5. SSE stop/resume 语义（仅断开视图）与用户预期（"停止"）差异——
   v1 文案规避"停止"字样。

## 20. Owner Decisions Required

1. 批准 **B 方向 + E-1..E-7 计划**（逐段授权节奏）。
2. 消费者助手身份文案（单一"保险顾问助手" vs 按任务措辞）。
3. Consumer 空间鉴权模型：公开 chat / CONSUMER 角色 / 其他（E-6）。
4. HD-2 weknora 接线（独立于本线，解 M5-C.1 BLOCKED）。
5. 会话持久化后端范围（PERSISTENCE 缺口）与 artifact 导出——
   是否立项（可后置）。

## 21. Scope Confirmation

```text
Business code changes = 0
Runtime changes       = 0
Router changes        = 0
Agent changes         = 0
Contract changes      = 0
Architecture changes  = 0
```
（本阶段产物：本报告 + .agent/memory 簿记；git tracked 集与
M5-C.2 完全一致，已核。）
