# Phase 28.E-2 — Consumer Rendering & View Boundary 报告

Date: 2026-09-26 · 范围：**web/** only。runtime/schema/config/ADR/治理
文档零触碰。核心交付：**ConsumerView allowlist 边界 + 虚构报告卡 P0
修复（Completion ≠ Artifact）**。

## 1. Executive Summary

- 新建 `web/src/state/consumerView.ts` = 消费者渲染的**白名单边界**
  （纯函数；显式字段/字面量/查找表；禁止 spread/delete/JSON 往返——
  内部字段只能通过"在此显式写出"才会到达 DOM，而这里没有）。
- **P0 修复（live 证实）**：finalize 不再由 `completed` 推导报告卡，
  改为 `hasRealArtifact`（同一 run 内存在 report-generation 阶段的
  `artifact_created` 事件）。U4 实测：grounded QA 轮**零报告卡**
  （旧 U3 轮的虚构卡为历史持久化数据，新轮不再产生）。
- 消费者面清除：ArtifactCard 类型/run 行、demo 标签+bm-* id、事件
  计数、未知 stage 原样 id 回退（stageZh 会回显——边界已防御）、
  冲突横幅 Run id、模型 reasoning 流（永不渲染）、Composer
  "Agent Mode · 真实 LLM" 提示。
- 回归：web 175+2 · tsc clean · backend PENDING（预期 729/729）。
  Runtime/Router/Intent/Grounding/契约全部 UNCHANGED。

## 2. Pre-Implementation Audit（E-1 后树一致 ✓）

git：branch main @ 9407a84，E-1 改动集之外无新变化；无 runtime/
authority/contract 变化。渲染链（API/SSE → runReducer/chatState →
ChatLayout → AgentActivity/Message/ArtifactCard）逐文件审计完成。

## 3. Current Consumer Data Path（审计结论）

`SSE(RuntimeEvent[]) → runReducer(RunUiState) → AgentActivity 直渲染`
+ `finalize(ChatLayout) → chatState 消息(user/assistant/activity/artifact)
→ Conversation/MessageView/ArtifactCard`。**边界缺失点**=AgentActivity
直读 RunUiState 文案字段 + ChatLayout 用 stageOrder**猜** artifact。

## 4-6. Consumer View Boundary / View Model / Allowlist

`consumerView.ts`（allowlist 出口，全部纯函数）：
`toArtifactView(type)`（ARTIFACT_VIEWS 白名单：仅 insurance-report →
{title 客户保险需求分析报告, cta 查看完整报告}；未知→null 不渲染）·
`consumerStageLabel(stageId)`（stageZh 映射；未知/回显→「处理中」）·
`hasRealArtifact(state)` · `consumerFinalizeArtifact(state)` ·
`consumerTerminalHeader(status)` · `consumerFallbackText(refusal|error)`
（保守文案，无事实/无原因/无内部词）· `ASSISTANT_NAME=保险顾问助手`
（presentation 常量，非架构常量）。**无任何 Runtime 对象 spread/透传。**

## 7. Forbidden Internal Fields（DoD 全项）

run_id/case_id/artifact_id/eval_id/approval_id/trace_id/event_id/
agent_id/workflow_id/tool_id/skill_id/provider/model/prompt/raw_error/
stack/internal status/internal event type —— **均不进入消费者 DOM**
（DOM 级测试断言，见 §17）。注：runId/artifactType 作为**数据获取键**
仍存在于组件 props（不渲染）——彻底 DTO 化随 E-3 activity 重构完成。

## 8. Internal-ID Leakage Audit（修复清单）

| 泄漏点 | 处置 |
|---|---|
| ArtifactCard `{artifactType} · run {id}` 行 + Modal 头部类型 | **移除**（卡片=白名单 title+cta；Modal 头=consumer title） |
| AgentActivity「Portfolio Demo Mode · {caseId}」 | **移除**（含 caseId prop） |
| AgentActivity「{n} events」计数 | **移除** |
| 未知 stage 回显原始 id（stageZh `?? stage`） | 边界防御：`consumerStageLabel` 回显→「处理中」 |
| 冲突横幅 `Run: {id}` + Developer Mode 提及 | **移除/消费者化** |
| StreamPanel reasoning 思维链文本 | **永不渲染**（仅 content 流） |
| Composer「Agent Mode · 真实 LLM 理解与决策」 | →「由 AI 保险顾问为你分析」 |
| 旧持久化会话中的虚构报告卡消息（U1/U3 历史数据） | 不动用户数据；**新轮不再产生**（记录为已知限制） |

> **修正（2026-09-28，Phase 28.K.28）** — 上表 `StreamPanel reasoning 思维链文本 = 永不渲染`
> 一条**已被 Owner 决定推翻并收窄**。该行针对的是 E-2 时代的 **StreamPanel**（K.20 起该面板已移除）；
> 现行为：`reasoning` delta **允许进入 step 输出盒**（渲染为弱化+「思考」标识的独立 segment），
> 但**仍不进入答案气泡 `stream`**，也**仍不进入 AgentActivity 的 activity DTO**。
> 详见 `phase-28k28-reasoning-displayable-buffer.md`。本表保留为历史记录，未改动。

## 9. Agent Identity Mapping

`ASSISTANT_NAME`（presentation-level，可调）；无 registry/agent id
渲染。未引入新品牌名。

## 10. Raw Event Leakage Audit

AgentActivity 无 Trace 段/事件名/事件计数（E-1 已移除 Inspector 内嵌；
本轮移除残余）。activity-latest 行 = activity.ts 中文映射输出。

## 11-12. Artifact Rendering / Fake Report Card 根因与修复

根因（E-1 已定位）：ChatLayout finalize 对**任何 completed** 终态用
stageOrder 猜出 insurance-report + 硬编码标题 → chatState 追加 artifact
消息。**修复**：`consumerFinalizeArtifact` = `status==="completed" &&
events 含 artifact_created@report-generation` → 才有卡。QA 轮零
artifact 事件 → 零卡（U4 live 证实：新会话 grep 查看完整报告/
insurance-report/run = 0）。真实报告 → 既有 ReportModal 原样（Markdown
渲染，运行时原产物）。**未新增类型/后端/契约。**

## 13-16. QA Refusal / Clarification / Needs Review / Error

- Refusal：正文=后端诚实拒答文案（run_completed.message，服务器聊天
  取回）；不再包报告卡；`QA_REFUSED` 字符串从不渲染。
- Clarification：正文=agent 自然语言澄清问题（U2 形态）；头部
  「需要你补充信息」；无 reason code/intent/router 概念。
- Needs Review：头部「需要进一步核实」；无 approval/eval/risk 内部物。
- Error：503 横幅「暂时无法回答：…」；网络错误「暂时无法连接服务，
  请稍后再试。」；stream-error 直显 error 字符串的问题随
  consumerFallbackText 模式就绪，全量错误文案统一在 **E-5**（本轮未
  大改，遵守分工）。

## 17. DOM Leakage Tests

新增 `consumerDom.test.tsx`（#/chat 全 App 渲染 + 投毒 chat 状态）：
断言 body/modal 文本不含 §7 全部禁止串（run_leak/bm-leak/
insurance-report/QA_REFUSED/Developer/Inspector/Dashboard/Trace/Eval/
Debug/provider/glm/prompt…），且真实报告卡+Modal 正常。新增
`consumerView.test.ts`（allowlist/E-F 门控/回退文案/身份常量）。

## 18. Runtime Reuse Evidence

U4（17:15Z，SCRIPTED_PROBE）：消费者壳输入「重疾险的等待期一般是
多久？」→ `intent insurance_qa conf=1.00 rule` → shadow：
`knowledge-qa fired reason=authority` → `qa_answered grounded` →
run_completed（[E1] 引用 + 冲突条款双侧处理文案）→ UI 答案直呈、
**零报告卡**。bus runs=4=全部探针（REAL_USER=0 维持）。

## 19. Architecture Invariants（17/17）

单 Runtime ✓（仅既有 /api）· 无 Agent/Workflow/Tool 选择 ✓ · Router
唯一 authority（U4 实证）✓ · Intent≠Prompt 未触碰 ✓ · View=allowlist ✓
· 内部字段不直入组件渲染 ✓ · DOM 无内部 ID ✓ · raw event 不显示 ✓
· **Completion≠Artifact ✓ · 无真实 artifact 即无卡 ✓** · Grounding/
Citation 未触碰 ✓ · Event/Artifact 契约未改 ✓ · Authority 未变 ✓ ·
REAL_USER 未开放 ✓

## 20-21. Test / Regression Results

```text
web:     PASS — 175 passed + 2 skipped（E-1 基线 161+2 → 新增
         consumerView 12 + consumerDom 2 + AgentActivity 净 2；更新
         Composer 冲突横幅断言+AgentActivity 披露断言反转）
tsc:     PASS — clean
backend: PASS — 729/729（零 runtime 改动；B4/M4/M3 含于其中全绿）
```

## 22. Files Changed

```text
A  web/src/state/consumerView.ts + consumerView.test.ts
A  web/src/components/chat/consumerDom.test.tsx
M  web/src/components/chat/ChatLayout.tsx（finalize 门控）
M  web/src/components/chat/AgentActivity.tsx（消费者化重写渲染层）
M  web/src/components/chat/AgentActivity.test.tsx
M  web/src/components/chat/ArtifactCard.tsx（白名单卡片/Modal）
M  web/src/components/chat/Conversation.tsx（去 caseId 传递/横幅消费者化）
M  web/src/components/chat/Composer.tsx（提示文案）+ Composer.test.tsx
```

## 23. Files Not Changed

runtime/** · schema/** · config/** · api/client.ts · chatState.ts ·
activity.ts（映射层本体——E-3）· runReducer.ts · types/runtime.ts ·
内部面组件（Review*/Dashboard/DeveloperMode/RuntimeInspector）·
ADR/PRODUCT_VISION/ARCHITECTURE_PRINCIPLES · auth。

