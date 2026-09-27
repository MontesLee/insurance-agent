# Phase 28.K26 — True LLM Streaming

Date: 2026-09-27 · QA 路径真流式改造（授权范围内：QA generation path·
adapter·gateway streaming·grounding loop·测试·live pilot）。

## 1. Result

```text
PASS（backend **825 passed + 2 skipped 零失败** · web 258+2 · tsc
clean · live pilot：**T_first_delta < T_final 实证**——R1 24s≪94s·
R2 34s≪200s·R4 规划不退化）
```

## 2. Root Cause

```text
K.22 Policy B 为 post-generation chunking（完整生成→门→48 字符
切块）——用户在整个生成期（QA 实测 70-200s）只见 understand/work
两行+心跳；K.21 已证 QA 路径无 delta 的结构性原因=generate_grounded
只调 gateway.generate()（单次调用无流式）。
```

## 3. Before

```text
QA: gateway.generate()（单次）→ citation gate → _emit_streamed
  （48 字符假切块·门后）
generation: 无流式 · stream: 假 · frontend: K.20 就绪但无真 delta
```

## 4. After

```text
Provider: OpenAICompatProvider.stream_generate（既有·复用）
Gateway: LLMGateway.generate_stream(request, on_text)——与 generate()
  完全同治理（policy/PII/rate/circuit/budget/有界重试/RateLimit
  退避/F2 llm.call 记录/错误规范化=429→RateLimit·其余→不可重试
  LLMError 立即 fail-closed）；无流式 provider 回退单次+单 on_text
QA: generate_grounded 流式分支——adapter.generate_stream 在同墙钟
  看门狗下逐 chunk 转发【仅 content 类】（reasoning 消费即弃）→
  句子级 segmenter：缓冲至句边界（。！？；\n）→ 每完整句运行
  【同一 citation gate】→ PASS→emit（sanitize 后）· FAIL→held
  （不外流·final gate 裁决）→ 最终门 PASS 后 flush residual
  （held+尾句）→ 流内容收敛=完整已验证答案
EventBus/SSE/Frontend: 零改动（agent_stream_delta 既有 transient
  通道·K.20 stream-message 渲染·K.17 lastDeltaAt 驱动）
```

## 5. Is it TRUE STREAMING?

```text
**YES** — 三重证据：
单测 T4：chunk 间延迟下 T_first < T_final-0.2s（强制断言）
Live R1：T_first=24.1s << T_final=94s（9 deltas 渐进）
Live R2：T_first=33.9s << T_final=200s（33 deltas·渐进 164s 跨度）
```

## 6. First Delta Evidence（live pilot·probe 主体）

```text
R1（等待期简答）：T_first_delta=24.1s · T_final=94s · delta_count=9
R2（等待期详答）：T_first_delta=33.9s · T_final=200s · delta_count=33
R3（拒答）：T_first=N/A（6s 快拒·零 delta·正确不伪造）
R4（规划）：355s+537s COMPLETED·9/9 VALID（不退化）
```

## 7. Safety

```text
Grounding: 未绕过（句子级=同一 gate 实例；最终门在完整答案上
  原样运行）· Citation: 未绕过（held 机制=段级门拒即不外流）
CoT/Reasoning: 0（adapter 仅转发 content 类·reasoning 消费即弃·
  T12）· Internal ID: 0（句子级 sanitize——分裂 ID 在缓冲重组后
  捕获·T11+live 全场景 NONE）· Tool/Skill/Agent/Raw Event/
  Exception: 0
门拒终局（R2 实证）：流式内容=已验证句·final 门拒→诚实
  QA_REFUSED（无假成功·K.20 失败 partial 保留契约处理已流内容）
```

## 8. K.24

```text
Timeout: adapter.generate_stream 同墙钟看门狗（budget=request.
  timeout_s）· Deadline: run-level supervisor 零触碰· Watchdog:
  保留（含流式调用）· Retry: 有界+RateLimit 退避保留· Terminal:
  _finish_run 幂等零触碰
```

## 9. K.25

```text
Progress: 零触碰（progressProjection 9/9）· Heartbeat: 语义保持
  （真 delta 到达→「正在生成回答」压心跳）· Terminal freeze: 保留
```

## 10. K.25-S1

```text
Server hygiene: 句子级 sanitize（流内第一防线）· Streaming
  hygiene: 分裂 ID 缓冲重组后捕获（T11）· Frontend fallback:
  contentHygiene.ts 渲染层原样（最终防线）
```

## 11. Planning Regression

```text
PASS——agent-loop 流式路径零触碰（provider.stream_generate 既有
  直连）；R4 live 两轮 COMPLETED·9/9 VALID·零泄漏
```

## 12. Tests

```text
Backend: **825 passed + 2 skipped（零失败）**（=K.25-S1 后 815+10
  K26：T1-T3 渐进 delta·T4 计时·T5 句段同一性[AAA。BBB。CCC。=>
  恰三段·无再切块]·T6-T8 引用/grounding 段级安全·T9 终局门拒
  诚实·T10 provider 失败零 delta·T11 分裂 ID·T12 reasoning 零
  转发·收敛性·非流式回退）
Web: 258+2（零前端改动）· TS: clean
Security: PASS · Streaming: 10/10 · Pilot: R1-R4 全 PASS
```

## 13. Known Limitations

```text
①R2 类长答案的最终门拒率不变（引用合规=D-04 轨道——流式只改
  展示不改门结果；已流内容按 K.20 失败契约保留+失败文案）
②glm 首 delta 前仍有 20-35s reasoning 期（provider 侧——该期间
  仅心跳/K.17 活性行；reasoning 不外流）
③held 段在最终门 PASS 前不可见（设计取舍：安全优先于完整流式）
④QA 引用门拒后 regen 循环的流式 delta 仍会发射（第二次尝试的
  验证句）——如最终仍拒，已流内容由 K.20 契约处理（如实）
```

## 14. Files Changed

```text
runtime/grounding/loop.py（adapter.generate_stream+句子级
  segmenter·移除 K.22 _emit_streamed 假切块）
runtime/llm/gateway.py（generate_stream 同治理+错误规范化+
  非流式 provider 回退）
tests/runtime/test_k26_streaming.py（新·10）
```

## 15. Owner Decision

```text
PASS——可进入正常 Pilot observation。后续可选：D-04 引用合规
校准（降低门拒率=提升可流式内容占比）。
```

STOP
