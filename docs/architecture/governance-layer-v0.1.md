# Governance Layer Architecture v0.1

Status: Accepted (Phase 27.5, commit 7985680 on
phase26c-productionization-v1.0 / c7ed9c6) · Date: 2026-09-24 ·
Companion ADR: ADR-017 (docs/production/ADR-017)

---

## 1. Overview

Phase 27.5 建立了 Agent **Human-in-the-loop Governance Layer**:
在 Agent 执行与人之间的、只读优先的治理界面层。

它解决的问题 —— 传统 Agent 的形态:

```
Input → LLM → Output
```

无法满足企业场景;本项目的实际形态是:

```
Input → Agent Execution → Evidence → Human Review
      → Decision → Audit
```

Governance Layer 就是中间"Human Review → Decision → Audit"这
一段的产品化:它不增强 Agent 的能力,而是让**人**能够安全、
高效、有据地接管与放行 Agent 的产出。

---

## 2. Architecture Diagram

```
                    User Request
                         |
                         v
                 Agent Runtime (26A–26C core, unchanged)
                         |
        +----------------+----------------+
        |                                 |
        v                                 v
     Runs                            Artifacts
        |                                 |
        +----------------+----------------+
                         |
                         v
              Governance Layer (Phase 27.5 UI)
                         |
        +----------------+----------------+
        |                |               |
        v                v               v
 Review Queue      Workspace        Dashboard
 (27.5-2)          (27.5-3)         (27.5-5)
        |
        v
 Human Decision (27.5-4)
        |
        v
 Decision Record (backend, immutable)
```

只读治理层消费既有 API;唯一的写动作是 Decision 的两个既有
mutation 端点(approve/reject),且状态转换全部由后端执行。

---

## 3. Component Responsibilities

### Review Queue(27.5-2)
职责:找到需要人工关注的审批任务;逐字展示后端审批状态;
可操作优先排序;loading/error/empty 三态。
**不负责**:workflow、decision、状态解释。

### Review Workspace(27.5-3)
职责:五节只读聚合 —— A 审批摘要(为什么审我)/ B 案例上下文
(关于谁)/ C 执行时间线(Agent 做了什么)/ D 产物(产出了什么)/
E 证据链(为什么相信)。
核心原则:**Evidence before Decision** —— 决定面板位于证据链
之后,审阅者先看证据再做判断。

### Decision Panel(27.5-4)
职责:记录人工判断 —— APPROVE(确认门)/ REJECT(意见必填),
经既有端点提交,无乐观更新,后端为唯一状态权威;已决定记录
不可编辑。
**不负责**:修改 Agent 输出、编辑推荐、触发重跑、控制 Agent。

### Pilot Dashboard(27.5-5)
职责:运营可见性 —— 按后端状态字符串精确分组的计数卡、等待
快照、最近决定、快速导航。
**不负责**:BI、Analytics、排名、评分、SLA 预测。

---

## 4. Data Flow

```
Approval → Project → Run → Artifacts → Evidence
                                     → Human Decision → Audit Record
```

当前**已有**的关系(后端真相):

- Approval → Artifact:harness 审批上下文携带 artifact_ids
- Run → Artifact:流水线 run 的产物端点(含 provenance)

当前 **Gap**:

- **Approval → Run**:不存在。审批记录不携带 run/case id,
  Workspace 的 C/D/E 节(时间线/产物/证据链)目前依赖人工选择
  run-id(持久化选择器)。

---

## 5. Design Principles

**Principle 1 — Backend is Source of Truth**
UI 不解释状态:状态字符串逐字渲染(WAITING_HUMAN 就是
WAITING_HUMAN,未知状态原样显示);等待时长等仅是呈现层换算;
失败时区块缺席而非显示假 0。

**Principle 2 — Evidence before Decision**
人工审核必须基于可追溯证据:证据链(推荐→需求→证据→来源)
渲染在决定面板之前;缺失证据显示 "No evidence linked",绝不
伪造。

**Principle 3 — Human decides, System records**
人只做两个动作:approve / reject。系统负责持久化与审计
(resolved_by / resolved_at / decision),决定记录不可编辑。

**Principle 4 — Governance Layer does not control Runtime**
治理层与执行引擎解耦:只读消费既有 API;唯一的写路径是既有
审批端点(后端执行状态机与角色检查);不在前端推导业务结论、
不创建第二套状态机、不直连数据库。

---

## 6. Current API Boundary

消费的既有 API(全部为 Phase 9/10/2 已有能力,零新增):

```
GET  /api/projects/{id}/approvals        # 队列/仪表盘(项目作用域)
GET  /api/approvals/{id}                 # 详情/摘要
GET  /api/projects/{id}/supervisor       # 案例上下文(项目级状态)
GET  /api/runs/{id}/events               # 执行时间线
GET  /api/runs/{id}/artifacts            # 产物列表
GET  /api/runs/{id}/artifacts/{type}     # 产物/证据链拼装
POST /api/approvals/{id}/approve         # 人工决定(REVIEWER 角色)
POST /api/approvals/{id}/reject          # 人工决定(REVIEWER 角色)
```

---

## 7. Current Limitations

**7.1 Global Approval Queue** —— 审批按项目作用域,无全局队列;
UI 以持久化项目选择器过渡。
未来:`GET /api/approvals`(全局聚合)。

**7.2 Approval → Run Binding** —— 见 §4 Gap;人工选择 run-id。
未来:审批记录携带 `{run_id, case_id}` 或提供联动端点。

**7.3 Identity** —— 无 who-am-I 端点;决定前 Reviewer 显示 "—",
决定后显示后端 resolved_by。
未来:identity API + 更完整的 RBAC 呈现(后端 RBAC 已存在)。

**7.4 Audit History** —— 决定记录为单条 resolved 项,无事件流。
未来:append-only 决定/审计事件端点。

---

## 8. Future Evolution

**Phase A — Human Feedback Loop**
```
Decision + Feedback → Evaluation Dataset → Agent Improvement
```
把 27.5 的决定与审查表单(pilot evidence)回流为评估数据。

**Phase B — Backend Domain Model**
补齐 Approval / Run / Case / Evidence / Decision 的显式关联
(消除 §7.1/7.2 的两个 Gap;为 Phase A 提供查询基础)。

**Phase C — Enterprise Governance**
RBAC 呈现、审计事件流、多项目队列、合规导出。

---

## 9. Architecture Decision Record

见 **ADR-017 Governance Layer Separation**
(docs/production/ADR-017-governance-layer-separation.md;编号
沿用 ADR-008..016 所在的 production 系列,故非提示词示例中的
ADR-008 —— 该编号已被 production-persistence 占用)。

Decision:Governance UI 保持与 Agent Runtime 独立。
Reason:避免人工工作流与执行引擎耦合 —— 治理层演进(表单、
反馈、BI)不得牵动运行时;运行时演进(队列/预算/恢复)亦不
得破坏治理契约(API 投影稳定)。
