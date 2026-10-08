# Agent Activity v2 — 数据需求设计（Phase 28.B prep · Step 3，DESIGN ONLY）

Date: 2026-09-25 · 性质：**设计文档，不实施**（spec 明令：不改 UI）。依据：
phase-28b-preparation-audit.md（贯通性实态）· PRODUCT_VISION 三空间/L1-L4
层级 · ARCHITECTURE_PRINCIPLES（Chat 为产品面；内部遥测不作用户内容）。

## 1. 现状（v1）

AgentActivity（web/src/components/chat/AgentActivity.tsx）由 RunUiState
投影渲染：8 阶段 stageOrder/stages、eval 汇总、stream 面板、
latestActivity 标签。**盲区**：QA 切片轮（无 stage 概念）整卡只显示
"Agent 正在工作"直到 run_completed；意图/路由/grounding 过程零呈现
（audit §1 判定：管道贯通、契约已同步、呈现缺失）。

## 2. v2 目标

让一次 chat 轮（无论走 agent 工作流还是 QA/grounding 切片）都有
**分阶段活动轨迹**，且严格分层：

- **L1（用户默认可见）**：自然语言相位文案——"正在理解您的问题"→
  "正在查询知识库"→"正在生成有依据的回答"→"已引用 N 条资料回答"
  /"知识库暂无可靠依据，已如实说明"。**零内部 id/枚举**（PRODUCT_VISION
  禁令：intent_id/agent_id/run_id 不得面向用户）。
- **L4（开发者层级，默认折叠）**：完整遥测——intent/confidence/
  reason_codes、route_decision（registry_lookup/fallback）、grounding_
  status/failure_reason、retrieval（provider/allowed/denied/latency）、
  generation_provenance（attempts/gate_violations/usage）。仅 Developer
  Space 语境展开（28.G 空间分离后归位；当前折叠面板即可）。

## 3. 数据清单（可得 vs 需新增发射）

### 3.1 现在即可用（后端已发射，契约已同步）

| 相位 | 数据源（事件 data） | 字段 |
|---|---|---|
| 意图理解 | `intent_classified` | intent, confidence, confidence_source, reason_codes, clarification_required, shadow, latency_ms, **route_decision{intent_id, agent_id, decision_source, validation_result}** |
| 回答落地 | `qa_answered` | grounding_status, failure_reason, evidence_refs[], retrieval{query, provider, governed_status, allowed/denied, conflict}, generation_provenance{provider, model, prompt_version, attempts, gate_violations}, slice, answer_len |
| 轮次骨架 | run_started/run_completed | status, result_status（QA_ANSWERED/QA_REFUSED） |

→ **v2 最小实现不需要任何后端改动**：intent_classified 即"理解"相位
完成信号；qa_answered 即"回答"相位完成信号；中间相位用乐观文案填充
（"正在查询知识库…"），完成事件校正。答后 L1 徽标 "已引用 N 条资料"
= evidence_refs.length。

### 3.2 需要**新增后端发射**（reserved 契约已就位，发射=未来 runtime 授权项）

| 事件 | 语义（建议） | 触发点 | 价值 |
|---|---|---|---|
| `grounding_started` | 证据检索开始 | QA/Product QA 轮进入 KnowledgeService 前 | 真实相位边界（替代乐观文案）；L4 延迟测量起点 |
| `grounding_completed` | 证据组装完成（含 allowed/denied 计数与 governed_status） | build_evidence 返回后 | 检索耗时/治理拒绝率实时可见；区分"检索慢"与"生成慢" |
| `route_selected`（audit G-3，ADR-020 设计提及未实现） | Router 权威裁决 | 28.B 切换后的每轮 | 权威路由可审计；现内嵌于 intent_classified.data.route_decision 已够 v2 用 |

发射纪律：data 均为元数据（沿用 events 元数据原则）；grounding_*
的 data 复用 qa_answered 的 retrieval 子集，不重复用户文本。

## 4. 派生状态模型（前端侧设计）

```ts
// runReducer 增量（TRANSITIONS 新 case，不改现有）：
interface GroundingPhase {
  kind: "intent" | "retrieval" | "generation" | "answer";
  status: "running" | "done" | "failed";
  label: string;              // L1 文案（中文，无内部 id）
  detail?: Record<string, unknown>;  // L4 原始遥测（折叠层）
}
// intent_classified → {kind:"intent", status:"done", detail:事件data}
// grounding_started(未来) → {kind:"retrieval", status:"running"}
// grounding_completed(未来) → {kind:"retrieval", status:"done", detail}
// qa_answered → {kind:"answer", status:"done"|"failed"(refused),
//                 label: 引用徽标文案, detail}
```

渲染规则：QA 切片轮复用同一张活动卡（stage 列表为空时只显示相位流）；
agent 工作流轮保持 v1 全量（相位流折叠在"详细"内）；demo 模式不受影响
（无新事件即无相位流，回退 v1 表现——**向后兼容**）。

## 5. 需要人工/后续决策

1. L1 grounding 徽标的展示措辞与位置（产品决策；audit §2 已列）。
2. reserved 事件毕业（后端发射 grounding_*）的授权时点——建议与
   28.B 切换同批（migration checklist 前置项 P-3）。
3. L4 折叠面板与 28.G 空间分离的归位关系（当前折叠=过渡形态）。

## 6. 明确不做（本设计边界）

- 不改 AgentActivity.tsx / activity.ts / runReducer 的**任何渲染行为**
  （spec 禁令）；本文件仅为数据与派生模型设计。
- 不新增后端事件（runtime/ 本阶段只读）。
- 不引入 Chat 之外的呈现面（Principle 1）。
