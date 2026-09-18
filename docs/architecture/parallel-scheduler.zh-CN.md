# Phase 7 —— 感知 DAG 的有界并行调度器

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](parallel-scheduler.md)

Phase 7 把 Harness 从**串行调度器**升级为**带并发上限、感知 DAG 的
调度器**，构建在冻结的 Phase 6.2.2 运行时之上。它只改调度，不改职责
边界：

```text
Planner      = WHAT          （不可变 Task Graph，未变）
Harness      = WHEN/CONTROL  （唯一的调度器 / 并发控制者）
Agent        = HOW           （只执行；绝不决定并行或 PASS）
Artifact     = TRUTH         （规范 schema 未变）
MessageBus   = COORDINATION （从不启动 worker，协议未变）
Eval         = QUALITY       （Harness 所有，严格度未变）
Checkpoint   = RECOVERY      （每个终态，基于磁盘）
```

## 配置

```python
LongRunningHarness(root, agent_executor=..., max_concurrency=1)   # 默认
```

- `max_concurrency=1`（默认）—— 走 Phase 6 **串行**路径，逐字节不变。
  Phase 6 的全部行为（消息驱动 handoff、eval 边界、repair、
  checkpoint/恢复、4-Agent E2E）都保持。
- `max_concurrency >= 2` —— 任务图中的独立任务**并发**执行（基于线程
  的 worker 池）。非法值（`0`、`-1`、非整数）在构造时立即失败。

## 调度模型

`Harness.run()` 内部的轮次制（BSP）循环：

1. **runnable 集合** —— 依赖全部 `PASSED`/`COMPLETED` 的 `PENDING`
   任务，按稳定图序排列。依赖为 `FAILED`/`NEEDS_REVIEW`/`BLOCKED` 的
   任务终态化为 `BLOCKED`。
2. **有界填充** —— 每轮最多 `max_concurrency` 个槽位；一个任务绝不
   会同时出现在两个 worker 里（`running_task_ids` 台账 + `RUNNING`
   状态）。
3. **隔离执行** —— agent 任务在 worker 线程中对 CaseState 深拷贝执行；
   参考（确定性运行时）任务在 scheduler 线程对主状态执行（Phase 6 的
   代码路径）。worker 绝不写共享的 project/状态/checkpoint。
4. **按图序提交** —— 轮次屏障之后，scheduler（唯一写者）按图序提交：
   通过规范的 `put_artifact` + `artifact_registry` 路径合并 artifact
   （无论线程时序如何，`ART-`/`EVAL-` 编号保持顺序且唯一）、重放
   worker 事件、运行 Harness 所有的 Eval + Repair（≤ 2）、设置终态、
   为每个终态 checkpoint。
5. **消息** —— 执行后消费 handoff，与 Phase 6 完全一致；MessageBus 仍
   不启动 worker。被 handoff 激活的任务走下一轮有界并行。

崩溃恢复：被中断进程遗留在 `RUNNING` 的任务恢复为 `PENDING`（记录
`task_recovered` 事件）—— 绝不当作 `PASS` —— 已终态的任务跳过、不重跑。

## 为什么用轮次（BSP）而不是持续填充

按图序提交要求确定的提交顺序：轮次屏障保证无论线程完成顺序如何，
artifact 编号、eval 编号、事件顺序都只由图决定（T20 用"多次运行
artifact_id 完全一致"验证这一点）。代价是慢任务会让本轮的下游等到
屏障 —— 这是一个明确的工程取舍。

## 诚实的范围

这是**单进程、基于线程的有界调度器**。不是分布式执行，不是生产级
集群调度器，也不是容错分布式系统：没有分布式 worker、没有动态重
规划、没有外部持久队列；恢复仍然是基于磁盘的 JSON checkpoint。

已知的不对称：并行模式下 `force_rerun` 只覆盖 stage 已完成的跳过，
不覆盖已 `PASSED`/`COMPLETED` 的任务 —— 幂等优先于 force-rerun
（有意的、已文档化的限制，不是 bug）。

测试：`tests/runtime/test_parallel_scheduler.py`（T1–T21 + 禁止
worker 自评 PASS + 探针"牙齿"测试）与
`tests/runtime/test_parallel_4_agent_e2e.py`（真并行 4-Agent E2E，
用阻塞探针在 LLM 循环内部证明重叠执行）。
