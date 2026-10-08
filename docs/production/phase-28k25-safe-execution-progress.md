# K.25 Final Report — Consumer Safe Execution Progress

Date: 2026-09-27 · Phase 0-15 执行完毕。

## 1. Result

```text
PASS WITH LIMITATION（技术链路全通+全量回归绿；Real-User R1-R4
=PENDING——无自然新流量且 pilot 仍跑 K.25 前码，不 synthetic 冒充）
```

## 2. Root Cause

```text
K.21 已证：QA 路径 backend 只发 4 事件（run_started/intent_classified/
qa_answered/run_completed）——检索与生成两个最长阶段零事件→消费者
只能见 understand+work 两行+K.17 心跳。规划路径事件丰富（stage_/
eval_/tool_）但 E-3 折叠①未显示 ○ 未启阶段②工具级 retry 噪声会闪
"未完成"③无终态冻结（stale 事件可重开进度）。
```

## 3. Actual Event Chain

```text
Backend(run_qa_turn 现于检索前后发既有 tool_started/completed) →
EventBus(tool_* 走 durable _emit·delta 走 transient) → SSE →
runReducer → consumerActivities（allowlist 折叠+intent 追踪+终态
冻结）→ AgentActivity（✓/●/○ 三态渲染）→ Consumer Chat
```

## 4. Existing Events Reused

```text
tool_started / tool_completed / tool_failed（QA 检索里程碑——复用
agent 环既有词汇，payload {step,tool} 同构）· intent_classified（意图
追踪驱动 composing 派生）· stage_started（○ 门控）· 其余 E-3 既有映射
全部保留
```

## 5. New Events

```text
NONE（零新事件类型——QA 检索里程碑为既有 tool_* 词汇在新调用点的
发射；payload 仅 {step:1, tool:"knowledge_search"}）
```

## 6. Consumer Progress Model（最终允许集）

```text
understand（已理解你的问题）· work（正在为你分析/已完成分析）·
materials（正在核实相关资料/已完成资料核对）· catalog（产品资料）·
verify（正在核实相关信息/已完成信息核实——eval/grounding）·
composing（正在整理回答/已整理回答——仅 QA 意图·检索完成后派生）·
stage:*（规划 8 阶段动词短语）· report（分析报告已生成）· clarify
（需要你补充信息）· + AgentActivity 层：generation 行（K.17 delta
驱动）· heartbeat（K.17 真静默）· ○ pending（规划未启阶段·真实
stage_order）——未知事件一律 fail-closed 隐藏（U2）
```

## 7. Event Mapping（新增/变更部分）

```text
tool_started(knowledge_search)      → 正在核实相关资料（materials running）
tool_completed(knowledge_search)    → 已完成资料核对 +（QA 意图时）
                                     正在整理回答（composing running）
qa_answered / run_completed/failed  → 已整理回答（仅当已启动）
intent_classified.data.intent       → 追踪（insurance_qa/product_qa/
                                     governed-unknown → composing 适用；
                                     plan → 不适用）
tool_failed（运行中）               → 行保持 running（I6 retry 稳定；
                                     终态决定最终文案）
run_completed/run_failed            → 折叠冻结（terminal=true，后续
                                     stale 事件 break——I10）
stage_order（真实工作流定义）        → ○ 正在<动词>（仅 ≥1 stage_started
                                     后显示；QA 轮无 stage 事件→零模板）
```

## 8. Safety

```text
CoT leakage: 0 · Reasoning leakage: 0 · Internal ID leakage: 0 ·
Tool leakage: 0 · Skill leakage: 0 · Agent leakage: 0 ·
Raw event leakage: 0 · Exception leakage: 0
（progressProjection U3/U4/U5 + consumerDom FORBIDDEN 族 + 既有
E-2/E-3 套件；后端 tool_* payload 仅 {step,tool} 固定词汇——K.22
T13 更新断言锁定）
```

