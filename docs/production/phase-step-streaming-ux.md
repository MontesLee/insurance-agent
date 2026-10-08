# Agent 执行步骤级 LLM Streaming 展示（Step Streaming Output）

Date: 2026-09-28 · 前端-only 实现（**零后端改动·零新事件类型**）。

## 1. Architecture Audit

```text
现有 streaming 能力：
  · Provider 层 OpenAICompatProvider.stream_generate（真 token 流）
  · Agent 环 _generate_with_retry 逐 delta emit("agent_stream_delta",
    {kind: reasoning|content})（K.24 看门狗内）
  · QA 切片 K.26 句子级 validated streaming
  · SSE transient 通道（live-only 不入历史/replay）
现有 Step lifecycle：
  · agent_step_started（durable·data.step=N）开步
  · agent_decision（durable）闭步
  · run_completed/run_failed 终结
现有 transport：SSE GET /api/runs/{id}/stream（transient delta 无 id 行）
前端时间线：consumerActivities 折叠 ✓/●/○ + K.20 全局 stream 气泡
缺口：content delta 无 step 归属——全部进一个全局缓冲，无法按步展示
```

## 2. Files Changed

```text
web/src/state/runReducer.ts
  + RunUiState.stepOutputs: Array<{key,text}> / currentStepKey
  + agent_step_started 开桶（key="step-N"）·delta 归桶·
    agent_decision 闭归属·terminal 冻结；QA 路径不变（全局气泡）
  原因：step 归属是纯事件序推导（SSE 有序），零后端改动
web/src/components/chat/AgentActivity.tsx
  + StepOutputBox（React.memo）固定高度 max-h-40/overflow-y-auto/
    活动光标/用户滚动保护/渲染层 sanitize
  + 活动卡内 step-outputs 区（每桶一盒·完成保留·活动盒带光标）
  原因：Codex 式每步执行过程展示
web/src/state/stepStreaming.test.ts（新·7）
web/src/components/chat/stepOutput.test.tsx（新·5）
```

## 3. Event Contract

零新事件类型——复用既有词汇，归属为前端推导：

```text
agent_step_started{step:N}  → 开桶 step-N（currentStepKey=step-N）
agent_stream_delta{kind:content} → 追加至 currentStepKey 桶（尾 4000 截断）
  kind:reasoning → 永不入桶（E-2 维持）
agent_decision → currentStepKey=null（后续 delta 不归属旧步）
run_completed/run_failed → 冻结全部桶（currentStepKey=null·零后写）
QA 切片（无 agent_step 事件）→ 全局 stream 消息气泡（K.20 不变）
```

## 4. Runtime Data Flow

```text
LLM provider stream_generate
  ↓ (真 token delta)
agent loop _generate_with_retry → emit agent_stream_delta{kind,text}
  ↓ (reasoning 消费即弃)
server emit → bus.publish_transient → SSE（live-only）
  ↓
runReducer：currentStepKey 开桶时 delta 入该步桶（否则全局气泡）
  ↓
AgentActivity → StepOutputBox（memo·固定高·自动滚动·光标·sanitize）
```

## 5. Tests

```text
before: web 258 passed + 2 skipped · tsc clean
after:  web **270 passed + 2 skipped**（+12：stepStreaming 7 +
        stepOutput 组件 5）· tsc clean
新增 12 · 通过 12 · 失败 0
覆盖：Case A 单步累积+终态冻结·Case B 多步隔离（step2 不入
  step1）·reasoning 零入桶·QA 路径不变·决策边界不误归属·
  Case D 终态后零写·长文尾 4000 截断·组件（双盒+sanitize+
  data-active+max-h-40/overflow 类+无步内容零盒）
```

## 6. Manual Verification

```text
未执行（live pilot 上需 Owner 授权重启前端/后端配合真实 LLM 流）——
静态+组件级测试已证：delta 到达即渲染路径成立（真实 transient
通道与 K.26 live T_first<T_final 同链）；组件固定高/滚动/光标/
  sanitize 在 jsdom 断言。live 手验=下次 Owner 授权窗口。
```

## 安全

```text
reasoning 零入桶（E-2）·渲染层 sanitizeConsumerText（K.25-S1 最终
防线）·content-only·无内部 ID 入 DOM（组件断言）·桶仅 transient
（不落盘不重放）
```
