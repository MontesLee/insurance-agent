# Phase 28.K.28 — Chatbot End-to-End Latency Profiling

Date: 2026-09-28 · 性质：**Instrumentation + Measurement + Diagnosis ONLY**
（Owner 任务书明确禁止优化；本阶段零业务逻辑/prompt/模型/步骤/超时/缓存
变更）。

## 1. 交付物

- **`PERFORMANCE_PROFILE.md`（仓库根）** — 完整档案：E2E/TTFC/TTFT、
  逐案例分解、四类归因、Top-5、Critical Path、Q1-Q8 结论、下一阶段候选。
- `runtime/obs/run_profiler.py` — 总线旁路 per-run 时间线记录器（亚毫秒
  到达时间戳·durable+transient·fail-quiet·落盘 tmp/obs/run-profiles/）。
- `tools/perf/benchmark_chat.py` + `analyze_profiles.py` — 5 场景 ×3 基准
  驱动（浏览器同构路径）+ 三源合并分析器（独占时长分桶·嵌套工具·双形态
  工具名·终态按列表位置）。
- 前端 `web/src/perf/chatPerf.ts` + 3 处一行接线 — Performance marks
  （submit/首事件/首 content/终态/终态渲染→sessionStorage+console）。
- 测试：profiler 8 个（电池内）·chatPerf 3 个（vitest）。

## 2. 核心测量结果（15 runs·真实 GLM+WeKnora·:8123 pilot）

| 案例 | E2E P50/P95 | 主构成 |
|---|---|---|
| A 简单问答（拒答） | 4.34s / 4.36s | knowledge_search 4.3s（99.4%） |
| B 知识问答（终门拒） | 33.0s / 34.7s | LLM×2 82-88% + 检索 4.3s |
| C 家庭分析 | 88.1s / 95.9s | agent 环 LLM 94-95% |
| D 完整报告 | 110.4s / 113.7s | 10-12 步 LLM 90-95% |
| E 长对比（实走规划） | 79.9s / 87.5s | LLM 76-93% + 检索 1-5 次 |

- **TTFC 7.6-28.3ms 全场景**（P0 ≤1-2s 达标）；网络+SSE 5-20ms。
- **瓶颈=LLM 生成墙钟（76-95%）**；WeKnora 检索固定 4.25-4.47s/次
  （零命中付满）；编排/工具/前端合计 <1%。
- **规划路径 0 content delta**（终答=tool-call 参数不流式；reasoning 按
  E-2 不渲染）→ 用户可见文本=终答 88-114s——P1 最大单一事实，同时解释
  Owner 早前「30s 无 streaming」观察。
- 单线程顺序执行：Critical Path=墙钟（span 记账闭合 ±50ms）。
- E2E<10s 需减 D P95 −103.7s（-91%）——参数级不可达，需 ①终答流式化
  ②模型分层 ③检索治理 组合（候选表见档案 §6 Q8）。

## 3. 执行纪律记录

- 唯一业务文件改动：`runtime/server.py` +2×3 行 profiler attach（纯观察
  ·fail-quiet·已在文档说明 Why/Minimal/Impact）。
- 失误 1 次（已修正+留教训）：测试电池与基准并发 → 电池 fake/mock 网关
  污染共享 tmp/obs/agent.jsonl 的 C/D/E 窗口；权威数据（总线 profiler）
  不受影响；A/B 窗口干净且与 obs 精确互证（B_1: 15257.5+13447.7ms =
  28707ms 跨度）。
- 分析器 3 个推导 bug 当场修复（工具名 skill/data.tool 双形态·同名工具
  跨步误配对→区间游走·嵌套工具→独占分桶）；profiler 修 1（同双形态）。
- pilot :8123 经 Owner 两次授权重启（加载 profiler）；probe-alpha
  synthetic 身份与真实用户台账隔离。

## 4. 验证

- backend **838 passed + 2 skipped**（829 基线 + profiler 8 + 1 skill
  形态）·web **283+2** ·tsc clean。
- 15/15 基准 run 完整落盘；记账闭合（独占和+未归因 ≈ 墙钟 ±50ms）。

## 5. 状态

**COMPLETE — STOP（按任务书：不做优化，等 Owner 决策下一轮）。**
