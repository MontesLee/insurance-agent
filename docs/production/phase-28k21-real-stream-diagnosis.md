# Phase 28.K.21 — Real Consumer Streaming Path Diagnosis

Date: 2026-09-27 · AUDIT ONLY（零改动·零 synthetic·零重启）。

## 1. Status

```text
COMPLETE（Root cause 定位：R2 变体——QA 切片生成路径后端不发射
agent_stream_delta；用户最近一轮恰走 QA 路径）
```

## 2. Running Instance Verification

```text
backend :8123 PID 5840 LIVE（startup 03:34:43Z·K.13+F1+F2 代码）
frontend :5273 PID 37032（vite dev·HMR）
**运行前端确实包含 K.20**（直接拉取 vite 转译产物实证）：
  · /src/components/chat/Conversation.tsx 服务版含 stream-message ✓
  · /src/state/runReducer.ts 服务版含 lastDeltaAt 与
    "if kind==='reasoning' return"（K.20 缓冲语义）✓
→ R9（前端非 K.20）排除。
```

## 3. REAL_USER Run Used

```text
两条新真实 run（pilot-user-02 首次使用！）：
  run_c3eb2b0a（16:02 本地）：intent=plan 类 → agent 环 → ask_user
    澄清 → waiting/WAITING_USER（39s）
  run_a1f2535e（16:34 本地）：intent=insurance_qa → QA 切片 →
    retrieval allowed=1（weknora）→ generation glm attempts=1 →
    llm_unavailable → 诚实拒答（128s）
用户看到"已理解/正在分析"的最近体验 = run_a1f2535e（QA 轮）。
```

## 4-9. Layer 1-6 逐层

```text
Layer1 LLM：两轮均进入 LLM（ask 文本=LLM 生成；QA 轮生成尝试过）
Layer2 delta：run_a1f2535e=**零 delta**——QA 切片（run_qa_turn→
  generate_grounded→网关适配器）**不发射 agent_stream_delta**（代码
  实读：仅 agent 环 _generate_with_retry→stream_generate 发射）；
  run_c3eb2b0a（agent 环）按代码应有 delta（transient 不可回溯——
  如实：无法事后证实）
Layer3 EventBus：QA 路径无 publish（与 Layer2 同因）
Layer4 SSE：无从转发（无源）；SSE 通道本身在案工作（K.16 证）
Layer5 reducer：K.20 语义已在运行前端（§2 实证）；无事件可处理
Layer6 渲染：stream-message 门控条件正确——无 content delta 时
  正确不显示（不伪造）；K.17 心跳在 12s 后应已显示（用户报告的
  静态期与 12s 前窗口+QA 拒答文案一致）
```

## 10. Test vs Production Payload Comparison

```text
K.20 测试=直接向 reducer 注入 agent_stream_delta 事件（形状与
后端发射完全一致：data{kind,text}——无 mismatch）。测试从未覆盖
"QA 路径应产 delta"——因为 QA 路径本就不产（K.20 §11-① 已记录
该限制）。字段/嵌套/事件名/通道/reducer action/SSE 序列化：
逐一比对零 mismatch。
```

## 11. Root Cause

```text
**R2 —— 进入 LLM generation，但后端没有产生 agent_stream_delta。**
细分：仅 agent 环（run_agent_turn 路径）发射 delta；QA 切片
（知识问答主路径）经 generate_grounded→LLMGateway 适配器调用，
**无流式发射**。用户最近轮（16:34）intent=insurance_qa 走 QA
路径 → 零 delta → 无 stream-message（正确不伪造）→ 仅剩
"正在为你分析"+12s 后心跳 → 最终 llm_unavailable 诚实拒答。
Observed evidence → run_a1f2535e 事件链（4 事件·无 delta）+
qa-ctx（attempts=1 llm_unavailable）+ 代码实读（发射点仅在
agent.py _generate_with_retry）。
次要事实：该轮生成本身失败（glm 不可用）——即使有流式，该轮
也无答案可流。
```

## 12. Minimal Recommended Fix（不实施）

```text
在 QA 生成路径增加 content 流式发射：generate_grounded 的网关
适配器（或其 provider 流式包装）将 content 分块经现有 emit 通道
以 agent_stream_delta{kind:content} 转发（reasoning 不发）。
触点=runtime/grounding/loop.py 或 runtime/llm/gateway.py 的流式
包装 + server QA 切片的 emit 接线——**后端改动，需 Owner 单独
授权**（K.20 授权范围仅前端；本诊断证实该缺口即真实用户根因）。
不改：QA 语义/引用门/证据门/EventBus/SSE 协议（复用 transient
delta 通道，零新事件类型）。
```

## 13. Evidence

```text
vite 转译产物拉取（K.20 在线证明）·两 run 事件链+qa-ctx+chat 全文
（operator 只读）·runtime/agent/agent.py 发射点实读·
runtime/grounding/loop.py QA 路径实读·K.16/K.20 报告（已知限制
记录链）
```

## 14. STOP

```text
零代码/配置/测试修改·零 synthetic·零重启·零 REAL_USER 干预
```
