# 架构总览

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](overview.md)

本文按仓库实际实现描述系统。**代码是事实来源**；文中每一条结论都对照
过当前实现。

## 1. 这个项目是什么

一个 **Agent Runtime / Harness 工程项目，以保险分析领域作为示范**。
保险流水线（事实 → 需求 → 风险 → 缺口 → 方案 → 产品 → 报告）是示范
负载；工程贡献是 LLM 周边的执行系统：

> 一个可靠、状态驱动、Eval 把关、可观测、可恢复、有界并行的 Agent
> 执行系统 —— 而不是一个聊天机器人。

两个入口层驱动同一个运行时：

- **交互式聊天**（`runtime/agent/`、`runtime/server.py`）：有界 agent
  循环（`run_agent_turn`），带意图路由与工具调用。React UI 走的是这条路径。
- **程序化长运行 project**（`runtime/harness/`）：Planner → Task Graph →
  Harness → 专家 Agent。这一层是库，由代码/测试驱动（见
  `tests/runtime/`）；checkpoint、DAG 调度、A2A 协调都在这一层。

## 2. 定义架构的职责分离

| 角色 | 回答的问题 | 实现位置 |
| --- | --- | --- |
| **Planner** | 做什么 | `runtime/planner/` —— LLM 计划 + 严格校验 |
| **Agent** | 谁来做 / 怎么做 | `runtime/agents/registry.py`（专家）、`runtime/agents/executor.py` |
| **Skill** | 可复用的领域能力 | `.trae/skills/*`（9 个，各自带契约与 eval） |
| **Tool** | 可执行的能力接口 | `runtime/agent/tools.py`（面向 agent，Schema 校验） |
| **Harness** | 何时 / 执行控制 / 可靠性 | `runtime/harness/harness.py` + `runtime/orchestrator.py` |
| **Eval** | 结果是否满足质量约束 | `runtime/eval_engine.py`（+ `runtime/repair.py`） |
| **Artifact** | 持久结果 / 事实来源 | `runtime/artifact_registry.py`、`runtime/state/` |
| **Message** | 协调信息 —— 永不是持久事实 | `runtime/agents/message_bus.py` |

这些分离是**刻意设计**：

- Planner 不能发明能力 —— task_type 只能来自受信注册表；LLM 输出视为
  不可信，校验 fail-closed。
- Agent 不能决定并行、建任务、改图，也不能自评 PASS。只有 Harness 运行
  Eval 并判定 PASS/FAIL。
- agent 模式下工具不做 Eval（`skip_eval=True`）；先存 artifact，由
  Harness 评估。
- Artifact 是持久事实；Message 只做协调，永不替代 Artifact。

深入阅读：[planner](planner.zh-CN.md) · [harness](harness.zh-CN.md) ·
[并行调度器](parallel-scheduler.zh-CN.md) · [agents](agents.zh-CN.md) ·
[a2a](a2a.zh-CN.md) · [eval](eval.zh-CN.md) ·
[artifact 与溯源](artifacts-and-provenance.zh-CN.md) ·
[保险领域](insurance-domain.zh-CN.md)

## 3. 端到端流程

```text
用户
 ↓
意图路由（agent_decide，每轮首个决策）
 ↓  GENERAL_KNOWLEDGE / GENERAL_GUIDANCE / PRODUCT_LOOKUP → 直接回答，
 ↓  不进入客户建档，也不跑完整咨询流水线
 ↓  CLIENT_ADVISORY → 个人规划；TASK_EXECUTION → 基于已有数据执行某步
 ↓
Planner（LLM，重试 ≤ 2）               runtime/planner/planner.py
 ↓ 严格 JSON Task Graph
Graph Validator（10 项检查, fail-closed） runtime/planner/validator.py
 ↓ 可信图（字段从受信 Task Registry 填充）
长运行 Harness                          runtime/harness/harness.py
 ↓ 不可变任务图 + 落盘 project
Scheduler（max_concurrency，默认 1）
 ↓  串行路径 | BSP 轮次：runnable 集合 → 有界 worker
专家 Agent                              runtime/agents/
 ↓ 工具 → artifact 候选（skip_eval）
scheduler 独占提交（并行模式）           按图序 merge + 事件重放
 ↓
Eval（Harness 所有）                    runtime/eval_engine.py
 ↓ PASS → checkpoint、下一批 runnable   FAIL → Repair ≤ 2 → 重试 → Eval
 ↓ 耗尽 → NEEDS_REVIEW，下游 BLOCKED
Artifact + 血缘 + 溯源                  runtime/artifact_registry.py
 ↓
报告 / 用户可见结果
```

## 4. 意图路由（对照 `runtime/agent/schemas.py` 验证）

聊天 agent 通过结构化 `agent_decide` 决策对每一轮分类（枚举由 JSON
Schema 强制）：

```text
GENERAL_KNOWLEDGE   概念是什么 —— 定义、区别
GENERAL_GUIDANCE    一般性地该怎么考虑 / 怎么选
CLIENT_ADVISORY     针对用户自身情况的个人规划/推荐
PRODUCT_LOOKUP      具体产品 / 编号 / 术语
TASK_EXECUTION      基于已有数据执行某个具体步骤
```

