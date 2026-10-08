# PERFORMANCE_PROFILE.md — Chatbot End-to-End Latency Profile

Date: 2026-09-28 · Phase 28.K.28 · 性质：**Instrumentation + Measurement +
Diagnosis ONLY**（零优化、零业务逻辑改动、零 prompt/模型/步骤变更）。

测量环境：pilot 后端 `:8123`（controlled_pilot·真实 GLM glm-4.7·真实
WeKnora 127.0.0.1:8080·PG registry）·基准驱动 `tools/perf/benchmark_chat.py`
（httpx 客户端，按浏览器同构路径 POST 消息→SSE 追踪至终态）·
15 runs（5 场景 × 3 次，顺序执行）·probe-alpha 身份（synthetic，与真实
用户台账隔离）。

---

## 0. 方法与 Trace 体系

**统一 trace_id = `run_id`**（复用既有体系，未新建）：每轮 chat 请求一个
run_id，贯穿 Frontend（SSE 订阅）→ API（POST /messages 返回 run_id）→
Agent Runtime（所有 RuntimeEvent 携带）→ LLM/Knowledge（obs 记录可按
窗口 join）。

新增 instrumentation（全部纯观察，fail-quiet）：

| 层 | 文件 | 内容 |
|---|---|---|
| 服务端 | `runtime/obs/run_profiler.py`（新） | 每 run 一条总线旁路订阅：durable+transient 事件亚毫秒到达时间戳 → `tmp/obs/run-profiles/{run_id}.json` |
| 服务端 | `runtime/server.py`（+2×3 行 attach） | run 注册时挂 profiler（唯一业务文件改动） |
| 前端 | `web/src/perf/chatPerf.ts`（新）+ 3 处一行接线 | Performance marks：submit→首事件→首 content delta→终态→终态渲染；`sessionStorage["webui:perf:last"]` + console |
| 工具 | `tools/perf/benchmark_chat.py`、`analyze_profiles.py`（新） | 基准驱动 + 三源合并分析（客户端时钟 / 服务端单调钟 / obs jsonl） |

既有观测复用：intent 延迟（`intent_classified.data.latency_ms`）·知识检索
（obs `knowledge.search`）·QA 网关调用（obs `llm.call`）。

数据质量声明：
- **权威数据 = 总线 profiler**（独立进程时钟，逐 run 文件）。obs jsonl 的
  llm.call 佐证 join 仅 A/B 窗口干净——执行失误一次：测试电池与基准并发，
  电池的 fake/mock 测试网关写入了共享 `tmp/obs/agent.jsonl`（C/D/E 窗口
  污染；已识别、不影响总线数据；教训=基准期间禁止并发跑电池）。
- n=3 时 **P95=max**（如实标注，不做平滑）；统计含 min/max/mean/median。
- 客户端驱动不含 React 渲染时间（localhost 网络 <20ms 已含）；渲染级
  TTFC 可用前端 marks 在浏览器实测（工具已就位，本轮未采样——相对
  60-114s 的轮次，渲染为十毫秒级，不改变结论）。
- 分析期两个 bug 已修复并留测试：工具名双形态（agent-loop 顶层 `skill`
  vs QA 路径 `data.tool`）·工具嵌套执行（`product_candidate_provider` 内嵌
  `knowledge-search`）需独占时长分桶。

---

## 1. Executive Summary

目标基线：P0 首个可见反馈 ≤1-2s ·P1 首个有效内容 ≤3s ·P2 完整响应 <10s。

| 指标 | 实测（P50 / P95=max@n=3） | 判定 |
|---|---|---|
| **E2E**（submit→终态） | A 4.34s/4.36s ·B 33.0s/34.7s ·C* 88.1s/95.9s ·D 110.4s/113.7s ·E 79.9s/87.5s | 仅 A 达标（但是拒答） |
| **TTFC**（submit→首个事件到达） | 全部运行 **7.6–28.3ms** | **P0 达标**（40-100×余量） |
| 首个 LLM reasoning delta（不渲染） | 典型 3.2–3.5s；provider 首试失败时 15.3–19.3s | — |
| **首个用户可见文本** | QA 路径 9.0–21.7s；**agent/规划路径 = 终答时刻 88–114s** | **P1 大面积不达标** |
| 后端占比 | 网络+SSE 开销 5–20ms；后端墙钟 ≈ E2E | 瓶颈 100% 在后端 |

