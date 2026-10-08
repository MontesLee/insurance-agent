# Phase 28.K.16 — Consumer Live Execution Feedback Audit（AUDIT + DESIGN ONLY）

Date: 2026-09-27 · READ→TRACE→ANALYZE→PROPOSE（零改动·零重启·零测试）。

## 1. Current Architecture（真实链路·代码级）

```text
User Message → POST /api/chats/{id}/messages
→ _agent_worker：intent_classified →（切片或 agent 环）
→ agent 环每步：_generate_with_retry
   · 优先 provider.stream_generate（glm：reasoning_content 先流·
     content 后流）
   · 每个 delta → bus.publish_transient("agent_stream_delta",
     {kind: reasoning|content, text})（server.py:804-810·不入事件史）
→ SSE /api/runs/{id}/stream：transient delta 无 id 行但**实时转发**
   （server.py:990）
→ useRunStream(EventSource) → runReducer
   · agent_stream_delta → 缓冲进 s.stream{kind,text(截尾4000)}·
     **绝不入 events[]**（runReducer.ts:154-160/288-289）
   · kind=content → AgentActivity StreamPanel 渲染（"正在输出…"）
   · kind=reasoning → 缓冲但永不渲染（E-2 安全裁定）
→ consumerActivities(events[]) 折叠 → AgentActivity 清单/心跳（K.13
   心跳键=events.length——delta 不改变它）
→ 终态 consumerTerminalView（E-5 优先级）→ finalize
```

## 2. Event Inventory（Consumer 可用性）

```text
可用（已映射/可映射·activity.ts 既有 allowlist）：
  run_started·intent_classified·agent_step_started·agent_decision·
  tool_started/completed/failed（knowledge_search/check_catalog→
  materials/catalog）·stage_started/completed/failed·eval_started/
  passed/failed（K.13→verify）·artifact_created(report)·qa_answered·
  run_completed/failed
transient（实时送达·内容受限映射）：
  agent_stream_delta{kind=content}→答案流渲染；
  {kind=reasoning}→仅缓冲不渲染——**到达这一事实未被用作信号**
不可用（内部·正确地隐藏）：repair_*·checkpoint_*·agent_step_error·
  intent shadow 字段等
```

## 3. Silent Period Root Cause（run_50389328 的 40.1s）

```text
定位：step3 的最终答案生成期（04:05:17.4→04:05:57.5）。
逐层事实：backend 在执行 ✓（glm 流式生成中）；EventBus 有事件 ✓
  （agent_stream_delta 持续发布·transient）；SSE 有传输 ✓；
  frontend 收到 ✓（reducer 缓冲）；frontend 丢弃=**半真**——
  content 部分最终渲染，但 (a)reasoning 类被安全丢弃（多数时间窗）
  (b)delta 不入 events[]→活动清单与 K.13 心跳键均不感知
→ 用户看到：清单静止；content 未流出前无任何"生成中"信号。
结论：**不是后端卡死，也不是 SSE 断流——是"到达的 delta"未被
  转译为消费者安全的执行活性信号。**
```

## 4. K.13 Assessment

```text
实现（AgentActivity.tsx）：useActivitySilence(events.length)——纯前端
  定时器：live 且 12s 内 events.length 不变→显示固定等待文案；
  新事件即清；终态不显。
不足（真实反馈证实）：①键=events.length——transient delta 不计入，
  即使 token 正在流入也照常触发"请稍候"（弱化可信度）；②文案静态
  无事实差异（无法区分"正在生成"与"真无事件"）；③12s 阈值前仍是
  完全静默。判定：**是纯前端定时器**（无 backend truth）——按设计
  保守，但信息量不足。
```

## 5. LLM Stream Assessment

