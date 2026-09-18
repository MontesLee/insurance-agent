# Agent-to-Agent Communication

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](a2a.zh-CN.md)

Source of truth: `runtime/agents/message_bus.py`, `runtime/agents/handoff.py`,
`runtime/agents/registry.py` (communication policy).

## 1. Positioning

```text
Agent A ──send_agent_message──▶ MessageBus ──consume──▶ Harness ──schedules──▶ Agent B
```

Messages are **coordination signals, not durable truth**: agents reference
`artifact_id`s (never payload copies), the bus validates and persists the
message, and the Harness — never the bus — decides what executes next.

> The MessageBus does not replace Harness scheduling. This is not a
> distributed actor system; it is a persistent, validated coordination log
> inside a single-process runtime.

## 2. The MessageBus

- **Persistence**: one JSONL file per project (`messages.jsonl`); survives
  restarts; idempotent by `message_id` (duplicate send = no-op).
- **Message types** (closed vocabulary): `TASK_HANDOFF`,
  `INFORMATION_REQUEST`, `INFORMATION_RESPONSE`, `REVIEW_REQUEST`,
  `REVIEW_RESPONSE`.
- **Statuses**: `PENDING → DELIVERED → ACKED` or `FAILED`.
- **Validation on send** (fail-closed `ValueError`): sender and target must
  be registered agents; the pair must be allowed by the communication
  policy; the type must be in the vocabulary; referenced `artifact_id`s
  must exist in the CaseState registry.
- **Sender identity is structural**: the tool schema has no `from_agent`
  argument; the bus receives the agent id from the executor context, so an
  LLM cannot spoof another agent.

## 3. Communication policy

Derived from the domain data-flow (analysis → evidence → product → report);
reverse/diagonal paths are denied:

```text
insurance_analyst   → knowledge_specialist, product_specialist
knowledge_specialist → insurance_analyst
product_specialist  → report_specialist, insurance_analyst
report_specialist   → insurance_analyst
```

## 4. Handoff lifecycle (`consume_handoffs`, run by the Harness)

For each `TASK_HANDOFF` in `PENDING`/`DELIVERED`:

```text
validate: no self-message · policy allows the pair · task_id present
        · task exists in the graph · to_agent matches the task's assignment
        · referenced artifacts exist
    ↓ all valid
task PASSED/COMPLETED  → message ACKED          (ack only after success)
task FAILED/NEEDS_REVIEW → message FAILED       (never acked on failure)
task PENDING           → task_activated emitted; the Harness still checks
                         dependencies before anything runs
```

Bounded per run (`MAX_HANDOFFS_PER_RUN = 20`); handoff processing failures
never break the run.

## 5. What messages can NEVER do

- Create tasks or agents, or change assignment, dependencies or the graph
- Start a worker, bypass the scheduler, or bypass dependency validation
- Skip eval or carry payload content (ids only)

These properties are enforced by the bus/handoff validators and covered by
`tests/runtime/test_message_driven_scheduler.py` and
`test_agent_communication.py`. In parallel mode, workers send messages
through the same bus (a capture-only proxy replays the durable events at
commit, in deterministic order).
