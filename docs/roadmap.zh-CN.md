# 路线图 —— 未来工作（未实现）

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](roadmap.md)

本页所有内容都是**未来方向**。今天代码库里都不存在；这份列表记录冻结
后的架构可能往哪里生长，并注明每个方向可以依托的既有接缝。

| 方向 | 状态 | 自然接缝 |
| --- | --- | --- |
| **动态重规划** —— 运行时依据 eval 结果/新事实修订 Task Graph | 未实现（Phase 8 候选） | 图目前已经端到端不可变；replanner 应是 Planner 与 Harness 之间一个独立校验的新阶段，仍不得改动执行中的图 |
| 图修订 / 基于运行反馈的 planner 重试 | 未实现 | `PlannerResult` + 校验器已 fail-closed；运行结果尚未回流 |
| 持久外部队列（Redis/Kafka/…） | 未实现 | checkpoint/队列边界本就是文件形态；代码中没有任何队列客户端 |
| 分布式 worker | 未实现 | worker 隔离 + scheduler 独占提交是本地前身；没有网络层 |
| `NEEDS_REVIEW` 任务的人工审批 UI | 部分：状态与门已存在；审批目前是程序化的（`orchestrator.approve`） | 任务状态与事件已建模 review；没有审批界面 |
| 飞书 / 外部通知 | 未实现 | —— |
| 生产级长运行执行（服务、看护进程） | 未实现 | harness 是库；`python -m runtime.server` 是唯一常驻进程 |
| 更丰富的知识源（外部语料、授权内容） | 未实现 | Evidence Provider 是唯一接缝；语料目前是本地演示库 |
| 保险之外的更多领域 | 未实现 | skills/contracts/catalog 就是可替换的领域包 |

以上任何一项都应继续遵守的约束：Planner/Agent/Skill/Tool/Harness/
Eval/Artifact 的分离、Harness 拥有 eval、处处 fail-closed 校验、以及
确定性提交。