```text
A 答案流：agent_stream_delta{kind=content}——backend 产生 ✓·SSE ✓·
  reducer ✓·consumerView/组件 ✓ 渲染（既有·保留）
B reasoning：{kind=reasoning}——同链路到达但**永不渲染**（E-2）；
  现有缓冲仅取 text 尾部 4000 字符供内部状态——确认 B 不入 DOM
  （consumerDom 套件锁定）
C 执行事件：无显式 generation_started/progress 语义事件——
  **NO EXISTING SAFE EXECUTION EVENT**（语义层面）；但 delta 到达
  本身=更强事实（真实 token 流）·未被利用
```

## 6. Security Assessment

```text
Allowed（消费者可显）：理解/检索资料/核实信息/整理方案/生成回答/
  等待补充——活动 allowlist 既有键
Forbidden（维持）：prompt·CoT/reasoning 文本·tool 参数与内部名·
  provider/model·skill·run_id/artifact_id/eval_id·agent 内部
  ID·stack·raw event·内部错误——现状全部达标（E-2/E-3 套件+
  consumerDom FORBIDDEN 族锁定）
方案红线：任何设计只使用"到达时间/数量计数"这类元数据，绝不使用
  reasoning 内容本身
```

## 7. Options

```text
Option A（推荐·复用既有事件·纯前端）：
  reducer 在每个 agent_stream_delta 记录 lastDeltaAt（时间戳元数据，
  内容零暴露）；AgentActivity 派生真实活性行——最近 ~2s 内有 delta
  →「● 正在生成回答」（确定性文案·映射层新增键）；心跳条件收紧为
  "无事件且无近期 delta"（真静默才显示"请稍候"）；可选加客户端
  elapsed「已用时 Ns」（明确为客户端计时·终态即停）。
Option B（后端里程碑·Option 2）：agent 环在检索/生成相位发
  execution_phase_started/completed 极少量高层事件（不含任何内部
  信息）——语义更强·但触后端事件词汇（需 Owner 授权·冻结面）。
Option C（仅增强心跳）：保留 K.13·降低阈值+动画——无 backend
  truth，不解决可信度（不推荐单用）。
```

## 8. Recommended Minimal Design

```text
Option A（frontend-only·~3 文件）：
  1) runReducer：agent_stream_delta 分支追加 s.lastDeltaAt=Date.now()
     （RunUiState 新字段·纯元数据）
  2) AgentActivity：活性派生 hook——now-lastDeltaAt<2000ms→当前行
     「正在生成回答」（复用 ● 进行中样式）；heartbeat 显示条件改为
     live && 无新事件 && 无近期 delta；终态/流关闭即停（既有）
  3) consumerView/activity：新增 generation 活动键文案（正在生成
     回答/已生成回答[由 qa_answered/finish 事件闭合]）——走既有
     allowlist 机制
  不改：backend/EventBus/SSE/事件 schema/答案流渲染/E-2 安全层
```

## 9. Exact Files Likely To Change

```text
web/src/state/runReducer.ts（lastDeltaAt 元数据）
web/src/components/chat/AgentActivity.tsx（活性行+心跳条件）
web/src/state/activity.ts 或 consumerView.ts（generation 文案键）
测试：runReducer.test.ts·AgentActivity.test.tsx·activity.test.ts
```

## 10. Test Plan

```text
normal execution（含工具轮）：清单+活性行顺序
long LLM generation：reasoning delta 连续到达→「正在生成回答」持续·
  content 流面板照常·reasoning 文本零渲染
tool execution/failure：materials/catalog 行既有+新增
needs_review/failed/waiting/terminal：终态优先级与心跳立即停止
unknown event：fail-closed 不渲染
internal leakage：FORBIDDEN 族注入=0
reasoning leakage：reasoning delta 全文不入 DOM（关键新断言）
真静默：无事件无 delta>12s→心跳；delta 恢复→心跳消失
```

## 11. DoD

```text
Consumer 在 LLM 真实产 token 期间持续看到「正在生成回答」活性行
（由真实 delta 到达驱动·非定时器伪装）；真静默≥12s 才显示等待文案；
终态立即停止一切活性指示；reasoning/内部实现零泄漏（测试锁）；
全部既有回归绿。实现仍需 Owner 单独授权（本阶段仅设计）。
```
