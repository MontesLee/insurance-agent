# PRODUCT VISION — Chat-first Insurance Agent Platform

> **Governance baseline v1.0 — FROZEN 2026-09-25**（Phase 28.0.4）。
> 本文件是产品身份与空间边界的**唯一权威版本**（`docs/PROJECT_VISION.md`
> 为导航桩）。修改本文件需要所有者明确的产品决策，不得顺带改动。
> 依据：Phase 27.9 / 28.0 / 28.0.1 / 28.0.3 审计链 + Phase 28.1 治理引导。
> 配套硬约束：`ARCHITECTURE_PRINCIPLES.md`（本目录）· AGENTS.md（Skill 层）
> · docs/adr/（决策记录）。

# Product Identity

**本项目不是**：

- 保险后台管理系统
- Dashboard 产品
- 人工审核工具
- 通用聊天机器人

**本项目是**：

> **"Chat-first Insurance Agent Platform"** ——面向普通保险消费者的
> 对话式保险智能平台。目标用户是消费者本人（不是开发者、测试人员、
> Agent 工程师；审核员服务于此平台的运营，不是它的产品用户）。

**用户唯一业务入口**：

```
User Message
  ↓
Insurance Conversation
  ↓
Intent Recognition
  ↓
Router
  ↓
Specialized Agent
  ↓
Workflow Execution
  ↓
Evidence-grounded Result
  ↓
Artifact Delivery
```

（第一版 Agent 边界：**Insurance QA Agent**——保险知识/产品基础解释/
条款解释，必须知识 grounding；**Insurance Planning Agent**——风险/缺口
分析、方案设计、产品推荐、报告生成，拥有现有 8 阶段工作流。会话前端只
负责澄清与呈现，不拥有业务工作流。）

宁可追问与拒答，不可编造；宁可暴露"暂无依据"，不可假装知道。

# Space Boundary（三空间边界）

## User Space

**唯一入口：Chat UI。**

允许的业务：

- insurance QA（保险知识问答）
- product QA（产品事实问答）
- insurance planning（保障方案规划）
- existing policy modification（已有方案修改）

输出：

- text answer（文本回答，evidence-grounded）
- insurance report（保险报告）
- HTML/PDF artifact（HTML 在线查看 / PDF 打印导出）

**禁止用户看到**：

- run_id、artifact_id、eval_id、approval_id（任何内部 ID）
- dashboard
- developer mode
- 任何 Operator/Developer Space 界面与技术细节（L1-L4 层级标准，
  技术详情折入详情/开发者空间）

## Operator Space

用途：**人工审核、异常处理、升级处理**。

包含：

- Review Center（复审中心）
- Approval（审批）
- Feedback Loop（反馈闭环）

**不是用户入口。** 人工审核是**升级路径**而非默认环节（见
ARCHITECTURE_PRINCIPLES Principle 6）：AI 无法安全判断时才升级给人；
人做最终责任决策与不可自动确认的事实核验。

## Developer Space

包含：

- Dashboard
- Developer Mode
- Eval（评估体系）
- Trace
- Runtime inspection（运行时检查）

内部工程与审计空间；其数据（raw events/ids/payload）是永久审计资产，
但永远不成为产品主路径或用户可见内容。

---

## Anti-Goals（禁止演变为）

通用聊天机器人 · Workflow 展示工具 · Developer Dashboard 产品 ·
Evaluation 平台产品 · 保险后台管理系统 · 人工审核工具。
（同源禁令：绕过 Chat 新建业务入口、绕过 Router/Registry 新建执行路径、
无证据"LLM 直答"通道、内部 id/枚举当用户内容。）
