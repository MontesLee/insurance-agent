# Phase 28.C-0 Report — QA Agent Design & Contract Preparation

Date: 2026-09-25 · 状态：COMPLETE（**docs-only，零代码**）· 交付物：
`docs/production/architecture/phase-28c0-qa-agent-design.md`。

## Completed work

1. **前置阅读**：PRODUCT_VISION / ARCHITECTURE_PRINCIPLES（FROZEN）·
   ADR-022 / ADR-019（APPROVED）· phase-28-implementation-plan §5 ·
   phase-28-implementation-gates（ADR-022 栏）——全部作为冻结约束对待。
2. **六面审计**（read-only，file:line 实证，设计文档 §0 A1-A8）：
   - KnowledgeService（组合根/K001-K004/strict 模式 weknora+PG 强制）
   - WeKnora 集成（纯检索端点/stamps 投影/F-24 重锚/abstention 同构）
   - 证据模型与契约（R1-R9、全引用元组、knowledge-evidence/query 契约）
   - LLM Gateway（ADR-011 已实现未接线——runtime/llm/gateway.py 全
     能力在位：policy/PII/限流/熔断/预算/重试/错误规范化/观测）
   - 答案生成流（三件套缺陷复核：证据不进上下文 tools.py:402-404、
     答案零门 agent.py:96-100、描述谎言 schemas.py:163-165）
   - 属性级 grounding 先例（SUPPORTED/UNSUPPORTED/CONFLICT/NOT_CHECKABLE
     三态诚实语义）
3. **设计文档八节全交付**：责任边界（拥有/禁止双清单+One Runtime 执行
   形态）· 输入契约（IntentResult 必经验证）· WeKnora 检索契约（经
   KnowledgeService、ALLOWED-only、confidence 只来自检索分数）·
   AnswerContext schema（answer/evidence_refs/grounding_status/
   failure_reason + evidence_map/retrieval/generation，闭合契约）·
   grounding 规则（事实三分类来源约束 + 引用闭环门四步 + 拒绝梯度）·
   六故障模式（四强制+时效+目录缺失，全映射既有信号）· Catalog 硬边界
   （事实查表/知识检索不互补位）· 测试策略（unit/contract/e2e 五场景/
   回归红线）。
4. **开放决策清单**（§9 D1-D6，各带建议）：qa-answer artifact 政策
   （v1 不升格）、LLM 网关接线（推荐）、契约位置、查询改写、LLM-down
   降级形态、目录 schema 字段。
5. **实施序建议**：契约→门→缝→网关→执行单元→QA 意图权威切片→e2e，
   每步过 ADR-022 三段门。

## Files changed

- NEW：`docs/production/architecture/phase-28c0-qa-agent-design.md`（本
  阶段核心交付物）
- NEW：`docs/production/architecture/phase-28c0-report.md`（本文件）
- 记账：`.agent/{checkpoint,current-task,decisions}.md`、memory

## Compliance check（spec Forbidden 清单）

- ❌ 未修改 runtime（零 Python 改动——git 复核）
- ❌ 未创建 QA Agent 实现（设计文档明示 implementation 需另行授权）
- ❌ 未修改 WeKnora（审计只读）
- ❌ 未修改 Router authority（权威切换仍属 28.B；本设计只定义 28.C 的
  QA 意图切片语义，引用 ADR-020 迁移策略原文）
- ❌ 未修改 orchestrator
- ✅ Only docs and audit

## Key design decisions（供所有者快速裁决）

1. **AnswerContext v1 = run 记录而非 artifact 类型**（D1 建议）——避免
   eval/risk-rules/contracts 三处联动与 Review Card 全红连锁。
2. **QA LLM 经 ADR-011 网关**（D2 建议）——唯一新增 LLM 调用点顺带
   偿清 R6 绕行债。
3. **引用闭环门在交付前、代码级、LLM 不自查**——幻觉在交付面结构性
   不可达。
4. **confidence 只来自检索分数的有界映射**——模型自报数字不进契约。

## Next recommended action

所有者裁决 §9 D1-D6（尤其 D1/D2/B3 目录 schema）后授权 **28.C-1**
（按设计文档实施序：schema + 契约测试先行）。readiness 与就绪判定沿用
phase-28c-readiness.md（CONDITIONALLY READY——代码侧 GO，三项人工
决策 + HD-2 数据侧阻塞价值不阻塞代码）。

**STOP — 设计阶段完成，未实施；等待 28.C-1 授权与 D1-D6 裁决。**
