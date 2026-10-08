# ADR-020 — Router Contract

## Status

**APPROVED (2026-09-25, Phase 28.0.5 owner ruling — 保持原文，无修改)**.
三层约束（schema contract + import boundary + CI tests）按原文生效。
依赖：ADR-019（IntentResult 唯一输入，已 APPROVED）、ADR-021（Registry
唯一 Agent 来源，已 APPROVED）。

## Context

现状：**Router 不存在**（27.9 全库 grep：无 intent→agent 分发组件；
"路由"由单 chat Agent 在 prompt 内自选工具完成，runtime/agent/prompts.py:
12-41——意图与工作流知识混在同一 prompt）。4 专家层是确定性
task_type→agent 映射（runtime/agents/registry.py:124-128），但那是执行
分派不是意图路由，且不在生产路径。ARCHITECTURE_PRINCIPLES §3 要求
Router owns routing only。

## Problem

目标链路 `Intent → Router → Agent` 中 Router 是缺失的一环；若不先立
契约，最可能的"自然实现"就是把业务语义塞进路由条件（现状 prompt 就是
前车之鉴：每意图直接写死工具链）。

## Decision

Router 是**纯查表组件**，全部职责 = `Intent → Agent`：

```
INTENT_AGENT_MAP = {
  insurance_qa        → insurance-qa-agent,
  product_qa          → insurance-qa-agent,        # catalog-first 路由在 Agent 内
  insurance_plan      → insurance-planning-agent,
  modify_existing_plan→ insurance-planning-agent,  # continuation 模式
  unknown_insurance_intent → conversation-agent,   # 澄清，非业务
}
route(IntentResult) → agent_id + route_selected 事件
```

**YES（允许）**：intent→agent_id 查表；fail-closed 兜底（unknown /
意图不在表内 / Registry 无此 agent → conversation-agent 澄清，**绝不
默认 planning**）；`route_selected` 审计事件。

**NO（禁止，均属契约违约）**：

- 保险业务逻辑（任何 if-else 带产品/风险/客户语义）
- Workflow 编排（知道任何阶段/步骤/skill 顺序）
- 知识检索（不碰 KnowledgeService/WeKnora/Catalog）
- 产品推荐（不碰候选/推荐引擎）
- 置信度再评分 / 意图再分类（那是 ADR-019 的事）
- LLM 参与路由（永久禁止）

模块依赖硬约束：router 模块只允许 import intent schema 与 Agent
Registry 接口（以 import 边界测试执行——决策表之外无依赖）。

## Alternatives considered

- **A. LLM Router（模型选 Agent）**——否决：非确定第一跳之后第二跳
  再非确定；LLM 将同时拥有"理解+分发"双权，违背 Principle 2/3 与
  ADR-019 规则 2。
- **B. 条件策略引擎路由（带业务条件的 policy engine）**——否决：条件
  里写业务语义的滑坡正是本契约要防的；查表已覆盖全部已知需求。
- **C. 维持"会话 Agent 内自选"（现状）**——否决：路由与工作流混层
  （漂移基线 P1），多 Agent 无从接入。

## Consequences

- 正：路由可穷举测试；新增 Agent 只改 Registry+表；审计事件齐全；
  "workflow leakage"哨兵有明确裁决点。
- 负：表达力受限（表无法表达"复合意图"——复合需求应由意图层澄清或
  Agent 内部处理，不为路由加条件）；conversation-agent 兜底体验需
  设计（承接 unknown）。
- 合规：ADR-017 不涉；ADR-004 不涉（无评估语义）。

## Implementation boundary

- 新增：router 模块（表+查表+事件）；import 边界测试。
- 依赖消费：IntentResult（ADR-019）、Registry 条目（ADR-021）。
- 冻结：一切业务模块对 router 的反向依赖为零；禁止 router import
  orchestrator/yaml/skills/knowledge。
- 实施阶段：28.A（与 019/021 同期，影子模式）。

## Migration strategy

随 28.A 影子模式上线（记录 route_selected 但不裁决）→ 28.C 起 QA 意图
真实路由 → 28.B 起全意图权威（chat Agent 的工具自选路径退役）。

## Validation criteria

- Unit：全表命中/unknown/表外意图/Registry 缺 agent 三类 fail-closed。
- Contract：与 019/021 的接口契约测试。
- Import 边界测试：router 依赖白名单（违例即红）。
- 回归：全部既有基线绿（router 上线不改变既有路径行为直至切换点）。
