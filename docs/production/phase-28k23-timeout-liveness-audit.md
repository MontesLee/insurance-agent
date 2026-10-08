# Phase 28.K.23 — End-to-End Timeout & Run Liveness Audit

Date: 2026-09-27 · AUDIT ONLY（零改动·零重启·零 synthetic·零测试修改）。

## 1. Status

```text
COMPLETE（全链路 timeout 图谱建立；Root cause=R3+R6+R7 → 综合 R9）
```

## 2. User-Visible Symptom

```text
「已理解你的问题」= run_started+intent_classified → understand=completed
「● 正在为你分析」= intent_classified 后 work=running（E-3 DTO 唯一
事件-backed 事实）——两行由事件驱动，在下一个事件到来前**自然
持续存在**。若 run 无 terminal→UI 永远停在 work=running+K.17
心跳（12s 起）。
```

## 3-4. Architecture Timeout Map / Inventory

| Layer | Component | Timeout | Scope | 证据 |
|---|---|---|---|---|
| Provider | WeKnora HTTP | 15s（health 5s） | 单次检索请求 | weknora.py:210/258 |
| LLM | LLMRequest.timeout_s=90（rules） | 90s/attempt | QA 生成请求 | qa-grounding-rules.yaml:76 |
| LLM | 网关钳制 min(req, gw.timeout_s) | 同 rules 单旋钮 | 每次 generate | gateway.py:101 |
| LLM | adapter 看门狗（墙钟） | =request.timeout_s=90 | 每 provider 调用 | grounding/loop.py:64 |
| LLM | agent 环 provider（httpx） | 60s **per-read**（非墙钟） | 每 OpenAICompat 调用 | model.py:111（timeout=60 httpx per-read） |
| Retry | gateway_max_retries=1 | 2 次/attempt | RateLimit 退避 1.5/4s | rules+K.7 |
| Retry | generation regen=1 | ≤2 attempts | 引用门失败再生成 | generate_grounded |
| Retry | agent LLM_RETRY=2·MAX_STEPS=12 | 有界 | agent 环 | agent.py:22-23 |
| **Run** | **无独立 deadline** | **ABSENT** | **整个 run 生命周期** | **全仓 grep 零命中**（无 watchdog/deadline/run_watcher；worker=daemon Thread 无 join/监控：server.py:521-522） |
| SSE | EventSource（浏览器） | 无应用层超时 | 连接 | useRunStream.ts（onerror→浏览器自动重连；无自设 deadline） |
| Frontend | UI 等待状态 | **ABSENT** | run 活动指示 | runReducer/AgentActivity 无 wall-clock 超时（K.17 心跳=提示非超时） |

## 5. Run Lifecycle Contract

```text
TERMINAL（server.py:73-80 _TERMINAL）：COMPLETED/NEEDS_REVIEW/
PAUSED_NEEDS_REVIEW→needs_review/WAITING_FOR_USER→waiting/FAILED/
BLOCKED→failed（经 run_completed/run_failed 事件+_set 终态）
NON_TERMINAL：queued/running
waiting/needs_review=终态（对话层可续，run 本身已闭合）✓
```

## 6. Terminal Closure Audit（11 路径）

```text
A 正常成功 → run_completed ✓（worker 正常路径）
B/C/D LLM 超时/错误/重试耗尽：
  QA 路径→llm_unavailable/citation_gate AnswerContext→run_completed
  （refused 也是 completed 终态）✓
  agent 环→_generate_with_retry 耗尽→AGENT_ERROR finish needs_review
  →run_completed(needs_review) ✓
E/F 工具失败/超时：knowledge_search 空结果→failed 返回→agent 继续/
  needs_review ✓；WeKnora 15s 超时→ProviderUnavailable→QA 拒答/
  agent 环 tool_failed→有界步数内闭合 ✓
G/H 证据/引用失败 → refused/completed 或 needs_review ✓
I needs_review → 终态 ✓
J **意外异常 → 闭合 ✓**：agent worker 外层 except→run_failed
  （CRASHED）+finally（server.py:892-912）；demo worker 同构
  （:438-445）。代码级确认：异常不逃逸 worker。
K/L 客户端断开/SSE 断 → run 不受影响（业务存活与传输解耦：
  worker 线程独立；断开后重连经 cursor 续读）✓（这是正确设计）
**唯一缺口=正常执行中的无限等待**：所有闭合路径都以"某层超时/
错误/完成发生"为前提——若 provider 挂起不返回（httpx per-read
60s 可被慢滴流无限续命；agent 环**无墙钟看门狗**——仅 QA 适配器
有），worker 线程可无限阻塞→run 永远 running。
```

## 7. Retry / Wall-Clock