## 24. Deferred Issues

E-3：activity.ts 完整语义扩展（QA/grounding/终态文案统一；header 与
latest 措辞目前并存「已完成/分析完成」）· runId/artifactType props 彻底
DTO 化 · E-4：导出/深链 · E-5：错误/终态全量 UX（stream-error 文案
统一走 consumerFallbackText）· E-6：鉴权 · 旧持久化会话的历史虚构卡
（用户数据不动；可在未来提供一次性清理）· 会话持久化后端（Owner）。

## 25. Owner Decisions

① E-3..E-6 逐段授权；② ASSISTANT_NAME 文案确认（现「保险顾问助手」）；
③ HD-2/鉴权/M5 遗留（不变排队）。

## 26. Next Phase

28.E-3 Consumer Activity Mapping（activity.ts 扩展 + 文案统一 + DTO 化
收尾）；E-4/E-5 可并行推进。

## 27. Scope Confirmation

```text
Business code changes = web/**（上列 10 文件）
Runtime/Router/Intent/Grounding = UNCHANGED
Event/Artifact Contract = UNCHANGED · WeKnora = NOT CONNECTED
REAL_USER = NOT ENABLED · ROUTER_AUTHORITY = UNCHANGED
CONSUMER role = NOT CREATED · Auth policy = UNCHANGED
```
