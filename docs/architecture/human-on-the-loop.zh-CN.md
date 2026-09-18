# Phase 10 —— Human-on-the-loop 控制面 V0.1

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](human-on-the-loop.md)

事实来源：`runtime/control/`（models、store、monitor、policy、manager）、
`runtime/harness/harness.py`（控制面部分与门控）、`runtime/server.py`
（supervisor API）、`tests/runtime/test_human_on_loop.py`。

## 1. HITL 与 HOTL —— 本阶段的核心区别

```text
HITL（Phase 9）：某个具体动作/图【需要】人工决策。
    任务 → 审批门 → WAITING_HUMAN → 人决定 → 继续。

HOTL（Phase 10）：人作为监督者【位于工作流 DAG 之上】。
    Agent 默认自主执行；确定性 monitor 持续观察运行健康；只有确定性
    阈值才通知或暂停。
```

**人在 DAG 之外。** 正常执行永远不等人；人随时可以观察，并在确定性
运行时策略认为值得介入时介入。

## 2. 架构

```text
                         HUMAN（监督者）
                           │
                   ┌───────┴────────┐
                   │  Control Plane │  observe / pause / resume / retry /
                   │                │  replan / cancel / information /
                   └───────┬────────┘  approve / reject
                           ↓（命令【先审计】，由 Harness 应用）
                     ┌───────────┐
                     │  Harness  │
                     └─────┬─────┘
                    DAG 调度器（串行 / 有界并行）
                           ↓
                      Agent → Artifact → Eval → Replan
                           ↓
                  RuntimeMonitor（只做确定性观察）
                           ↓
               信号 → 运行时风险 → InterventionPolicy
                           ↓
             NONE / NOTIFY / PAUSE / WAIT_APPROVAL
```

职责分离保持不变：Planner = 做什么 · Agent = 怎么做 · Harness = 执行 +
控制 + 恢复 · Eval = 质量 · Artifact = 事实 · MessageBus = 协调 ·
Approval（Phase 9）= 显式人工审批边界 · Monitor = 观察运行健康 ·
ControlPlane = 人工介入边界 · Human = 监督者。

## 3. Monitor（确定性；绝不咨询 LLM）

`RuntimeMonitor.observe(project, events)` 是持久状态 + 事件日志的纯
函数。信号（V0.1）：

| 信号 | 严重度 | 确定性来源 |
| --- | --- | --- |
| `SIGNAL_TASK_FAILURE` | MEDIUM | 任务 FAILED / NEEDS_REVIEW（含失败的重规划） |
| `SIGNAL_REPAIR_EXHAUSTED` | MEDIUM | 失败任务 attempts ≥ 3 |
| `SIGNAL_REPLAN_EXHAUSTED` | HIGH | 重规划预算耗尽且存在未成功的尝试 |
| `SIGNAL_REPLAN_NO_CHANGE` | MEDIUM | 重规划复现了同一张图 |
| `SIGNAL_BUDGET_EXCEEDED` | MEDIUM | 任务/修复计数超过配置预算 |
| `SIGNAL_LONG_RUNNING` | MEDIUM | 任务 RUNNING 超过陈旧阈值 |
| `SIGNAL_REPEATED_FAILURE` | HIGH | 同一任务 ≥ N 次 task_failed（事件日志） |
| `SIGNAL_GRAPH_CHANGE_HIGH_IMPACT` | HIGH | 直接复用 Phase 8 的图 diff |
| `SIGNAL_INTEGRITY` | CRITICAL | 悬空依赖 / 无与 current_graph_revision 匹配的 active 修订 / 未知任务状态 |

运行时风险汇总：LOW < MEDIUM < HIGH < CRITICAL（取最高严重度）。
**这些是运行时执行风险，不是保险业务风险** —— 与领域里的 R1–R5 客户
风险类别无关。

去重 / 防事件风暴（§34/§35）：每个信号有稳定指纹（项目、类型、任务、
图修订、相关状态）。同一指纹的 OPEN 告警绝不重复创建、绝不重复通知；
条件消失的告警会 RESOLVED；历史性为真的信号（已应用的图变更）保持
OPEN 直到人工通过 RESUME 确认。RESUME 会持久记录已确认的指纹 ——
持续存在但已被人工复核的信号不会立刻再次暂停运行时；而真正变化的
状态会产生新指纹并再次触发。

## 4. 介入策略（确定性）