```text
QA 最坏墙钟 ≈ 90×2(gateway)×2(regen) = 360s（有界·诚实失败）
Agent 环最坏 ≈ 12 步×(60s/读×慢滴流不确定+LLM_RETRY) = **无上界**
（httpx per-read 非墙钟+无 run deadline+无步间时限）
```

## 8. QA Path

```text
链路有界（§7）✓。K.22 _emit_streamed 复核：纯门后同步循环+
  try/except return（异常吞掉·不影响生成/终态·无 await——同步
  代码无 hang 面）——**K.22"emit 无害"声明验证成立**。
```

## 9. Agent-loop Path

```text
_generate_with_retry→stream_generate：**无墙钟看门狗**（对照 QA
adapter 的 28.B5.1 看门狗注释——agent 环未采用同模式）。慢滴流/
挂起 provider→阻塞可无限。终态闭合仅在"调用返回/抛错"后发生。
```

## 10. SSE / Consumer Path

```text
Case A backend 发 terminal→SSE 送达→前端 finalize ✓（既有测试）
Case B **backend 无 terminal→前端永不结束等待**：无 wall-clock
  兜底——stream-message/活性行/心跳持续，直到浏览器标签关闭。
Case C SSE 断开→run 继续（正确）；重连续读 ✓；但重连后若仍无
  terminal→同 Case B。
transport liveness（SSE/心跳）≠ business run liveness——**前者
  正常工作，后者存在无限期缺口**。
```

## 11. REAL_USER Historical Evidence

```text
4 条真实 run 全部到达终态（completed×3[QA_REFUSED/COMPLETED]·
waiting×1）——**历史零悬挂**。当前 bus=5 全终态。用户反馈的
"长时间无输出"与 K.21 已证的 128s QA 拒答轮匹配（有终态·慢），
而非无限悬挂；但架构缺口（§6 唯一缺口）真实存在，属未触发的
风险面。
```

## 12. Failure Matrix

| Failure | Component | Timeout? | Retry? | Terminal? | Consumer Feedback |
|---|---|---|---|---|---|
| Provider timeout | LLM | 90s(QA)/60s per-read(agent) | 2× | ✓（闭合） | 诚实拒答/needs_review |
| Provider error | LLM | — | 2× | ✓ | 同上 |
| Tool timeout | Tool | 15s(WeKnora) | agent 步内 | ✓ | 工具失败→有界路径 |
| Tool exception | Tool | — | — | ✓（agent 环） | 同上 |
| Evidence fail | QA | — | — | ✓ completed | 拒答文案 |
| Citation fail | QA | — | regen 1 | ✓ | 拒答文案 |
| Unexpected exception | Runtime | — | — | ✓ run_failed | 失败文案 |
| SSE disconnect | Transport | 浏览器重连 | — | N/A（run 独立） | 重连续读 |
| **Run hangs（provider 挂起）** | Runtime | **无** | N/A | **✗ 可永不终止** | **永久"正在分析"+心跳** |

## 13. Root Cause Classification

```text
**R9（多因）**：
R3 — LLM timeout 存在（QA 层）但 **Run-level timeout ABSENT**
（全仓无 deadline/watchdog；daemon 线程无监管）
R6 — 前端无 terminal 超时兜底（backend 永不终态→UI 永久等待；
  EventSource 无应用层时限）
R7 — 层间交互缺口：agent 环 httpx=per-read 60s（慢滴流无限续命）
  × 无墙钟看门狗（QA 有）× 无 run deadline × 无前端兜底=四层
  叠加的唯一未覆盖路径
```

## 14. Severity

```text
P2（非 P1——依据：历史零悬挂实证·不影响数据安全·不泄漏资源
[daemon 线程随进程回收]·可恢复[刷新/重连/服务重启]；但属
"用户可能永远得不到结果"的未触发风险面+长等待 UX 已实际发生
[128s+]）
```

## 15. Remediation Options（三层拆分·不实施）

```text
Layer1 Run Safety：run-level deadline（worker 外层墙钟监督→
  到期 run_failed[timed_out]·终态契约扩展）——根治理
Layer2 Execution Safety：agent 环 provider 调用加与 QA 同源的
  墙钟看门狗（消除慢滴流无限续命）·复核各层 retry 预算总和
Layer3 Consumer UX：前端 terminal 兜底（N 分钟无终态→可理解
  的"仍在处理/稍后查看"提示+可重试入口——非伪造失败）
三者独立授权·独立实施·Layer1+2 为根·Layer3 为兜底
```

## 16. What Must NOT Be Changed Yet

```text
K.17 心跳（≠timeout·仅为 liveness hint·维持）；K.20/K.22 流式；
一切 timeout/retry/契约——本审计仅记录 REMEDIATION_REQUIRED
```

## 17. STOP

```text
零代码/配置/测试改动·零重启·零 synthetic·零 REAL_USER 流量
```
