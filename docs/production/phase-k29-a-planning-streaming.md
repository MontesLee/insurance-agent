# Phase K.29-A — 规划路径 User-visible Streaming

Date: 2026-09-28 · 依据：Owner K.29-A 任务书（消除规划路径长时间无用户可见
内容；不做模型/WeKnora/并行/prompt 优化）。

## 1. Root Cause（§四 审计问答）

| 问 | 答案（代码实证） |
|---|---|
| Q1 哪个 LLM call 产生 tool_call 而非 content | 规划路径每步均 tool-calling 模式；**终答=agent_decide(action=finish, message=…) 的 tool-call 参数**（agent.py finish 分支） |
| Q2 该 call 是否支持真实 streaming | 是——provider `stream_generate` 逐 SSE 碎片下发（model.py:165） |
| Q3 delta 形式 | reasoning_content→reasoning；content→content；**tool_calls 参数碎片→原先被静默累积从不外发**（model.py:214-220） |
| Q4 是否等参数拼完才继续 | 是（dispatch 需要完整 args；本次改动不改变这一点——只是边拼边「旁路展示」） |
| Q5 终答为何无 content delta | ①GLM tool 模式中途 content 通道常为空（叙述在 reasoning，E-2 禁渲染）②finish 的 message 是 tool-call 参数碎片，provider 层只累积 |
| Q6 第一处真正用户内容 | 改前=终态 transcript（=T6）；改后=模型流出的 content 叙述（若有）+ answer 通道 |

## 2. Architecture Change（复用既有事件体系，零新架构）

```text
provider stream_generate
  └─ 新增 yield kind=tool_args {tool, text}（原生参数碎片，仅原始字节）
agent loop _generate_with_retry
  ├─ tool_args 碎片 → answer_stream.py JSON 感知增量扫描器
  │    （字符串/转义/深度状态机；截断安全；`message` 出现在别处字符串内不会误判）
  ├─ 仅 agent_decide 且 action=finish → message 可见前缀差分
  │    → emit agent_stream_delta {kind:content, channel:"answer"}（≤1200 字符，
  │       与 _clip(1200) 收敛一致）
  ├─ 其他工具参数：零外发（§七）；call_tool 的 message：不外发
  ├─ ask_user：不流式（基准实测发现其 schema 可能在部分流出后被拒——泄漏类，
  │     finish+message 本质自洽不会泄漏被拒草稿）
  └─ 重试 attempt>0：先发 reset 标记（消费端清缓冲，收敛到胜出尝试）
SSE（复用 transient 通道，不落盘不变）→ runReducer
  ├─ channel:"answer" → 消息位流式气泡（K.20 位置；终态由 transcript 收敛，
  │    步边界/agent_decision 不清 answer 流——防闪烁防重复，§十一）
  ├─ reset → 清气泡
  └─ 无通道 delta → 原有行为不变（步桶；QA 双视图）
```

## 3. Files Changed

| 文件 | 改动 |
|---|---|
| `runtime/agent/model.py` | stream_generate 增发 kind=tool_args 原生碎片（+8 行） |
| `runtime/agent/answer_stream.py`（新） | JSON 感知增量扫描器（scan_decide/visible_message） |
| `runtime/agent/agent.py` | _generate_with_retry 消费分流+finish 门控+reset（纯流式消费层，决策逻辑零改） |
| `runtime/obs/run_profiler.py` | delta 记录加 delta_channel 字段 |
| `web/src/state/runReducer.ts` | answer 通道分流至消息气泡+reset+步边界不清 answer 流 |
| 测试 | 后端 +14（answer_stream 7 + K.29 集成 7）；前端 +5（answer-channel reducer） |

业务决策/工具/技能/模型/prompt/WeKnora：**零改动**。

## 4. Event Flow（实测一例，浏览器验证轮 run_8da6ac89）

```text
agent_step_started ×11 ─ reasoning deltas 131 个（E-2 不渲染）
  └─ 终步: agent_decide args 碎片 → answer_stream 提取
       → agent_stream_delta{content, channel:answer} @108759ms
       → SSE @~108843ms（浏览器实测首见）
       → transcript 收敛 + run_completed @108958ms
```

## 5. Before / After（K.28 baseline vs K.29-A，各 3 runs/场景）

**模型行为逐轮分化（glm 采样方差）是第一解释变量**——如实分两型呈现：

| 型 | K.28（9 轮） | K.29-A（9 轮） |
|---|---|---|
| 叙述型（模型流 content 叙述） | **0/9 轮**（全程零 content delta） | **5/9 轮**：22-1765 个 content delta，首见 30.6s/40.4s/61.6s/89.5s/117.9s |
| 纯推理型（reasoning 到 finish） | 9/9：可见文本=终态 88-114s | 4/9：answer 通道点亮，但 glm 整块下发 finish 参数 → 首见≈终态（burst） |

