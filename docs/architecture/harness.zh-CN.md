# 长运行 Harness

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](harness.md)

事实来源：`runtime/harness/harness.py`、`runtime/orchestrator.py`、
`runtime/state/`、`runtime/tasks.py`、`runtime/checkpoint.py`。

## 1. 定位

Harness 负责**何时**与**可靠性**：任务生命周期、依赖约束、调度（串行
或有界并行）、触发 Eval、repair、checkpoint、恢复、handoff 消费。它不
做任何保险判断，也不出让自己的权威：

- 只有 Harness 能设置 `PASSED / FAILED / NEEDS_REVIEW / BLOCKED`。
- 只有 Harness 运行 Eval（`_run_eval_and_repair`）与 Repair。
- 只有 Harness 写 checkpoint 与任务状态。
- Agent 只执行；MessageBus 只协调；任务图不可变。

## 2. 磁盘上的 project 模型

```text
<harness_root>/
  projects.json                    # 所有 project 的索引
  <project_id>/
    project.json                   # project 元数据 + 任务列表（状态、依赖、尝试次数）
    events.jsonl                   # 持久、只追加的 harness 事件日志
    checkpoints.jsonl              # harness 级 checkpoint 记录
    messages.jsonl                 # MessageBus 存储（A2A）
    case/
      case_state.json              # CaseState（stages、tasks、artifacts、evals、trace）
      artifacts/<type>.json        # 每个 artifact 单独一个可检视文件
```

运行进程在内存里拥有的一切都能从这份布局重建：**新的**
`LongRunningHarness` 实例（或进程）调用 `load_project()` + `resume()`
即可继续。

## 3. 任务状态机（project 层）

状态（与实现完全一致 —— `PENDING, RUNNING, PASSED, FAILED, BLOCKED,
NEEDS_REVIEW, COMPLETED`），全部迁移由 Harness 执行：

```text
PENDING ──调度──▶ RUNNING ──eval PASS──▶ PASSED        （正常终态）
   │                  │
   │                  ├──agent/eval 失败且 repair 耗尽──▶ NEEDS_REVIEW（终态）
   │                  └──worker 异常──▶ NEEDS_REVIEW     （终态）
   │
   ├──依赖 FAILED/NEEDS_REVIEW/BLOCKED──▶ BLOCKED        （终态）
   ├──分配非法──▶ BLOCKED                                 （终态）
   ├──未知 task_type──▶ FAILED                            （终态）
   └──磁盘上 stage 已 COMPLETED──▶ COMPLETED              （终态，跳过）
RUNNING ──进程中断 + resume──▶ PENDING                    （恢复：绝不当作 PASS）
```

- 终态意味着：不再重复执行（幂等），且已 checkpoint。
- 依赖为 `NEEDS_REVIEW`/`FAILED`/`BLOCKED` 时下游变 `BLOCKED` —— 失败
  向传播，绝不转成通过。
- 并行模式按轮次执行同一套语义；见
  [parallel-scheduler](parallel-scheduler.zh-CN.md)。

**stage 层状态**（CaseState 内）以 `PENDING / RUNNING / COMPLETED /
FAILED / NEEDS_REVIEW / SKIPPED` 的词表镜像；任务台账
（`runtime/tasks.py`）通过单一写路径（`set_status`）镜像 stage 状态，
`check_mirror()` 是被测试守护的不变量。

## 4. 执行模式

### 串行（`max_concurrency=1`，默认 —— Phase 6 路径）

按图序处理每个任务：确定性 agent 分配 + `validate_assignment` → 依赖
检查 → 幂等跳过（stage 已 COMPLETED、唯一 stage 去重）→ 执行（专家
agent 走 `SpecialistAgentExecutor`，或确定性参考运行时）→ Harness
eval + repair ≤ 2 → 终态 → checkpoint。之后有界 handoff 循环（≤ 5 轮）
消费消息并重跑被激活的 pending 任务。

### 并行（`max_concurrency > 1`）

轮次制（BSP）：计算 runnable 集合 → 填满 `max_concurrency` 个槽位 →
worker 在隔离的 CaseState 副本上执行 agent 任务（参考任务在 scheduler
线程执行）→ 轮次屏障 → **按图序提交**（merge artifact、重放 worker
事件、harness eval + repair、checkpoint）。完整细节见
[parallel-scheduler](parallel-scheduler.zh-CN.md)。