*C 的 3 次中 1 次为澄清问（WAITING_USER 21.9s）；completed-only 统计：
mean 92.0s / median 88.1s / max 95.9s。

**一句话结论：延迟几乎全部由 LLM 生成时间构成（76–95%），其次是每次
~4.3s 的 WeKnora 知识检索固定成本；编排/工具序列化/网络/前端合计 <1%。**

---

## 2. 真实调用链（审计确认，非推测）

```text
Composer.send (ChatLayout.tsx:121)
  → POST /api/chats/{id}/messages          [ack 4-16ms，异步执行]
  → EventSource /api/runs/{id}/stream      [首事件 8-28ms]
_agent_worker（单线程顺序执行——关键路径=墙钟，无并行可摊）:
  run_started
  → intent 层（rules-only shadow）          [实测 0-16ms]
  → 切片判定
  ├─ QA 切片: tool_started(knowledge_search) → WeKnora+治理 → tool_completed
  │   → gateway.generate_stream（glm 流式）→ 逐句引用门 → content deltas
  │   → qa_answered → _finish_run（sanitize+transcript 写入）
  └─ 规划/agent 环: 每步 agent_step_started → provider.stream_generate
      （reasoning deltas 流出·E-2 不渲染；终答=tool-call 参数·不流式）
      → agent_decision → tool_*（skill 执行）→ …12 步 → finish
  → run_completed（终态+transcript）
```

---

## 3. Per-Case 数据（15 runs）

### 分解总表（服务端墙钟 ms，独占分桶）

| run | 墙钟 | LLM | Knowledge | Tools | App | 未归因 | 结果 |
|---|---|---|---|---|---|---|---|
| A_1-3 | 4278-4350 | ~1 | 4275-4346 | 0 | ~0 | <3 | QA_REFUSED（G-1 零命中） |
| B_1 | 33011 | 28707 | 4300 | 0 | 0 | 4 | QA_REFUSED（流式部分句后终门拒绝） |
| B_2 | 34694 | 30391 | 4298 | 0 | 0 | 5 | 同上 |
| B_3 | 31293 | 26820 | 4467 | 0 | 0.1 | 5 | 同上 |
| C_1 | 95863 | 90753 | 4339 | 601 | 120 | 51 | COMPLETED |
| C_2 | 88060 | 82953 | 4362 | 564 | 133 | 49 | COMPLETED |
| C_3 | 21914 | 21783 | 0 | 33 | 84 | 14 | WAITING_USER（澄清） |
| D_1 | 110404 | 105421 | 4302 | 537 | 102 | 42 | COMPLETED（报告交付） |
| D_2 | 104168 | 99306 | 4250 | 474 | 96 | 41 | COMPLETED |
| D_3 | 113654 | 108674 | 4418 | 426 | 97 | 39 | COMPLETED |
| E_1 | 79914 | 67021 | 12791 | 0 | 84 | 18 | COMPLETED |
| E_2 | 87539 | 65937 | 21505 | 0 | 75 | 21 | COMPLETED |
| E_3 | 59202 | 54858 | 4252 | 0 | 74 | 18 | COMPLETED |

（未归因 <51ms = 线程调度/序列化/emit 等；span 独占和+未归因 ≈ 墙钟
±50ms，全链记账闭合。）

### 逐案例要点

**A 简单问答**（4.29-4.36s，全部拒答）：99.4% = 一次 knowledge_search
（4.28-4.35s，**零命中查询同样付满 4.3s**）；intent 0ms；无 LLM 调用。
G-1 语料缺失使最快场景以拒答收场——但延迟画像本身成立。

**B 需知识库**（31.3-34.7s，全部拒答但过程完整）：知识检索 4.3-4.5s →
glm 两次生成（首试 12.2-18.2s + 门败后重生成 9.3-13.4s；obs 精确印证
B_1：15257.5+13447.7ms = 跨度 28707ms）→ 终门仍拒。**content delta 在
9.0-21.7s 间流式到达**（10-15 句），最终被终门拒绝替换——用户先见流式
文本后见拒答（UX 议题，非本阶段范围）。

**C 家庭缺口**：completed 轮 12 步 agent 环，每步 LLM 4.4-19.4s；知识
检索 1 次 4.3s；app <135ms。C_3 澄清轮也花 21.9s（两次 10.6/11.2s LLM）。

**D 完整规划报告**（104-114s）：10-12 步；最慢单步 = step_2 需求分析
20.5-23.1s、step_11/12 终答/报告 18.4-22.8s；知识检索 1 次 4.3s。

