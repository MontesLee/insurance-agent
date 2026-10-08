# Phase 28.0.5 Report — Architecture Decision Finalization

Date: 2026-09-25 · 仅触碰 docs/adr/**、docs/production/architecture/**、
.agent/**（bookkeeping）。零代码/schema/runtime/frontend/backend 改动；
未实施 28.A。

## Step 1 — ADR 状态检查（裁决前 → 裁决后）

| ADR | Current Status（裁决前） | Decision（核心决策） | Required Modification（28.0.3） | Approval Requirement（本轮 fulfilled?） |
|---|---|---|---|---|
| 019 | PROPOSED | 独立意图层；IntentResult；LLM 提案/确定性终裁 | **M1**：意图输入含会话+active case 上下文；上下文不可得→modify→澄清 | ✅ 所有者裁决 APPROVED，M1 落笔（Decision 规则 7/8） |
| 020 | PROPOSED | Router 纯查表 intent→agent；四禁 | 无（APPROVE as-is） | ✅ APPROVED（三层约束保持：schema contract+import boundary+CI tests） |
| 021 | PROPOSED | Registry 单一真源+启动校验 | 无（附形态裁定） | ✅ APPROVED（v1=configuration based；禁 runtime dynamic registry） |
| 022 | PROPOSED | 证据必须性+引用闭环门+四故障路径 | 无（附两项裁定） | ✅ APPROVED（grounding required；product fact/coverage/waiting period/exclusion/policy term←Catalog 或 WeKnora；缺失 fail closed） |
| 023 | PROPOSED | Text+Artifact；格式矩阵；渲染唯一性 | 无（附默认格式裁定） | ✅ APPROVED（v1=Markdown default；HTML/PDF=future；唯一性与 L1 规则 v1 生效） |
| 024 | PROPOSED | Conversation→Case→Run；四机制 | **M1** 反馈锚定 + **M2** 数据政策边界 | ✅ **APPROVED_WITH_CONSTRAINTS**：两补充条款落笔（Decision §5/§6）；三项数据政策未定义前 BLOCKED implementation |

## Step 2 — 已应用的修改（文件级）

- `docs/adr/ADR-019-intent-layer.md`：Status→APPROVED；Decision 增规则
  7（输入=message+recent conversation context+active case context；
  上下文不可得→modify→clarification）与规则 8（**prompt 永不作为
  intent source**）。
- `docs/adr/ADR-020-router-contract.md`：Status→APPROVED（原文保持，
  三层约束注记）。
- `docs/adr/ADR-021-agent-registry.md`：Status→APPROVED（v1=
  configuration based；禁 runtime dynamic registry）。
- `docs/adr/ADR-022-knowledge-grounding.md`：Status→APPROVED
  （grounding required + fail closed 裁决注记）。
- `docs/adr/ADR-023-chat-artifact-experience.md`：Status→APPROVED
  （v1=Markdown default；HTML/PDF 自 v1 起列为 future scope；渲染
  唯一性与 L1 层级 v1 生效）。
- `docs/adr/ADR-024-conversation-case-lifecycle.md`：Status→
  APPROVED_WITH_CONSTRAINTS；Decision 增 §5（反馈锚定 run_id+
  artifact_version，防未来反馈污染）与 §6（数据政策三定义
  retention/access boundary/deletion strategy；**信息不足即 BLOCKED
  implementation**，明示已阻塞项：会话持久化实施、客户事实落库/
  保留/删除路径）。

## Step 3 — Decision Record

`docs/production/architecture/phase-28-decision-freeze.md`（approved
019-024 / remaining blocked 三项 / unlocked 28.A / blocked 28.C·28.E
及 28.B/D 附注 / HD-1·HD-2·O-1 处置备注）。

## Step 4 — 治理状态

`.agent/checkpoint.md` 已更新：Governance FROZEN · 019-023 APPROVED ·
024 APPROVED_WITH_CONSTRAINTS · Next = 28.A Intent Router Registry。

## Validation

git 复核：本阶段改动仅 `docs/**`（六份 ADR 状态/条款、freeze 记录、
本报告）与 `.agent/**`；runtime/web/backend/schema/tests 零触碰。
未实施 28.A。

**STOP — 等待 28.A 授权。**
