# Phase 9 —— 人工审批网关 V0.1

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](human-in-the-loop.md)

事实来源：`runtime/approval/`（models、store、policy、manager）、
`runtime/harness/harness.py`（审批部分 + `resume_approval`）、
`runtime/server.py`（审批 API）、`tests/runtime/test_approval.py`。

## 1. 为什么需要审批

自主执行系统需要一种可靠的方式，让人类对高影响决策保留最终控制
权。Phase 9 增加的是一个 **Runtime 控制面能力** —— 不是 Skill，也
不是 Agent 特性：

> Agent 可以请求人工判断；Planner 可以提出候选计划；Harness 是唯一
> 能暂停与恢复的层；人类是高影响变更的最终权威。

审批**不是** Eval：审批永远不能把 eval FAIL 变成 PASS。审批把关的是
*结构性变更*（图激活），永远不是*质量结论*。

## 2. 谁能做什么（权限边界）

| 层 | 请求 | 批准/拒绝 | 恢复/激活 |
| --- | --- | --- | --- |
| 人类（经 API/manager） | —— | ✔（actor 白名单：`human`） | —— |
| Harness | ✔（创建请求） | —— | ✔（仅 `resume_approval`） |
| Agent / 工具 | ✔（仅请求；V0.1 不产生 agent 发起的请求） | ✘ actor 白名单拒绝 + 无代码路径 | ✘ |
| Planner | ✘ | ✘ 拒绝 | ✘ |
| MessageBus | 仅协调消息 | ✘ 无代码路径 | ✘ |

由 manager 中确定性的 actor 白名单（`RESOLVE_ACTORS`）、代码构造
（agent/planner/bus 没有任何引入审批的路径）与测试（T4–T7）共同
保证。

## 3. 审批状态机（fail-closed）

```text
PENDING → WAITING_HUMAN → APPROVED → RESUMED        （仅 Harness 恢复）
                        → REJECTED                  （终态：fail closed）
                        → EXPIRED                   （终态：绝不继续）
```

- `EXPIRED` 存在但 V0.1 不设 TTL —— 过期只能显式触发。
- 非法迁移一律拒绝（PENDING 直接 → APPROVED、拒绝后再批准、恢复后
  再批准）。
- 批准在 `APPROVED` 上幂等；所有终态都是终态。

## 4. 确定性策略

`ApprovalPolicy.evaluate_replan(diff, project) → AUTO | HUMAN_APPROVAL`。
是机器计算的图 diff 的纯函数 —— LLM 永远不决定"这需要人工"。高影响
指以下任意一项：

- 新增任务数超过 `replan_added_threshold`（默认 2）
- 删除了任何任务
- 修改了任何依赖边
- 改动了已完成任务的后续路径

另外两类请求类型**保留、不产生**：`APPROVAL_EXTERNAL_ACTION`
（send_email / submit_application / call_external_api）与
`APPROVAL_HIGH_IMPACT`（最终产品推荐、重大方案变更、敏感数据操作）。

**默认关闭**：未安装 `approval_policy` 时一切 AUTO —— Phase 8 行为
逐字保留（有测试）。

## 5. 重规划 + 审批流

```text
replan 触发（Phase 8 语义不变）
   → Planner → Graph Validator（fail-closed）
   → ApprovalPolicy
        AUTO   → 修订经策略批准 → ACTIVE → 执行
        HUMAN  → 修订 PENDING_APPROVAL（候选不可变持久化）
                 → ApprovalRequest WAITING_HUMAN
                 → project 状态 waiting_approval —— 什么都不执行
                 → 人类 APPROVE → Harness resume_approval
                                   → 校验审批 + 修订
                                   → 激活 → checkpoint → 执行
                 → 人类 REJECT  → 修订 REJECTED、replan 台账 rejected；
                                  该 project 的重规划停止
                                  （fail closed —— 不再生成替代图）
```

**未批准的图绝不可能变成 active**：候选以 `pending_approval` 存在于
修订血缘中；只有在校验过 `APPROVED` 决定之后，`resume_approval` 才
激活它。

图修订生命周期现为：candidate → validated → `PENDING_APPROVAL` →
`APPROVED` → `ACTIVE`（或 `REJECTED`）；AUTO 路径记录
`approved_by: policy:auto`，人工路径记录 `policy:human`。

## 6. 持久化、checkpoint、恢复

- 每个 project 一个 `approvals.jsonl`（追加 + 重写，同 MessageBus）。
- checkpoint 记录携带 `approval_id` / `approval_status`；暂停时写入
  显式的 `WAITING_HUMAN` checkpoint。
- 等待期间崩溃：重启检测到阻塞审批后**什么都不执行** —— 不跑任务、
  不激活图（`run()` 返回 `waiting_approval`）。
- 已批准但未恢复同样阻塞普通 `run()`：显式的 Harness 恢复是唯一
  前进路径。
- 在其他进程（经 API）做出的拒绝，会在 Harness 下次接触时同步进
  replan 台账与图血缘。

## 7. 与并行调度器的兼容

审批恰好在 Phase 8 的重规划屏障上评估 —— 并行 pass 返回之后（所有
worker 汇合、已提交、eval/repair 完成）。worker 绝不会对着未批准的
图执行，因为等待期间根本不执行任何东西（`max_concurrency=2` 下有
测试）。

## 8. 可观测性与 API

事件：`approval_requested → approval_waiting → approval_approved |
approval_rejected | approval_expired → approval_resumed`（另有
`approval_failed` 表示被拒操作），全部携带 `project_id`、
`approval_id`、`graph_revision`、`timestamp` —— 只有结构化数据，没有
思维链。现有 SSE 事件流可以直接渲染。

最小 API（仅状态；执行经 Harness 恢复）：

```text
GET  /api/projects/{project_id}/approvals
GET  /api/approvals/{approval_id}
POST /api/approvals/{approval_id}/approve   {"actor": "human"}
POST /api/approvals/{approval_id}/reject    {"actor": "human", "reason": "..."}
```

项目在 `INSURANCE_AGENT_HARNESS_ROOT`（默认
`<run_root>/harness-projects`）下查找。approve/reject 幂等；非人类
actor 返回 409。

## 9. 当前限制

- V0.1 只自动产生 `APPROVAL_REPLAN` 请求；external-action 与
  high-impact 类型是保留壳。
- 无 TTL / 自动过期。
- 拒绝即停 —— 没有"拒绝 → planner 替代方案"回路。
- API 只做决定；恢复是库调用（`LongRunningHarness.resume_approval`）
  —— 还没有 UI 按钮。
- **飞书（以及任何外部通知渠道）是未来的适配器，不属于 Phase 9。**
- Phase 9 加固说明：串行路径现在也做崩溃恢复（`RUNNING → PENDING`），
  并跳过"有完成证据（stage 已完成或有输出 artifact）"的终态任务 ——
  堵上了 agent 模式重复 run() 会重复执行 PASSED 工作的潜在漏洞。