## 9. Event Robustness

```text
Duplicate: PASS（U6——upsert-by-key 幂等）· Replay: PASS（同 U6+
折叠确定性）· Reconnect: PASS（tool_* 走 durable 通道可重放·delta
transient 按设计不重放）· Out-of-order: PASS（顺序折叠+状态替换）·
Terminal race: PASS（U7/I10——terminal 冻结）
```

## 10-13. K.17/K.20/K.22/K.24 Regression

```text
全 PASS——K.17 测试 16/16（含 T8 心跳/活性行共存）·K.20 streamMessage
9/9·K.22 6/6（T13 断言按新 payload 契约更新）·K.24 8/8——全部含于
全量 808+2 零失败
```

## 14. Backend Tests

```text
808 passed + 2 skipped（零失败）before=808+2（K.24 后）→ after=808+2
（K.25 后端改动经 K.22/K24/C1/C2/K7 套件+全量验证）
```

## 15. Web Tests

```text
255 passed + 2 skipped（before=246+2 → after=255+2；+9 progressProjection
新测试；1 处 planning 期望按 ○ 新契约更新）· TS=PASS
```

## 16. TypeScript

```text
PASS（tsc --noEmit clean）
```

## 17. Real User Verification

```text
R1（QA）: PENDING · R2（规划）: PENDING · R3（长生成）: PENDING ·
R4（失败/拒答）: PENDING——不 synthetic 冒充；且 pilot :8123 仍运行
K.25 前码（生效需 Owner 授权重启）
```

## 18. Before / After

```text
Before（QA 轮）：已理解你的问题 ● 正在为你分析 →[12s 心跳]→ 终局
After（QA 轮）：✓已理解你的问题 ●正在核实相关资料 → ✓已完成资料核对
  ●正在整理回答 →（K.22 门后 delta→K.17 正在生成回答+K.20 流式
  气泡）→ ✓终局
After（规划轮）：既有 ✓/● 阶段行 + ○ 未启阶段（真实 stage_order）
```

## 19. Remaining Limitations

```text
①QA"正在整理回答"为检索完成后的派生态（该路径无独立生成开始事件
  ——不加新事件类型的前提下的诚实粒度；生成中细粒度=未来可选）
②○ pending 仅规划脊柱（stage_order）——agent 通用轮无工作流定义
③pilot 需 Owner 授权重启载入 K.24+K.25 后端
④Real-User R1-R4 待自然样本
```

## 20. Files Changed

```text
runtime/qa_agent/agent.py — 检索里程碑 tool_* 发射（既有词汇·emit
  异常无害）·风险低（observability-only·K.22 契约不变）
runtime/server.py — QA emit lambda 分流（delta→transient·其他→
  durable _emit）·风险低
web/src/state/activity.ts — intent 追踪·composing 派生·tool_failed
  稳定化·terminal 冻结·verbOfStage 导出·风险中（投影语义——9 新
  测试+既有套件锁定）
web/src/components/chat/AgentActivity.tsx — ○ pending 渲染·风险低
tests/runtime/test_k22_qa_streaming.py — T13 断言按新 payload 契约
web/src/state/progressProjection.test.ts — 新 9 测试
web/src/components/chat/AgentActivity.test.tsx — planning 期望+○
```

## 21. Scope Check

```text
Router: unchanged · Runtime: unchanged（零新引擎/EventBus/SSE）·
Event vocabulary: unchanged（零新增——tool_* 为既有类型复用）·
K.17: preserved · K.20: preserved · K.22: preserved（Policy B 语义
零触碰）· K.24: preserved（deadline/watchdog 零触碰）
```

## 22. Owner Decision Required

```text
①pilot :8123 重启授权（载入 K.24 deadline+K.25 进度后端）
②Real-User R1-R4 验证窗口（重启后自然流量）
③（可选未来）QA 生成开始的独立后端事件（新事件类型——需授权）
```
