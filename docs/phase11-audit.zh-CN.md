# Phase 11 实施前架构审计

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](phase11-audit.md)

日期：2026-09-18 · 基线提交：`c294a33`（Phase 10 已冻结并推送）。

## 1. 运行时架构（审计时状态）

四个已冻结能力全部在位并通过测试：

- **Phase 7** —— 有界并行 DAG 调度器（`_run_parallel`、BSP 轮次、worker
  隔离、scheduler 独占提交）；`max_concurrency=1` 保持串行路径。
- **Phase 8** —— 动态重规划（确定性触发、不可变图修订、diff、预算、
  no-change 守卫）。
- **Phase 9** —— HITL 审批网关（`runtime/approval/`、fail-closed 状态机、
  Harness 独占恢复）。
- **Phase 10** —— HOTL 控制面（`runtime/control/`、确定性 monitor + 介入
  策略、可审计幂等命令）。

## 2. 当前测试数量

`pytest tests/runtime -q` → **293 passed**（Phase 9 前基线 248，经
Phase 9/10 增长）。完整回归 runner：**51 PASS / 0 FAIL / 1 pre-existing
INFRA_ERROR**（step3-mutation；Phase 7 housekeeping 会话中干净树复现；
cp936 控制台需要 `PYTHONIOENCODING=utf-8`）。

## 3. E2E 能力

并行与串行 4-Agent E2E 已存在（`test_parallel_4_agent_e2e`、
`test_true_4_agent_e2e`，真实 executor/引擎）；重规划 E2E 与审批 E2E
存在于 Phase 8/9 套件。此前**没有统一的 benchmark 框架** —— 这正是
Phase 11 的交付物。

## 4. Demo 能力

`demo.py demo-a/demo-b`（前 agent 时代的确定性流水线）与 web 聊天 UI。
没有分阶段 demo；没有纯状态输出的 trace summary。Phase 11 新增
`demos/`，六个一条命令即可运行的 runner。

## 5. Benchmark 能力

`evals/agent-benchmark/`（33 例 agent benchmark + golden、skill 变异
语言）早于多 Agent 运行时 —— 它考验的是确定性流水线，而不是
Planner/Harness/Replan/HITL/HOTL。Phase 11 为运行时本身新增
`evals/benchmark/`。

## 6. 故障注入能力

分散在各阶段测试套件（repair、approval、crash、actor 权限）。Phase 11
整合为声明式矩阵（`failure-injection/matrix.json`，18 行）并机器校验
预期。

## 7. Trace 能力

每个 project 持久的 `events.jsonl`、CaseState trace、checkpoint、
approvals/commands/alerts JSONL —— 全部在位。缺人类可读的 run summary；
Phase 11 新增 `run_summary()`（纯从持久状态推导）。

## 8. README 就绪度

双语 README + 完整文档体系（含快速开始）已在，但没有 benchmark/demo
说明，第一屏低估了运行时（偏向聊天机器人）。Phase 11 刷新第一屏并
补充可自行运行的章节。

## 9. 保险耦合点

领域词汇存在于：`.trae/skills/*`、`contracts/`、`catalog/`、
`knowledge/`、`runtime/insurance-analysis.yaml`、
`runtime/planner/registry.py`（任务目录）、`runtime/agents/registry.py`
（专家）、`runtime/agent/tools.py`，以及 `harness.py` 内的遗留
`TASK_DEFS` 映射（保持冻结、已记录）。通用模块（control、approval、
state、checkpoint、artifact 注册表、event bus、planner 引擎/校验器）
在代码层面无领域词 —— 由 `test_generalization.py` 结构性验证。

## 10. 可复用的通用运行时

可直接在保险之外复用：调度器、状态机、checkpoint、artifact 血缘、
eval 引擎机制（规则配置驱动）、消息总线协议、审批网关、控制面、
可观测性。更换领域 = 替换 registry/workflow/skills/contracts/catalog/
knowledge 包。见 `generalization.md`。