**E 长对比分析**（59-88s，实际走规划路径而非 QA 长流式——意图分类结果
如此，如实呈现）：5-7 步；知识检索 1-5 次（E_2 含 2 次零命中失败仍各付
4.3s）；首 reasoning delta 3.4s（provider 首试失败轮 17.7-19.3s）。

### TTFT / 生成期（LLM 细目）

- QA 路径（网关 glm，obs 实证）：单次调用 9.3-18.2s（含 reasoning 期——
  glm 首 content 前有 20-35s reasoning 段的历史观察，本轮 B 首句 9-21.7s
  一致）。
- Agent 环（绕网关直连 provider，K.12 已知缺口；TTFT 由总线推导）：步起
  →首 reasoning delta 3.2-3.5s；步内生成（首 delta→步终）1-29s。
- 前端/网络：ack 4-16ms；SSE 递送滞后计入首事件 8-28ms；终态到达较服务
  端墙钟差 5-20ms。

---

## 4. Critical Path

每轮 = **单线程顺序执行**（span 独占和 ≈ 墙钟 ±0.1% 证实无并行段）：
**Critical Path = 墙钟时间**；无「并行掩盖」收益存在。

```text
D 案例（最重，110.4s 典型）:
submit ─16ms─ intent(0ms) ─ step1 LLM 10.5-18.2s ─ step2 LLM 21.2s
  ─ [记录工具 0.04s] ─ step3-10 LLM+工具 ~50s ─ knowledge_search 4.3s
  ─ step11 终答 LLM 20.6s ─ step12 报告 LLM ~5s ─ finalize 0.1s ─ 终态
```

四类耗时归因（墙钟占比，completed 轮均值）：

| 类别 | A | B | C | D | E |
|---|---|---|---|---|---|
| LLM | 0% | 82-88% | 94-99% | 90-95% | 76-93% |
| Knowledge/Retrieval | 99.4% | 12-14% | 4.9% | 4% | 5-25% |
| Tools/IO | 0 | 0 | 0.6% | 0.4% | 0 |
| App（intent+finalize+调度） | <0.1% | <2% | <0.2% | <0.2% | <0.2% |
| 网络/前端（客户端侧） | — | <20ms | <30ms | <20ms | <30ms |

---

## 5. Top 5 Slowest Operations（客观统计，15 轮汇总）

| # | 操作 | 单次耗时 | 说明 |
|---|---|---|---|
| 1 | agent-loop 单步 LLM（glm reasoning+生成） | 4.4–33.0s/步；单轮合计 54.9–108.7s | 规划路径总时延的主体 |
| 2 | qa_llm_grounding（glm 网关生成×2 次含重生成） | 26.8–30.4s/轮 | B 案例 82-88% |
| 3 | knowledge_search（WeKnora vector_search+治理） | **4.25–4.47s/次，固定成本**（零命中同样付满） | 每轮 0-5 次 |
| 4 | finalize_transcript（sanitize+写 transcript） | 0.07–1.28s（B 长答案最大） | 仅 B 显著 |
| 5 | 规划 skill 工具（record_*/solution/product_candidate 等） | 0.03–0.60s | 可忽略 |

---

## 6. 结论问答（Q1-Q8）

**Q1 完整响应时间？**
简单拒答 A：均值 4.33s（P50 4.34 / P95 4.36）。知识问答 B：33.0s（33.0/
34.7）。家庭分析 C（completed）：92.0s（88.1/95.9）。完整报告 D：109.4s
（110.4/113.7）。长分析 E：75.6s（79.9/87.5）。**全局 P95 = 113.7s（D）**。

**Q2 首个可见反馈？**
**7.6–28.3ms**（submit→首个 SSE 事件：run_started/intent，活动卡即刻有
内容）——P0（≤1-2s）**达标**。

**Q3 首个 LLM Streaming？**
- 内部 TTFT（首 reasoning delta）：典型 **3.2–3.5s**；provider 首试失败
  轮 15.3–19.3s。reasoning 按设计不渲染（E-2）。
- **用户可见流式文本（content delta）**：仅 QA 路径有，**9.0–21.7s**；
  **规划/agent 路径为 0——终答以 tool-call 参数返回、不经流式转发**，
  用户可见文本=终答（88–114s）。此为对 P1（≤3s）影响最大的单一事实。

