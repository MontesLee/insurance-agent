# Phase 28.B Preparation Audit — 事件贯通性（只读）

Date: 2026-09-25 · 性质：READ-ONLY（零代码先行）。目标：确认
intent_classified / qa_answered / router decision / grounding 事件在
events.py → SSE → 前端契约 → AgentActivity → Chat UI 的贯通状态。

## 0. 管道结构（as-built 实证）

```
runtime/events.py EVENT_TYPES (后端词汇表，含 intent_classified+qa_answered)
  → EventBus → /api/runs/{id}/events + /stream(SSE)（原样透传，无过滤）
  → web/src/hooks/useRunStream.ts（EventSource → dispatch "event"）
  → web/src/state/runReducer.ts（"event" case：**所有类型入 state.events
     持久时间线**（agent_stream_delta 除外）；TRANSITIONS 表内类型才驱动
     状态迁移——表外类型存储但不解释，设计性忽略）
  → web/src/components/chat/AgentActivity.tsx（由 RunUiState 投影渲染；
     latestActivity switch 同样只认已知类型）
```

## 1. 四类事件的贯通判定

| 事件 | 后端词汇 | 后端发射 | SSE 透传 | reducer 存储 | 前端类型契约 | AgentActivity 呈现 |
|---|---|---|---|---|---|---|
| **intent_classified** | ✅ events.py:67 | ✅ 每轮（data: intent/confidence/confidence_source/reason_codes/clarification_required/shadow/latency_ms/**route_decision**） | ✅ | ✅ | ❌ union 缺失 | ❌ 不可见 |
| **qa_answered** | ✅ events.py:75 区块 | ✅ QA 切片轮（data: grounding_status/failure_reason/evidence_refs/retrieval/generation_provenance/**slice**/answer_len；答案全文不入事件） | ✅ | ✅ | ❌ union 缺失 | ❌ 不可见 |
| **router decision** | ⚠️ **无独立事件** | ⚠️ 仅作为 intent_classified.data.route_decision 内嵌（完整 RouterDecision 契约文档） | ✅ | ✅ | ❌ | ❌ |
| **grounding started/completed** | ❌ **不存在** | ⚠️ grounding 遥测内嵌于 qa_answered（grounding_status/retrieval/generation_provenance.attempts+gate_violations）；检索/生成/门禁各阶段无独立起止事件 | ✅（如内嵌） | ✅ | ❌ | ❌ |

**结论：管道层（SSE/reducer 存储）全贯通；契约层（EventType union）与
呈现层（activity）双缺口**——即 28.0.1 隐耦 #3 的实态：事件被存储计数
但前端类型系统不可命名、UI 不可解释。router decision 与 grounding 起止
的**独立事件**在后端尚不存在（设计缺口，非同步缺口）。

## 2. 各面细目

### events.py（后端）
- 词汇表 frozenset 含全部生命周期域 + intent_classified（28.A-1）+
  qa_answered（28.C-1）；`_emit` 校验表内类型（表外 ValueError）。
- RuntimeEvent.to_dict 14 字段稳定契约；消息截断 600；RUN_TERMINAL
  = run_completed/run_failed。

### web event schema（web/src/types/runtime.ts）
- `EventType` union **22 值，止于 tool_failed**——缺 intent_classified/
  qa_answered（及未来 grounding_started/completed）。TS 编译期约束：
  typed 代码无法命名新类型（运行时数据仍流过）。
- `RUN_TERMINAL_EVENT_TYPES` 与后端 RUN_TERMINAL_TYPES 一致 ✓。

### AgentActivity（web/src/components/chat/AgentActivity.tsx）
- 渲染输入=RunUiState 投影：stageOrder/stages/evals/stream/
  latestActivity；**无 intent/route/grounding 概念**。
- 轮次计数（`{n} events`）含新事件（存储层贯通的佐证）。

### SSE pipeline
- useRunStream：EventSource + after_event_id 续传游标 ✓；断线重连
  `connected` 状态 ✓；事件按序 dispatch ✓。无类型过滤——贯通无阻塞。

### Chat UI（ChatLayout/Conversation）
- agent 轮由 AgentActivity 呈现进度、Conversation 呈现消息；QA 切片轮
  的 run_completed（message=answer 前 600 字）正常入消息流 ✓；意图/
  grounding 过程对用户不可见（当前=设计默认：L4 层级未定）。
- 既有债在案：chatState.ts mapPromptToCase 前端 5 路关键词映射仍在
  （demo 模式；退役=28.B 内容）。

## 3. 缺口清单（映射到本阶段步骤）

| # | 缺口 | 处置 | 步骤 |
|---|---|---|---|
| G-1 | EventType union 缺 intent_classified/qa_answered | **本阶段修**（web/** 允许） | Step 1 |
| G-2 | grounding_started/grounding_completed 后端不存在 | **契约先行**：union+schema 预留（reserved）；后端发射=未来 runtime 授权项 | Step 1/2 |
| G-3 | route_selected 独立事件不存在（ADR-020 设计提及） | 设计文档记录数据需求；不本轮实施 | Step 3 |
| G-4 | 双端等价无自动化守护 | **本阶段建** contract tests（backend == schema 词汇；frontend ⊇ schema+reserved） | Step 2 |
| G-5 | AgentActivity 不呈现新事件 | **设计 only**（不改 UI——spec 禁令） | Step 3 |

## 4. 判定

管道无阻塞；**契约与呈现双缺口即本阶段工作量**。Step 1（web 契约同步）
可在允许路径（web/**、schema/**、tests/**）内完成且零 UI 改动；
grounding 独立事件与 route_selected 的后端发射留待 runtime 授权（列入
migration checklist 前置项）。
