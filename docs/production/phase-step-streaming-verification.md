# Step Streaming — 审计与验收证据封存

Date: 2026-09-28 · 性质：**只读审计 + 验收取证（零代码改动 · 零提交）**。
触发来源：一份「实现 Agent 执行步骤级 LLM Streaming 展示」的外部规范。
结论：**该功能在当前工作区已实现**；本轮按规范 §20 STOP，仅封存证据，不提交。

---

## 1. 审计结论：功能已存在（未提交，同日）

既有实现在本工作区已落地，与规范 UI 要求逐条对应：

```text
web/src/state/runReducer.ts
  · stepOutputs: Array<{key,text}> · currentStepKey · sawAgentStep
  · agent_step_started → 开桶 key="step-"+data.step（无则计数）
  · agent_stream_delta{kind:"content"} → 追加当前桶（尾 4000 截断）
  · kind:"reasoning" → 永不入桶（E-2）
  · agent_decision → currentStepKey=null（闭归属，不误归属旧步）
  · run_completed/run_failed → currentStepKey=null（冻结，零后写）
  · QA 轮（无 agent_step 事件）→ 首个 content delta 自动开 "qa-composing" 桶
web/src/components/chat/AgentActivity.tsx
  · StepOutputBox（React.memo）· data-testid="step-output-box" · data-active
  · 固定高 max-h-40 / min-h-[3.25rem] / overflow-y-auto
  · 活动光标 · 用户滚动保护（userScrolled ref）· 渲染层 sanitizeConsumerText
测试：stepStreaming.test.ts(7) · stepOutput.test.tsx(5) · stepOutputE2E.test.tsx(2) · streamMessage.test.tsx(9)
文档：phase-step-streaming-ux.md · phase-step-streaming-live-fix.md
```

## 2. 后端既有流式能力（已在 canonical 事件词汇内）

```text
provider  runtime/agent/model.py:155/283        stream_generate（真 token 流）
agent 环  runtime/agent/agent.py:209-240        emit("agent_stream_delta", {kind,text})
QA 切片   runtime/grounding/loop.py:112/258/274 同上（K.22/K.26）
总线      runtime/event_bus.py:104               publish_transient（live-only，不入历史/replay）
传输      runtime/server.py:783-894 / 1539      SSE GET /api/runs/{id}/stream（transient 无 id 行）
前端      web/src/hooks/useRunStream.ts → runReducer.ts
词汇      runtime/events.py EVENT_TYPES == schema/event-vocabulary.json
          已含 agent_stream_delta · agent_step_started · agent_decision ·
          agent_step_error · agent_tool_call · agent_tool_completed · tool_started/completed/failed
```

## 3. 验证证据（本机实测·可复现）

```text
$ cd web && node node_modules/vitest/vitest.mjs run
  Test Files  33 passed | 2 skipped (35)
  Tests      272 passed | 2 skipped (274)
  EXITCODE=0

$ cd web && node node_modules/typescript/bin/tsc --noEmit
  TSC_EXITCODE=0        （clean）

基线对照（docs 记载）：phase-step-streaming-ux 270 → live-fix 272 —— 与实测 272 一致 ✓
```

## 4. 提交阻塞：不存在「仅 step-streaming」的窄提交

依赖闭包实测（只读分析 web/src import 图，种子=runReducer/AgentActivity/三个新测试）：

```text
step-streaming 切片最小「可编译」闭包 = 10 文件
  MOD(4)   web/src/components/chat/AgentActivity.tsx
           web/src/state/activity.ts
           web/src/state/runReducer.ts
           web/src/types/runtime.ts
  NEW(5)   web/src/components/chat/stepOutput.test.tsx
           web/src/components/chat/stepOutputE2E.test.tsx
           web/src/state/consumerView.ts
           web/src/state/contentHygiene.ts
           web/src/state/stepStreaming.test.ts
  clean(1) web/src/components/StatusBadge.tsx
```

两个关键事实：

```text
① 窄提交会编译不过：AgentActivity.tsx 直接 import consumerView.ts /
   contentHygiene.ts，而这两者在 git 中根本不存在（untracked）——
   只提交 step-streaming 文件 = 缺依赖 = 干净检出无法编译。
② 4 个 MOD 文件的 diff 早于 step-streaming：混有 K.17/K.20/K.25/K.26
   消费者活动语义（runReducer.ts +90 · AgentActivity.tsx +327）——
   该闭包 == 「消费者外壳切片」，不是「仅 step-streaming」。
```

工作区在飞总量：**35 modified + 141 untracked**（整个 Phase 28 未提交）。

```text
→ 只有两端可选，无「窄且可编译」的中间地带：
   (a) 10 文件外壳闭包（跨阶段语义，可编译、测试全绿）
   (b) 整个 Phase 28 工作区（176 项一次性 checkpoint）
```

## 5. 与规范的差异（诚实计入，未修）

```text
① 规范 §4/§6 要后端权威 execution_id + 稳定 step_id 落在 delta 上 →
   现状 delta 仅 {kind,text}，归属由前端事件序推导（"step-"+data.step）。
② 规范 §4 要新事件 step.delta / step.failed → 现状刻意零新事件（复用既有
   词汇），且规范 §16 自身禁止第二套 event system。
③ 规范 §14 工具步里程碑（"正在核对 N 条资料"）未入 step 盒 → 现走既有
   activity 行；词汇表已有 agent_tool_call/completed 可承载。
④ 规范 §11 批处理层未加 → 现每 delta 一次渲染（文档已记为已知局限）。
```

## 6. 未验证项（不声称通过）

```text
live 浏览器肉眼验证：PENDING
  原因：需 Owner 授权窗口 + 起后端(:5273 类) + 前端(:5173 vite) + 真实 LLM 流；
        本轮未执行。规范 §19.6 要求「无法验证必须写明原因，不得声称通过」。
  部分实证：phase-step-streaming-live-fix.md 记有 Owner 侧 live 探针
        （3044 deltas · T_first=3.7s ≪ T_final=128s）—— 本轮未复现该探针。
```

## 7. STOP

```text
零代码改动 · 零 git 提交 · 零 backend/EventBus/SSE/事件词汇改动 · 零 synthetic。
本文件为审计与验收取证，写入工作区（未提交），与所述代码同处于在飞状态。
```

---

### 交付摘要

| 项 | 结果 |
|---|---|
| 功能是否已实现 | 是（前端-only，零新事件类型） |
| 既有全量测试 | 272 passed / 2 skipped（exit 0） |
| 类型检查 | tsc --noEmit exit 0（clean） |
| 可否窄提交 | **否**（窄提交编译不过；最小闭包 10 文件且跨阶段） |
| live 手验 | PENDING（未执行，不声称通过） |
| 本轮 git 变更 | **无**（按 Owner 决定：暂不提交，仅封存证据） |
