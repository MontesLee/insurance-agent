# UI Pilot Gap Analysis — Phase 27.5-1 (2026-09-24)

## Role journeys (current UI vs needed)

### Role 1 — Insurance Consultant (顾问)
| Step | User action | System response | Current UI | Pain point | Required improvement |
|---|---|---|---|---|---|
| 1 | 输入客户情况 | chat 流式分析+产物卡 | ✅ Chat mode | 演示 KB;产物 JSON 感强 | 业务化渲染(卡片字段中文化、结论先行) |
| 2 | 理解风险/缺口 | 风险卡/缺口卡嵌入对话 | ✅ | 无汇总视图,需翻聊天记录 | Case 汇总页(客户画像+风险+缺口一屏) |
| 3 | 提交正式分析 | Case → Run | ⚠️ Developer mode | 要切"开发者模式"才能跑 Case,心理门槛高 | 顾问模式内一键"生成正式分析" |
| 4 | 查看报告 | RunOutput | ⚠️ 原始输出 | 无导出/打印 | 报告页(渲染+导出) |

### Role 2 — Reviewer(审核人 —— 试点核心角色)
| Step | User action | System response | Current UI | Pain point | Required improvement |
|---|---|---|---|---|---|
| 1 | 打开待审 Case | — | ❌ 无入口 | **没有任何审核队列界面** | Review Queue 列表(待审/已审/状态) |
| 2 | 查看 AI 分析全链 | — | ⚠️ 右侧 Inspector | 检视视图是调试向,非审阅向 | Case Detail 主文档式布局 |
| 3 | 检查证据链 | — | ❌ | 证据散在 artifact JSON 里,无"结论→证据"追溯视图 | Evidence View(逐推荐列证据引用,可点开) |
| 4 | Approve / Reject | 后端有端点 | ❌ **UI 无任何审批控件** | 只能用 curl/脚本审 | 审批操作(批准/驳回+必填意见) |
| 5 | 留下结构化反馈 | — | ❌ | Phase 27 审查包是手填 markdown | Review Form(8 节判定+时间戳自动记录) |

### Role 3 — Operator
| Step | Current UI | Pain point | Required |
|---|---|---|---|
| 系统健康 | /api/health 未在 UI 消费 | 无总览 | Pilot Dashboard(健康+关键计数) |
| 异常处理 | 无(恢复靠 operator 脚本) | 试点可接受 | 只读状态页即可 |

## Acceptance question 1: 现在的 UI 能否支撑顾问完成一次
Case Review?

**NO。** 三个硬缺口:没有审批入口(端点存在但 UI 未接)、
没有面向审阅的证据链视图(数据在 artifacts 里但以调试形态呈
现)、没有审核反馈记录界面(当前靠手填 markdown)。现有
Chat/Developer 两模式可完成"看分析",不能完成"审+批+记"。

## Top-3 UI blockers(试点视角)

1. **Approval UI 完全缺失**(B1):Review Queue + 审批操作 +
   意见必填 —— 试点的人审硬规则在 UI 层没有落点。
2. **无 Review Workspace**(B2):审阅需要"一屏读完证据链"的
   主文档视图;现在是右栏调试 Inspector,反直觉且信息密度错配。
3. **反馈与审查记录无界面**(B3):Phase 27 的人工审查包
   (12 case × 8 节判定 + 时间 + 变更建议)只能手填文档,审查
   时间/聚合指标无法自动采集。

## MVP scope(Phase 27.5 实现阶段建议)

**Must Have**(直接支撑 Owner 完成 12-case 审查 + 后续试点)
- Case Dashboard(case 列表 + 状态 + 入口)
- Review Workspace(Case Detail:客户画像/需求/风险/缺口/方案/
  推荐/证据链/报告,主文档布局)
- Evidence View(推荐→证据引用→原文,只读)
- Approval Interaction(批准/驳回 + 必填意见;走既有
  /api/approvals 端点,不新增业务规则)
- Review Form + 自动记时(结构化判定落库/导出,替代手填
  markdown;作为 pilot evidence 存储,不写 Runtime 状态)
- Basic Pilot Metrics(审查进度:待审/已批/已驳计数)

**Should Have**:Pilot Dashboard(健康+计数)、Runtime Status
页、报告导出/打印。

**Future(明确不做)**:multi-tenant、customer portal、CRM 集成、
queue/budget 深度可视化(等后端 API 化后再做)、移动端。

## 明确不做(本产品化阶段)

不改 Agent/Skill/Eval/Approval 逻辑;不接真实客户数据;不接
生产 LLM;不引入新框架;不直连数据库;不在前端自行判定审批
有效性(只呈现后端状态)。

## API Gap 分析(只分析,不实现)

| Need | Current | Required | Priority |
|---|---|---|---|
| Review Queue 列表 | GET /api/projects/{id}/approvals 已存在(未消费;无 identity 依赖) | 前端消费 + 全局待审列表(跨 project)或按 project 即可 | P0-UI |
| 审批操作 | POST /api/approvals/{id}/approve\|reject 已存在 | 前端消费 + 意见字段(后端已有 reason?核对;不足则最小扩展) | P0-UI |
| Case 汇总(cases+runs) | GET /api/cases、runs 按 id | 够用(前端聚合) | — |
| 证据链视图 | GET artifacts(逐类型) | 够用(前端拼装 provenance refs) | — |
| 审查反馈存储 | 无 | 最小新增只读资源(如 /api/pilot/reviews)或导出 JSON/文件 | P1-API(需后端最小新增,**须另授权**) |
| Pilot 计数 | 无 | 可由前端从 cases/approvals 聚合(只读) | — |
| Queue/Budget/Recovery 可视化 | 后端未 HTTP 化(26B 注记) | 等 API 化 | Future |

## Runtime boundary 确认

UI 只经 API 消费后端真相(SSE + REST 投影);不直连 DB、不写
Runtime 状态、不自行判定审批。Review Form 数据是 **pilot
evidence**,不是 Runtime 状态 —— 存储路径必须与 queue/agent_
runs 隔离(新增只读资源或文件导出),不得写入 CaseState/Task/
Run/Approval。审批有效性一律以 /api/approvals 的后端响应为准。