**Q4 最慢的 3 个步骤？**
① 规划终答/需求分析单步 LLM（18–33s/步）② QA 首试+重生成 LLM
（26.8–30.4s/轮合计）③ knowledge_search 固定 4.3s/次。

**Q5 每步骤耗时？** 见 §3 分解总表与各案例要点（逐步 span 明细在
`tmp/obs/perf-bench/summary.json`·`analysis.txt`）。

**Q6 最大瓶颈类别？**
**LLM**（生成墙钟占 76–95%）。次要：Knowledge 固定 4.3s/次。Tool/
编排/后端处理/前端/网络合计 <1%——**不是**瓶颈。

**Q7 若目标 E2E<10s 需减多少？**
最重 D：P95 113.7s → 10s，**需减 ≈103.7s（-91%）**。C：-85.9s。
B：-24.7s。仅靠参数级调整不可达——LLM 生成时间本身（54.9-108.7s）已
超预算 5-11 倍，必须以「体验等价」路径响应（流式终答/分步交付/模型分层），
属下一阶段 Owner 决策。

**Q8 下一阶段优先优化候选（仅列出，不实施）：**

| 候选 | 预期影响 | 证据 | 风险 |
|---|---|---|---|
| ① 规划路径终答流式化（tool-call 参数增量转发，同 K.26 句级门控） | 用户可见文本从 88-114s → ~30-40s（首个 content 提前约 60-70s）；不改墙钟 | C/D/E 15 轮 0 content delta；step_11/12 18-23s | 引用门/卫生边界需同 K.26 三层防泄；终答为结构化参数，句级切分语义需设计 |
| ② LLM 分层（fast 模型承担常规续步/工具编排步） | 环内 10-12 步中约 8-10 步为低复杂度续步，若 4-6s→1-2s 可省 30-50s | D step3-10 合计 ~50s；fast_provider 机制已存在（agent.py 成本分层） | 质量/决策漂移需 B4 等价门校准；GLM fast 档可用性待验证 |
| ③ WeKnora 检索耗时治理（4.3s 固定成本：embedding/检索/治理拆分定位） | 每次 -2-3s（若 embedding 批处理/缓存命中）；每轮 1-5 次 | 12 次调用全部 4.25-4.47s 含零命中 | 依赖 WeKnora 服务端实现（127.0.0.1:8080），跨系统 |
| ④ provider 首试失败重试（D_3/E_1/E_3 首 delta 15-19s）的退避/预热 | 失败轮 P95 -10-15s | 3/9 规划轮首试失败 | 涉及重试策略=业务超时策略变更，需授权 |
| ⑤ G-1 语料治理（独立轨道） | 不改延迟，但 A/B 案例从拒答变真答 | A 3/3、B 3/3 零命中/终门拒 | 既有治理门槛（3 次真实用户零命中）已立项 |

（①+② 组合理论可达 D≈30-50s；<10s 仍需 ③④ 及模型侧根本改善——如实
陈述，不做无数据承诺。）

---

## 7. 完成标准核对

- [x] 统一 trace_id（复用 run_id，贯穿前后端）
- [x] 单次 chat 请求全生命周期可追踪（client_*.json + run-profiles/*.json）
- [x] 每个 Agent Step 有 duration（agent_step_N_llm spans）
- [x] 每个 LLM call 有 TTFT+总时长（QA=obs 实证；agent 环=总线推导，标注）
- [x] Knowledge Search 有 duration（4.25-4.47s×12 次）
- [x] Tool 有 duration（区间游走解析，含嵌套独占分桶）
- [x] Frontend 有 TTFC（marks 就位；驱动侧网络级 7.6-28.3ms）
- [x] Critical Path 可识别（顺序执行=墙钟；span 记账闭合 ±50ms）
- [x] ≥5 场景（A-E）·[x] 每场景 ≥3 次
- [x] P50/P95（n=3 P95=max 如实标注）
- [x] Top 5 slow operations
- [x] PERFORMANCE_PROFILE.md（本文件）
- [x] 原有测试全部通过（backend 837+2·web 283+2·tsc clean·profiler +8）
- [x] 零业务逻辑改动（唯一业务文件 server.py 仅 +2×3 行观察 attach）

**STOP：本阶段到此为止，不做任何优化。等 Owner 基于本档案决策下一轮。**

原始数据：`tmp/obs/perf-bench/`（client_*.json·summary.json·analysis.txt·
bench_full.log）·`tmp/obs/run-profiles/`（15 个服务端时间线）。