设计意图（来自 prompt 契约，并有测试守护）：通用问题得到通用回答 ——
**不**进入客户建档；产品查询不要求完整客户档案。只有 `CLIENT_ADVISORY`
启动个人分析流水线；事实不足时 agent 会 `ask_user` 追问，而不是猜。

## 5. 执行模型

| 模式 | 路径 | 谁来 Eval |
| --- | --- | --- |
| 聊天 agent（`run_agent_turn`） | 有界循环，≤ 12 步，LLM 重试 ≤ 2，fail-closed | 工具运行确定性 skill（eval 在 stage runner 内）；eval 触发的 `needs_review` 会终止本轮 |
| 参考模式（确定性） | `orchestrator._execute_stage` —— 前 agent 时代的运行时 | stage runner 自身（eval + repair 在内部） |
| 专家 agent | `SpecialistAgentExecutor` → `ARTIFACT_READY` | **Harness**，经 `_run_eval_and_repair` |

Eval 所有权边界是统一的：executor 产出 artifact 候选即停；PASS 只由
Harness 判定。见 [eval.md](eval.zh-CN.md)。

## 6. 阶段史（工程演进）

| 阶段 | 交付 | 冻结产物 |
| --- | --- | --- |
| V2 Steps 0–4 | 契约、核心 skill、orchestrator、确定性 eval + repair、checkpoint | `contracts/`、`.trae/skills/`、`runtime/orchestrator.py`、ADR-001..007 |
| 2.5 / 2.6 | 运行时可观测（事件流、SSE）、聊天优先 agent、真实 LLM 模式 | `runtime/events.py`、`event_bus.py`、`runtime/agent/`、`web/` |
| 3 | 长运行 harness | `runtime/harness/` |
| 4 | planner + 注册表 + 校验器 | `runtime/planner/` |
| 5 | 多 Agent：专家执行器、确定性分配 | `agents/executor.py`、`registry.py` |
| 6 | A2A：MessageBus、handoff、通信策略 | `message_bus.py`、`handoff.py` |
| 7 | 有界并行 DAG 调度器 + housekeeping 冻结 | `harness.py`（`_run_parallel`）、`tests/runtime/test_parallel_*` |

各层按顺序冻结；每个阶段的回归至今仍在运行（`max_concurrency=1`
执行的仍是原样未动的 Phase 6 串行路径）。

## 7. 仓库结构（按架构边界）

```text
runtime/       Agent 运行时
  agent/       聊天 agent 循环、LLM provider 抽象、工具、意图
  planner/     planner、受信任务注册表、图 schema、校验器
  harness/     长运行 harness + 并行调度器
  agents/      专家注册表、执行器、消息总线、handoff
  state/       CaseState 容器、存储、状态迁移守卫
  （根文件）   orchestrator、eval 引擎、repair、artifact 注册表、
               checkpoint、events/event bus、FastAPI server
.trae/skills/  9 个保险 Skill —— 自包含（SKILL.md、CONTRACT.md、evals、
               入口脚本）；orchestrator 按声明路径加载
contracts/     每个 artifact 类型的规范 JSON Schema
adapters/      对话原生格式 → 规范 artifact 适配器
knowledge/     RAG 引擎 + 共享 Evidence Provider（溯源、fail-closed）
catalog/       演示产品目录（版本、生效日期、is_demo）
tests/         tests/runtime = pytest 套件；其余目录 = 独立脚本套件，
               由 tmp/run_regression.py 执行
evals/         系统级 benchmark（33 例）+ golden cases
web/           React/Vite 聊天 UI（SSE 流、开发者控制台、检查器）
docs/          本文档体系 + ADR + 开发笔记
```

## 8. 当前限制

- 单进程、基于线程的有界并行；无分布式 worker、无外部队列、无多节点协调。
- 并行调度是轮次制（BSP）：慢任务会让本轮的下游等到轮次屏障 —— 这是
  换取按图序确定性提交的代价。
- 持久化是磁盘 JSON；恢复是跨进程的磁盘断点续跑（测试中为模拟崩溃恢复），
  不是分布式崩溃恢复。
- 无动态重规划：执行期间任务图不可变。
- 演示产品目录（`is_demo`、虚构保险公司）与小型本地知识库 —— 没有真实
  保险数据，也未连接外部保险数据库。
- 已知测试基础设施问题：`step3-mutation` 套件报 INFRA_ERROR（干净树可
  复现）；回归 runner 在 cp936 控制台需要 `PYTHONIOENCODING=utf-8`。见
  [development/testing](../development/testing.zh-CN.md)。

## 9. 这个项目不是什么

- 不是分布式 Agent 平台。
- 不是生产级保险推荐系统，也不是真实保险产品数据库。
- 不是不受约束的全自主 Agent —— 每个扩展点都有校验、Eval 门禁与
  fail-closed。
- 不是 Kubernetes 级调度器、不是 Raft、不是分布式消息队列。

## 10. 未来方向（未实现）

见 [roadmap](../roadmap.zh-CN.md) —— 动态重规划、持久外部队列、分布式
worker、人工审批 UI、更丰富的知识源。全部明确标注为未来工作。