```text
LOW      → NONE        （自主继续）
MEDIUM   → NOTIFY      （持久化通知；执行继续）
HIGH     → NOTIFY      （可配置，如 high="PAUSE"）
CRITICAL → PAUSE       （在安全屏障执行）
```

另有 **WAIT_APPROVAL**：只要 Phase 9 审批门已在等待 —— 审批边界优先
于监督者通知。该策略不替代 ApprovalPolicy：ApprovalPolicy 判断
【某个具体图/动作】是否需要审批；InterventionPolicy 判断【运行时当前
状态】是否需要人工关注。

## 5. 控制命令（可审计、幂等、由 Harness 应用）

`ControlPlane.command(...)` 先持久化命令（`control_commands.jsonl`），
然后由唯一执行者 Harness 校验、变更状态、checkpoint 并发事件。命令
绝不直接改状态（§5/§32）。命令指纹包含 actor 与 payload：完全相同的
重复命令返回原已应用记录（幂等）；未授权 actor 绝无法搭已应用命令的
便车。崩溃时挂起的命令（已持久化、未应用）会在 Harness 下次接触时
幂等恢复。

| 命令 | 语义 |
| --- | --- |
| `PAUSE` | 监督者暂停；有 worker RUNNING 时顺延到下一个安全屏障（PAUSING → PAUSED），绝不中途杀死提交 |
| `RESUME` | PAUSED → RUNNING；确认（acknowledge）导致暂停的告警（迟滞） |
| `RETRY_TASK` | 校验后的终态失败任务重试（存在、非 RUNNING/PENDING/terminal-ok、依赖满足）→ PENDING；由调度器决定 |
| `CANCEL` | fail-closed 的项目取消；全部历史保留 |
| `REPLAN` | 走【既有的】Phase 8 重规划器（校验器、修订、diff、预算、no-change 守卫） |
| `PROVIDE_INFORMATION` | 生成带溯源的 `human-input` ARTIFACT |
| `APPROVE` / `REJECT` | 委托给 Phase 9 审批管理器 |

## 6. 运行时状态与持久化

Supervisor 状态：RUNNING、PAUSING、PAUSED、RESUMING、COMPLETED、
FAILED、CANCELLED、**WAITING_HUMAN**（Phase 9 审批 —— 与 PAUSED 语义
不同）。每个项目持久化：`supervisor.json`（SupervisorState）、
`alerts.jsonl`、`notifications.jsonl`、`control_commands.jsonl`。
checkpoint 在【同一套】检查点系统中携带 supervisor 字段（状态/风险/
活跃告警/待处理介入/最后命令 id）。无外部存储（仅文件 JSON）。

## 7. 崩溃 / 恢复

- PAUSED 时崩溃 → 重启后不执行任何东西，直到 RESUME。
- PAUSE 已持久化但未应用时崩溃 → 幂等恢复只应用一次。
- RESUME / RETRY / REPLAN 命令同理（各自幂等）。
- 观察只发生在安全屏障（轮次边界 / commit + eval/repair 之后）——
  绝不在轮次中；Phase 7 worker 隔离未受影响。

## 8. 权限边界（§24）

Human → 观察 + 全部命令。Harness → 内部操作 + 命令应用。Agent → 只可
【请求】介入（以告警/通知记录的信号 —— `request_intervention`；绝不
能暂停或变更）。Planner → 只出候选图。Monitor → 只观察（结构上没有
命令面）。MessageBus → 只协调。由 Harness 命令执行器中的 actor 白名单、
代码构造与结构性测试共同保证。

## 9. API（经控制面；由 Harness 应用）

```text
GET  /api/projects/{id}/supervisor | /alerts | /notifications | /control-commands
POST /api/projects/{id}/control/pause | resume | retry | replan | cancel | information
```

Phase 9 的 `/api/approvals/*` 原样保留。API 只解析与创建命令 ——
HTTP → ControlPlane → Harness，绝不直接改状态。Agent 执行在 harness
运行时中继续（API 进程只应用状态层效果）。

## 10. 当前限制（V0.1 可接受）

飞书（以及任何外部通知渠道）是未来的适配器，将消费已持久化的
Notification 模型 —— 不属于 Phase 10。无 LLM 异常检测、无真实 token
核算（预算是任务/重规划/修复计数）、不自动终止 worker、无基于 TTL 的
告警、无多用户 RBAC、UI 极简（SSE 事件可渲染 supervisor 状态）。
SIGNAL_LONG_RUNNING 天然读取墙上时钟（不在确定性声明范围内）。