## 5. 持久化矩阵（对照代码验证）

| 组件 | 是否持久 | 机制 |
| --- | --- | --- |
| Project | 持久 | `project.json` + `projects.json` 索引 |
| 任务状态 | 持久 | `project.json` 内（状态、依赖、尝试、分配 agent） |
| CaseState | 持久 | `case/case_state.json`（每次 checkpoint 写入） |
| Artifacts | 持久 | `case/artifacts/<type>.json` + CaseState 内 |
| Artifact 注册表 / 血缘 | 持久 | CaseState 内（`artifact_registry`） |
| Eval / repair 记录 | 持久 | CaseState 内（`evaluations`、任务 `repairs`） |
| Checkpoint | 持久 | CaseState 的 `checkpoints[]` + `checkpoints.jsonl` 记录 |
| Harness 事件 | 持久 | 只追加的 `events.jsonl` |
| Trace | 持久 | `state["trace"]`（run root 另有 `trace.jsonl` 镜像） |
| MessageBus | 持久 | 追加/重写 `messages.jsonl` |
| EventBus（SSE） | **内存** | 发布/订阅总线；按需从 trace 重建 |
| RunManager 运行 | **内存** | 挂在持久 case 目录上的运行注册表 |
| 聊天会话 | **内存** | V0.1 `ChatManager`，刻意如此 |

## 6. 恢复

- `resume(project_id)` 可在**新进程**中工作：加载 project + 校验
  CaseState（`checkpoint.validate`：可解析、case-id 匹配、schema、
  注册表指纹校验、task→stage 完整性 —— 任何失败都是
  `CHECKPOINT_INVALID`，绝不从损坏状态静默恢复）。
- 已记录的恢复策略：中断时处于 `RUNNING` 的任务重置为 `PENDING`
  （事件 `task_recovered`）并重新执行 —— **绝不当作 PASS**。
  `PASSED`/`COMPLETED` 任务直接跳过，不再调用 agent、eval、artifact。
- 诚实的说明：这是**基于磁盘、跨进程的断点续跑**（测试通过从磁盘
  重载状态来模拟崩溃中断）。它不是分布式崩溃恢复，也不自称是。

## 7. 失败模型（检测 → 处理 → 终态）

| 失败 | 检测 | 处理 | 终态 |
| --- | --- | --- | --- |
| Planner 输出非法 | schema/图校验器 | 有界重试 ≤ 2，然后带出错误 | `needs_review` 计划（不执行任何任务） |
| Agent 执行失败 | executor 返回 `AGENT_FAILED`（步数上限、空响应、LLM 错误、输出非法） | 不做 eval；任务失败 | 任务 `NEEDS_REVIEW`，下游 `BLOCKED` |
| 工具失败 | 结构化工具结果（`status=failed/needs_review`） | agent 看到结构化错误；`needs_review` 终止本轮 | 轮次 `needs_review`（聊天）/ 任务 `NEEDS_REVIEW` |
| Eval FAIL | harness eval 记录 | repair ≤ 2：重跑 agent、重新 eval | PASS，或耗尽后 `NEEDS_REVIEW` |
| Repair 不适用 | `repair.plan()` 无动作 | 立即升级 | `NEEDS_REVIEW` |
| 依赖失败 | 依赖状态检查 | 下游永不启动 | `BLOCKED`（级联） |
| 分配非法 | `validate_assignment` | 任务不运行 | `BLOCKED` + `agent_validation_failed` |
| Worker 崩溃（并行） | worker 内异常 | 转为该任务的结果；其他任务不受影响 | 该任务 `NEEDS_REVIEW` |
| 合并时 artifact 冲突 | scheduler merge 中的指纹比对 | `MERGE_REJECTED` —— 绝不覆盖 | 任务失败，状态保持一致 |
| 消息非法/自发/越权 | MessageBus / handoff 校验 | 消息置 `FAILED`；运行不受影响 | 仅协调层面 |
| 进程中断 | 磁盘上缺失/悬空状态 | resume：`RUNNING → PENDING`，终态任务跳过 | 一致地继续 |
