# Agent 间通信（A2A）

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](a2a.md)

事实来源：`runtime/agents/message_bus.py`、`runtime/agents/handoff.py`、
`runtime/agents/registry.py`（通信策略）。

## 1. 定位

```text
Agent A ──send_agent_message──▶ MessageBus ──consume──▶ Harness ──调度──▶ Agent B
```

消息是**协调信号，不是持久事实**：agent 只引用 `artifact_id`（绝不复制
payload），总线校验并持久化消息，而决定接下来执行什么的是 Harness ——
永远不是总线。

> MessageBus 不替代 Harness 调度。它不是分布式 actor 系统；它是单进程
> 运行时内一条持久化、经过校验的协调日志。

## 2. MessageBus

- **持久化**：每个 project 一个 JSONL 文件（`messages.jsonl`）；跨重启
  存活；按 `message_id` 幂等（重复发送 = 无操作）。
- **消息类型**（封闭词表）：`TASK_HANDOFF`、`INFORMATION_REQUEST`、
  `INFORMATION_RESPONSE`、`REVIEW_REQUEST`、`REVIEW_RESPONSE`。
- **状态**：`PENDING → DELIVERED → ACKED` 或 `FAILED`。
- **发送时校验**（fail-closed `ValueError`）：发送者与目标都必须是注册
  agent；该方向必须被通信策略允许；类型必须在词表内；引用的
  `artifact_id` 必须存在于 CaseState 注册表。
- **发送者身份是结构性的**：工具 schema 没有 `from_agent` 参数；总线从
  executor 上下文拿到 agent id，LLM 无法冒充别的 agent。

## 3. 通信策略

由领域数据流推导（分析 → 证据 → 产品 → 报告）；反向与交叉路径一律
拒绝：

```text
insurance_analyst    → knowledge_specialist、product_specialist
knowledge_specialist → insurance_analyst
product_specialist   → report_specialist、insurance_analyst
report_specialist    → insurance_analyst
```

## 4. Handoff 生命周期（`consume_handoffs`，由 Harness 运行）

对每条 `PENDING`/`DELIVERED` 的 `TASK_HANDOFF`：

```text
校验：非自发消息 · 策略允许该方向 · task_id 存在
    · 任务在图中存在 · to_agent 与任务分配一致
    · 引用的 artifact 存在
    ↓ 全部通过
任务 PASSED/COMPLETED  → 消息 ACKED         （只有成功后才 ack）
任务 FAILED/NEEDS_REVIEW → 消息 FAILED       （失败绝不 ack）
任务 PENDING           → 发出 task_activated；Harness 仍会先检查依赖
```

每次运行有界（`MAX_HANDOFFS_PER_RUN = 20`）；handoff 处理失败不会中断
运行。

## 5. 消息永远做不到的事

- 创建任务或 agent，修改分配、依赖或图
- 启动 worker、绕过调度器、绕过依赖校验
- 跳过 eval，或携带 payload 内容（只允许 id）

这些性质由总线/handoff 校验器保证，并由
`tests/runtime/test_message_driven_scheduler.py` 与
`test_agent_communication.py` 覆盖。并行模式下，worker 经同一条总线
发消息（捕获式代理在提交时以确定顺序重放持久事件）。
