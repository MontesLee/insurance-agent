# 路线图 —— 未来工作（未实现）

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](roadmap.md)

本页所有内容都是**未来方向**。今天代码库里都不存在；这份列表记录冻结
后的架构可能往哪里生长，并注明每个方向可以依托的既有接缝。

| 方向 | 状态 | 自然接缝 |
| --- | --- | --- |
| ~~动态重规划~~ **已于 Phase 8 V0.1 实现** —— 有界、Harness 控制、不可变修订（[dynamic-replanning](architecture/dynamic-replanning.zh-CN.md)） | 已实现 | 未来：`MISSING_REQUIRED_INFORMATION` 触发、轮次中重规划、人工审批门 |
| 图修订 / 基于运行反馈的 planner 重试 | 部分 —— Phase 8 已把运行结果（状态、触发原因）回流进受校验的重规划；通用反馈回路仍是未来工作 | `ReplanContext` 是接缝 |
| 持久外部队列（Redis/Kafka/…） | 未实现 | checkpoint/队列边界本就是文件形态；代码中没有任何队列客户端 |
| 分布式 worker | 未实现 | worker 隔离 + scheduler 独占提交是本地前身；没有网络层 |
| ~~人工审批~~ **审批网关已于 Phase 9 V0.1 实现**（[human-in-the-loop](architecture/human-in-the-loop.zh-CN.md)）—— 确定性策略、fail-closed 审批、Harness 独占恢复、最小 API | 已实现 | 未来：审批 UI 按钮、飞书适配器、TTL、拒绝→替代规划 |
| 飞书 / 外部通知 | 未实现（Phase 9 审批网关的未来适配器） | 审批事件 + API 是接缝 |
| 生产级长运行执行（服务、看护进程） | 未实现 | harness 是库；`python -m runtime.server` 是唯一常驻进程 |
| ~~监督者控制面~~ **已于 Phase 10 V0.1 实现** —— 确定性 monitor/信号/风险、介入策略、可审计监督者命令、pause/resume/retry/cancel/replan/人工输入（[human-on-the-loop](architecture/human-on-the-loop.zh-CN.md)） | 已实现 | 未来：飞书适配器、LLM 异常检测、TTL 告警、RBAC |
| 更丰富的知识源（外部语料、授权内容） | 未实现 | Evidence Provider 是唯一接缝；语料目前是本地演示库 |
| 保险之外的更多领域 | 未实现 | skills/contracts/catalog 就是可替换的领域包 |

以上任何一项都应继续遵守的约束：Planner/Agent/Skill/Tool/Harness/
Eval/Artifact 的分离、Harness 拥有 eval、处处 fail-closed 校验、以及
确定性提交。
