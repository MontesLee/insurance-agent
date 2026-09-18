# Resume bullets

> All numbers verified from the repo (v0.1.0): 326 tests, 11 benchmark
> cases, 18 fault injections, false-pass 0, two domains. No fabricated
> metrics.

## English — Agent Developer / Agent Engineer

- **Built a state-driven long-running multi-agent runtime** (planner with
  fail-closed graph validation, bounded-parallel DAG scheduler with
  worker isolation and deterministic commits, harness-owned eval with
  bounded repair, checkpoint/cross-process recovery, A2A message bus,
  dynamic replanning with immutable graph revisions) — validated by a
  deterministic benchmark: 11 scenario cases, 18 fault-injection
  scenarios, adversarial false-pass suite with 0 false passes, 326
  automated tests.
- **Designed human-control primitives for agent autonomy** — a fail-closed
  approval gateway (HITL) and a deterministic monitor/intervention control
  plane (HOTL) with audited idempotent commands and safe-barrier
  pause/resume — proving agents cannot self-approve, self-pass, or mutate
  runtime state, and humans supervise from outside the workflow DAG.
- **Demonstrated runtime generalization across domains** — the same
  planner/harness/scheduler/eval/artifact stack runs an insurance advisory
  pipeline (4 specialist agents, provenance-linked artifacts) and a
  software-engineering workflow via a ~40-line declarative domain
  adapter, with deterministic parallel-consistency (concurrency 1 vs 2
  identical results) and crash-recovery test evidence.

## English — Agent PM / AI Product Manager

- **Defined an agent product as a workflow, not a chat**: decomposed
  insurance advisory into 9 skills / 4 specialist agents with explicit
  tool and content boundaries (analysis may never reference products;
  only the catalog-backed layer may), turning product policy into
  machine-checkable eval rules instead of prompt guidance.
- **Designed the evaluation and failure-mode contract for a probabilistic
  system**: structured artifacts with provenance as acceptance criteria, a
  18-scenario fault-injection matrix defining required behavior under
  planner/agent/knowledge/human failures, and adversarial false-pass
  testing (0 false passes) as the product's definition of "did not
  hallucinate success".
- **Designed dual human-control UX for agent autonomy** (approval gates
  vs supervisory pause/notify/resume) and productized the system into a
  reproducible portfolio: one-command demos, bilingual docs, deterministic
  benchmark reports, and a versioned v0.1.0 release with a second domain
  demonstrated on the same runtime.

## 中文 — Agent 开发工程师

- **构建状态驱动的长运行多 Agent Runtime**：含 fail-closed 图校验的
  Planner、带 worker 隔离与确定性提交的有界并行 DAG 调度器、Harness
  独占的有界 Repair 评估、Checkpoint/跨进程恢复、A2A 消息总线、基于
  不可变图修订的动态重规划；以确定性 Benchmark 验证：11 个场景用例、
  18 个故障注入场景、对抗性 false-pass 测试 0 误通过、326 项自动化测试。
- **设计面向 Agent 自主性的人工控制原语**：fail-closed 审批网关
  （HITL）与确定性监控/介入控制面（HOTL），命令可审计、幂等、暂停仅在
  安全屏障生效——证明 Agent 无法自评通过、无法越权修改运行时状态，
  人在工作流 DAG 之上监督而非成为节点。
- **验证 Runtime 的跨领域通用性**：同一套 Planner/Harness/调度器/
  评估/Artifact 栈，通过约 40 行声明式领域适配器同时运行保险咨询
  流水线（4 专家 Agent、带溯源的 Artifact）与软件工程工作流；并行
  一致性（并发 1 与 2 语义一致）与崩溃恢复均有测试证据。

## 中文 — Agent 产品经理

- **将 Agent 产品定义为工作流而非对话**：把保险咨询拆解为 9 个
  Skill、4 个专家 Agent，明确工具与内容边界（分析层禁止出现产品、
  仅目录支撑层可推荐），把产品策略落成可机检的评估规则而非提示词。
- **为概率系统设计验收与失效契约**：以带溯源的结构化 Artifact 作为
  验收标准、以 18 场景故障注入矩阵定义各类失败下的必须行为、以
  对抗性 false-pass 测试（0 误通过）定义"未伪造成功"。
- **设计双轨人工控制体验**（决策审批门 vs 监督式暂停/通知/恢复），
  并完成作品化：一条命令的 Demo、双语文档、确定性 Benchmark 报告、
  v0.1.0 版本发布，并在同一 Runtime 上演示第二领域。
