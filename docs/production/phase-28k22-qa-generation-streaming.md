# Phase 28.K.22 — QA Generation Streaming

Date: 2026-09-27 · 后端最小改动（授权范围：QA generation path·
generate_grounded·流式包装·接线·测试；前端零改动——K.20 已备）。

## 1. Status

```text
COMPLETE（backend **800+2 零失败**·web/tsc 沿用干净基线；
REAL_USER verification=PENDING——不 synthetic）
```

## 2. Pre-Implementation Audit

```text
A. Agent 环可流式：_generate_with_retry 优先 provider.stream_generate
   → 每 delta emit("agent_stream_delta",{kind,text}) → server 包装
   publish_transient（live-only）→ SSE → K.20 reducer ✓
B. QA 现状：run_qa_turn → generate_grounded → gateway.generate
   （单次完整调用）→ 引用门 → AnswerContext——零 delta 发射
C. Adapter：_GatewayProviderAdapter.generate 为单次调用（无流式
   接口）；provider 侧 stream_generate 存在但 QA 未用
```

## 3. Root Cause

```text
K.21 R2：QA 生成路径（knowledge-qa/product-qa 切片共用
generate_grounded）结构上不发射 agent_stream_delta → SSE 无
content → K.20 stream-message 无从显示。
```

## 4-5. Streaming Architecture / Safety Policy

```text
**Citation gate compatibility = B（buffered streaming）**
Evidence：现有 QA 契约=AnswerContext 唯一交付物——答案只有在引用
闭包门通过后才存在"已验证"形态（B5.1 校准：attempts 循环+违规
反馈再生成）。真 token 级流式必然让消费者看到"未经门验证的中间
文本"，门拒后需撤回——违反"不为流式降低 citation gate"。
因此采用 Policy B：
  LLM 生成（既有单次调用）→ 引用门 → PASS → 将【已验证答案】
  按 48 字符定长切块经既有 transient 通道发射
  agent_stream_delta{kind:"content"} → SSE → K.20 消费。
fail-closed by construction：证据不足/检索空 → 生成不发生 → 零
delta；门拒/生成失败 → 零 delta。reasoning 在此路径不存在（单次
生成无流式中间产物）且永不发射。
诚实注记：B 非 token 级流式——用户看到的是"验证通过后的快速
级联呈现"（数帧内增长→收敛为正式消息）；等待时长本身不变
（治理优先，spec §8 明文允许）。
```

## 6. Backend Changes（3 文件）

```text
runtime/grounding/loop.py：generate_grounded(+emit=None)——门 PASS
  后 _emit_streamed(answer)（48 字符切块；emit 异常静默=纯展示层）
runtime/qa_agent/agent.py：run_qa_turn(+emit 透传)
runtime/product_qa_agent/agent.py：run_product_qa_turn(+emit 透传)
  ——首版遗漏 product-qa 透传（battery 捕获：切片 TypeError→
  fail-closed 落回 agent 路径→断言红）已补，53/53 复绿
runtime/server.py：QA 切片调用传 emit=（构造与 agent 环完全一致
  的 transient payload——同 schema·同通道·live-only）
零改动：Intent/Router/检索/证据门/引用门语义/AnswerContext
schema/事件词汇/SSE/前端
```

## 7. Consumer Integration

```text
K.20 零改动消费：QA delta 形状={kind:"content",text}（与 agent 环
一致）→ reducer 累积→stream-message 增长→terminal 收敛为正式
assistant message（qa_answered/run_completed 既有顺序不变）。
K.17：delta 到达驱动「正在生成回答」+12s 心跳语义不变。
```

## 8. Test Matrix（test_k22_qa_streaming·6 项）

```text
T1/T6 门 PASS→切块发射·拼接=答案全文（零重复·payload 仅
  {kind,text}）✓ T2/T3 证据不足/检索空→0 delta ✓
T7 引用门拒→0 delta ✓ T8 生成前 provider 失败→0 delta ✓
T13 payload 泄漏零（reasoning/provider/model/tool/skill/run_/
  artifact/prompt/system）✓ emit 异常不破坏生成 ✓
（T4/T5 混合流=K.20 前端套件覆盖[本路径无 reasoning]·T9 部分
  内容=构造上不发生[B 为完成后发射]·T10 needs_review=QA 路径无
  此终态·T11 快完成/T12 K.17=前端套件·如实映射见报告）
```

## 9. Safety / Leakage

```text
证据门前置（生成不发生=零 delta 构造保证）·引用门不可绕过
（发射点在门后）·fail-closed/needs-review/completed/failed 契约
零变化·payload 仅 {kind:"content",text}
```

## 10. F2 Observability

```text
零触碰：gateway.generate 调用路径未变（llm.call 记录·K.11 字段
  全保留）——emit 是门后的展示旁路，不经过 gateway
```

## 11. Real User Verification

```text
PENDING（不发送 synthetic；下一自然 QA 成功轮将直接展示）
```

## 12. Known Limitations

```text
①Policy B 非逐 token 流式——等待体验的实质改善需未来 Owner 决策
  （A 档：接受"门拒即撤回"的 UX 换真流式——治理变更需授权）
②48 字符定长切块为确定性选择（可调）
③llm_unavailable 轮仍无任何流（正确——无验证内容可发）
```

## 13. Rollback

```text
文件级回滚（无 flag）：还原 4 个改动文件（grounding/loop.py·
  qa_agent/agent.py·product_qa_agent/agent.py·server.py）至
  K.21 状态→QA 路径回到零 delta（K.20 对 agent 环流式不受影响）。
  emit=None 默认值=所有既有调用点行为不变（向后兼容构造保证）。
```

## 14. STOP

```text
零 Intent/Router/WeKnora/grounding/citation/fail-closed/事件词汇/
SSE/前端改动·零 synthetic·未重启（pilot 后端需 Owner 授权重启
方可生效——当前 :8123 仍运行 K.22 前代码）
```
