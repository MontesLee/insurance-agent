# Phase 8 —— 动态重规划 V0.1

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](dynamic-replanning.md)

事实来源：`runtime/harness/harness.py`（重规划部分）、
`runtime/planner/planner.py`（`replan`）、`runtime/planner/prompts.py`
（`build_replan_prompt`）、`tests/runtime/test_dynamic_replanning.py`。

## 1. 为什么需要重规划

Phase 8 之前，任务图在 project 生命周期内固定不变：repair 耗尽或结构性
死路只能让 project 停在 `NEEDS_REVIEW`。真实运行会暴露原计划无法预知
的信息（某步无法成功、某条路被堵死）。Phase 8 允许 **Harness** 在严格
控制下向 Planner 请求新图：

> Harness 控制、有边界、带不可变图修订与确定性校验的动态重规划。
> 不是自主自改写。

中心规则不变：**Agent 执行图、绝不拥有图；Harness 拥有执行；Planner
拥有规划；重规划是一次受控的 Harness → Planner 操作。**

## 2. 触发策略（确定性）

`_evaluate_replan_trigger` —— LLM 永远不决定 `should_replan`：

- 预算未耗尽（`len(replans) < max_replans`，默认 2）
- 没有任务处于 `RUNNING`（安全屏障，R1）
- **TASK_BLOCKED**：至少一个结构性死路的 `BLOCKED` 任务
- **TASK_NEEDS_REPLAN**：repair 耗尽且**有下游依赖**的
  `NEEDS_REVIEW` 任务 —— 失败的叶子任务保持 `NEEDS_REVIEW`；
  `NEEDS_REVIEW` 绝不自动等于重规划（§9）
- 普通 eval 失败不是触发条件 —— 先走正常 Repair 路径；只有 repair
  耗尽才可能具备资格
- `MISSING_REQUIRED_INFORMATION` / `EXTERNAL_RESULT_CHANGED` 是可表达
  的类别，V0.1 不自动产生

## 3. 安全屏障（§7）

重规划只在**当前调度轮次完全结束之后**评估：并行模式在
`_run_parallel` 返回后（所有 worker 汇合、结果全部提交、eval/repair
完成）；串行模式在主执行遍与 handoff 循环之后。`_run_replan` 额外拒绝
（`UNSAFE_BARRIER`）任何 `RUNNING` 状态 —— 屏障之上的第二道保险
（T3 测试）。

## 4. 重规划操作

```text
安全屏障 → 触发 → ReplanContext（id、状态、artifact 摘要、触发原因、
                              历史 —— 绝不倾倒原始历史）
                  → planner.replan(provider, context)    # 同一套严格
                  → JSON schema + Graph Validator          # 流水线，
                  → 有界重试 ≤ 2                           # fail-closed
                  → 结构指纹（规范 JSON 的 sha256）
                       与当前图相同 → REPLAN_NO_CHANGE（循环停止）
                  → 作为不可变修订 v2 应用（合并语义）
                  → 记录图 diff + 事件
                  → 执行新的 PENDING 任务
```

- **图修订 / 血缘**：`project.graph_revisions[]` —— 不可变快照
  `{revision, parent_revision, trigger, planner_run_id, status,
  created_at, tasks, diff}`；修订 1 在创建 project 时快照。v1 绝不会
  被改写成 v2（R5，用快照相等性测试）。
- **合并语义**：同 `task_id` 且终态良好（`PASSED`/`COMPLETED`）→
  原样保留、绝不重跑（R6）；同 id 非终态 → 在新修订下重置为
  `PENDING`（记入 `diff.rerun`）；新 id → `PENDING`；v2 中不存在的
  v1 任务离开活动列表，保留在快照与 `diff.removed` 中。
- **任务身份**：跨修订使用任务 id（重规划 prompt 要求 Planner 对要
  保留的已完成任务复用原 id，其余铸造新 id）。新任务带
  `graph_revision_introduced`。
- **Artifact** 存在于 CaseState 而非图中：换图后原样存活，v2 任务可
  继续消费（R7，用血缘测试）。
- **Diff**（`_graph_diff`）：机器计算的
  `{added, removed, preserved, rerun, dependency_changes}` —— 绝非
  LLM 文本。

## 5. 预算、循环与失败

- `max_replans`（默认 2，`0` 关闭，校验 ≥ 0）：每次重规划尝试都计数；
  耗尽后 project 停在 `NEEDS_REVIEW`。
- 同构守卫：候选图与活动图的规范指纹相同 → `REPLAN_NO_CHANGE`
  （确定性哈希，不用 LLM）。
- Planner 失败（有界重试耗尽或 provider 错误）：`replan_failed`，
  fail-closed —— **没有兜底图、没有静默回退**；活动图与状态保持
  原样（R12）。
- 重规划期间崩溃：尝试记录在 planner 运行**之前**以 `in_progress`
  落盘；恢复时标记 `failed`（`INTERRUPTED…`），绝不假设成功（R11）。
  活动图只在一次 `project._save()` 内完成切换。

## 6. 事件

`replan_triggered` → `replan_started` →（planner 的
`graph_validation_*`）→ `graph_revision_created` →
`replan_completed` | `replan_failed`。全部携带 `project_id` 与
`replan_id` / `graph_revision` / `parent_revision` / `trigger` / diff
摘要 —— 只有结构化数据，没有思维链。`graph_revision_created` 在
project 创建时也会触发一次（`trigger=INITIAL`）。

## 7. 权限边界（未变）

- Agent：无法访问 planner、无法改图、够不到 `graph_revision` 与
  `max_replans`（结构性测试）。MessageBus 仍只做协调 —— 不能
  创建/修改任务，也不能触发重规划。
- 只有 Planner 产出候选图；只有 Graph Validator 让它变为可信；只有
  Harness 应用它。
- Eval 所有权未动：重规划绝不绕过 eval；新任务走同样的 Harness 所有
  的 eval + repair。

## 8. 兼容性

`max_concurrency=1` 保持 Phase 6 串行路径（handoff 循环后评估重规划）；
`max_concurrency>1` 在并行 pass 之间评估。Phase 6/7 测试套件全部原样
通过（248 个 runtime 测试）。

## 9. 当前限制

- 重规划发生在轮次**之间**，不在轮次中（设计如此）。
- V0.1 自动产生的触发类别只有 `TASK_BLOCKED` 与
  `TASK_NEEDS_REPLAN`。
- 合并按 `task_id` 识别已完成工作 —— v2 若用新 id 重新描述同一工作，
  会重新执行。
- 尚无重规划的人工审批门；`MISSING_REQUIRED_INFORMATION` 触发尚未
  实现（未来工作，见 roadmap）。