| 指标 | K.28 baseline | K.29-A | 结论 |
|---|---|---|---|
| T3 首个用户可见流式文本 | **永不（=T6 88-114s）** | 叙述型 30.6-117.9s（5/9）；其余=answer burst≈T6 | 机制打通；可见性取决于模型当轮是否叙述 |
| T5 answer 通道首 delta | 不存在 | 9/9 点亮；41.1-109.8s，多数≈终态（glm 参数整块） | 真实流；打字效果依赖 provider 参数分片行为 |
| T6/E2E | C 92.0s·D 109.4s·E 75.6s（mean） | C 102.3·D 119.6·E 79.8（mean；D_1 needs_review 拉高） | **运行方差内不变**（见 §6 Q4/Q5） |
| TTFC 首事件 | 7.6-28.3ms | 9.9-18.8ms | 维持 |

浏览器实测（bridgic 驱动 :5273，规划问题）：活动管线 134ms 起可见→8 阶段
推进→8/8 产物→answer @108.8s→终态 109.0s（**SSE 递送滞后 84ms**）。
chatPerf marks：firstEvent=134ms·firstContent=108843ms·terminal=109042ms
（finalRender mark 未捕获——finalize 竞态，已知仪器缺口，不影响结论）。

## 6. 必答性能问题（§十五）

- **Q1** 首个可见内容：baseline=终态（88-114s）；K.29-A=叙述型 30.6-117.9s
  （5/9），纯推理型≈终态。**分母是模型行为方差，非机制缺口。**
- **Q2** 最终回答是否开始 streaming：**是**——answer 通道 9/9 真实点亮
  （provider 原生参数碎片，无任何伪造）。
- **Q3** 最终回答 first content delta：41.1s（E_1 短轮）至 ≈T6（多数——
  glm-4.7 服务端缓冲 tool-call 参数，整块下发；见 Q6）。
- **Q4** E2E 是否变化：**否**——均值在运行方差内（C +10s/D +10s/E +4s，
  D_1 一次 needs_review 拉高 D 均值；K.28 D_2 也曾 104s vs K.29 D_2 89.9s）。
- **Q5** **明确声明：本阶段解决的是 perceived latency（用户可见性），不是
  generation wall-clock latency。不声称性能优化成功。**
- **Q6** 80-114s generation wall-clock **仍然存在**（K.29-A D 墙钟
  89.8-133.7s；LLM 占比不变 ~95%）——profiling 数据在
  tmp/obs/perf-bench/{summary.json,analysis.txt}。

## 7. 回归（§十六）

- backend **852 passed + 2 skipped**（838+14）·web **319+2** ·tsc clean。
- QA 路径不变（无 channel → 原行为；测试覆盖）·非规划路径（legacy loop 同
  代码路径，决策逻辑零改）·终答不重复（气泡 gated on !terminalEvent +
  transcript 收敛；reducer 测试覆盖）·reasoning 不入气泡（E-2 保持；仅按
  Owner K.28 决策以独立段落入步盒）·tool arguments 不渲染（含 call_tool 的
  message；测试断言原文不在事件流）·步隔离不回归·transient SSE 不落盘。

## 8. 发现与修复的边界（基准期间）

1. **过早 ask_user 泄漏**（E_3：54.4s 处一次 schema 被拒的 ask_user 尝试
   message 先行流出）→ 修复：finish-only 门控（基准后落地，单测覆盖）。
2. glm-4.7 将 finish 参数**整块下发**（answer=单 delta burst）——服务端
   行为，客户端无从分片；如实记录，不做假打字。
3. 纯文本 finish（无 tool call 的终答）以 content 流入步盒（E_2 型 1765
   delta）——真实流式可见，但落位是步盒而非气泡（事中无法预知是终答）。

## 9. Remaining Bottlenecks（下一步候选，未实施）

1. **叙述稳定性**：模型当轮是否流 content 叙述方差大（0-1765 delta）——
   prompt 层引导（需 Owner 另阶段授权，§十八禁项）。
2. **glm 参数整块**：终答打字效果受 provider 参数分片行为制约。
3. generation wall-clock 本体（76-95% LLM）：K.28 Q8 候选②模型分层/①
   检索治理仍待 Owner 决策。
4. finalRender mark 竞态（仪器小缺口）。

## 10. 状态

**K.29-A COMPLETE — STOP**（按任务书 §十八：不继续换模型/优化 WeKnora/
并行/prompt/分层，等 Owner 裁决）。

原始数据：`tmp/obs/perf-bench/`（K.29）·`tmp/obs/perf-bench-k28/`（K.28
基线归档）·`tmp/obs/run-profiles/`（逐 run 时间线）。
