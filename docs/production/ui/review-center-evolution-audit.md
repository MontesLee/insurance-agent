# Phase 27.8 — Review Center Evolution & Human-centric UI Architecture Audit

Date: 2026-09-24 · READ-ONLY audit (no code/UI/schema/API/runtime/approval-
machine changes). Evidence: full web/src sweep (all 20+ components with
file:line refs, incl. first-paint order + developer-marker visibility +
empty-state strings), App.tsx shell, live backend state (6 staged HR
approvals), and the prior audits (27.7.7 workspace-ia-audit, 27.7.8
review-architecture-audit). Direction fixed by 27.7.8: Deterministic
Quality Layer → AI Review → Decision Router → Human Escalation →
Approval + Feedback; 原 Human Review 保留但降为 Escalation Workflow.

> **STATUS: analysis + architecture proposal only — STOP after this
> document. Nothing implemented; awaiting next-phase authorization.**

---

## 1. Current UI Landscape

### 1.1 Shell & navigation (App.tsx)

No router, no URLs — four localStorage-persisted modes
(`webui:mode`): **对话 chat (default) / 审核队列 review / Dashboard /
Developer**. Review is a three-level state chain
ReviewQueue → ApprovalDetail → ReviewWorkspace (App.tsx:91-108);
back from workspace lands on ApprovalDetail (a second click reaches
the queue). A refresh mid-chain drops the selection (mode survives,
selection does not). No identity display, no login, no breadcrumbs,
no toasts, exactly one modal (chat report). Consequences: no
shareable URL for a case/run; deep-linking and "send this case to a
colleague" are impossible — an architectural (not cosmetic) gap.

### 1.2 Per-page audit (§四 table)

| Page | 当前目标 | 目标用户 | 当前信息顺序（首屏） | 主要问题 | 未来定位 |
|---|---|---|---|---|---|
| ReviewQueue | 按项目列出审批+Review Card（只读） | 保险审核员（实际内容偏系统） | 标题 → **project_id 手输框** → 筛选 chips → 行（英文状态枚举 → card 级别 → **approval_id mono** → 客户名/reason 截断 → 英文校验 chips → meta 网格含 run_id/`—`） | 必须"背出"project_id 才能看到任何东西（首访死路）；英文枚举/内部 id 先于业务内容；card 拉取失败静默掉出筛选 | **Human Escalation 收件箱**：默认项目、按"为什么需要你"分组，AUTO_PASS 移出默认视图 |
| ApprovalDetail | 自我标注的"记录视图 placeholder" | 名义审核员，实为系统记录 | 状态徽章+approval_id → dl（项目/**Task 原始 task_id**/类型/请求方/UTC 时间…）→ Reason → 折叠 Context JSON | 死胡同数据表；无业务内容、无动作；task_id/requested_by 等系统字段先行的典型 | 降级为 Review Center 内的**决定记录/审计 tab**，不再是必经跳板 |
| ReviewWorkspace | 真正的决策工作台（27.7.7 九区 IA） | 保险顾问/审核员 ✅ | 客户行 → 摘要五卡 → 风险表(可展开依据+证据) → 方案 → 产品 → 🔴🟡🟢 → 决定 → 反馈 → 产物/报告 → 人话过程 → 折叠技术详情 | 残留：风险行展开的 mono `riskId·gapId` 行、产品推荐依据的 `type:ref` mono、交付物原始 status 串、F/G 编号插在 6/7 之间、9 产物并发急拉首屏偏慢 | **Review Center 主体**（Case Overview + 各区来源） |
| DecisionPanel | 唯一写入口（approve/reject/request-fix） | 审核员 | 状态 → Reviewer `—` + **给用户看的内部 GAP 注记** → 意见框 → 按钮（英文 Approve/Reject + 中文退回修正混排） | 提交后无导航；身份 API 缺失注记暴露给终端用户；Request Fix 实为 REJECT+前缀（诚实但别扭） | **Decision Workspace**：+ AI 建议 vs 人工判断 对照 + 决策原因结构化 |
| FeedbackPanel | 决定锚定的结构化反馈（"INERT EVIDENCE"） | 审核员 | 记录列表（含内部 `anchor/status/provenance` 行）→ 未决定门槛提示 → 表单（6 类目） | **仅存 localStorage**（GAP-27.7-01）；无导出/无共享/无后端；类目保存后仍是英文枚举 | **Feedback Loop 采集点**：后端实体 + 分类视图 + 金标集（Phase D） |
| PilotDashboard | 只读运营总览（前端聚合） | 试点运营 | 标题 → project_id 手输 + **"无全局审批端点(API GAP)"注记** → 状态卡（**原始英文枚举当大字标签**）→ 等待快照 → 最近决定（mono 时间戳+枚举，REQUEST_FIX 也纯红）→ 两个效果相同的入口按钮 | 枚举卡不可点、不联动队列筛选；内部 GAP 文案直接面向用户；时间戳原始 ISO | 运营视图：状态卡=链接（点击→收件箱对应筛选），决定色区分 approve/fix/reject |
| DeveloperMode (+CasesSidebar/Conversation/RuntimeInspector) | Cases·运行控制台；唯一能 POST /api/runs 的地方 | 工程师（刻意） | **run_id mono** → 案例列表（mono case_id/run_id.slice）→ 实时进度行（`stage_completed`/`eval FAIL · repair 1`）→ 报告 → 结局横幅 → Run/Pipeline/Eval/Trace/Artifact 检查器 | 无（对开发者正确）——但它是今天唯一"从案例到运行"的入口，审核员没有对应物 | **原样保留**，明确标注为工程/审计控制台（L4 永久居所） |
| Chat UI (User Mode) | 面向客户的演示/对话体验 | 终端客户 | 欢迎页 → AgentActivity（中文阶段表+工具行）→ ArtifactCard（**mono `artifactType · run {id}`**）→ 报告弹窗 | 自由文本被静默映射到 5 个演示案例（仅欢迎页小字披露）；产物卡露内部 id | 客户面保留；ArtifactCard 内部标识降级到"查看详情"内 |
| Artifact Viewer（ArtifactInspector / Workspace 产物注册表） | 产物 JSON 钻取 | 工程/审计 | mono 元信息网格 / 注册表行 + 复制 JSON | 仅钻取可见——定位正确 | L4 证据层，保留（复制 JSON/血缘是审计资产） |
| Timeline Viewer（TraceTimeline / Workspace 原始日志） | 事件流查看 | 工程/审计 | mono `时间 event_type stage repair` 行 → 展开全字段 dl + data JSON | 仅钻取/折叠可见——定位正确 | L4；Workspace 人话清单已是正确投影 |
| Run Detail | **不存在**（run 数据散落在 Workspace 技术详情/RuntimeInspector/CasesSidebar） | — | — | 无 URL 可寻址的 run 页 | 并入 Review Center 技术详情；URL 路由是 Phase A 项 |
| Supervisor 视图 | **不存在**（仅 Workspace 折叠块渲染 项目状态/风险级别；`active_alerts`/`pending_interventions` 已有类型**从未渲染**） | — | — | 告警数据有类型无界面 | Phase B：仅当数据支撑时进入 Escalation 原因区 |

### 1.3 Developer-marker 首屏泄漏清单（§八 证据）

Reviewer 面仍处首屏的内部标识：queue 行 `approval_id`/`Run:`/
`project_id` 输入、ApprovalDetail `task_id`、PilotDashboard 枚举大字卡、
DecisionPanel/FeedbackPanel 内部 GAP 注记与 `anchor/provenance` 行、
chat ArtifactCard `artifactType · run id`。已正确降级的样板：
ReviewWorkspace（run/artifact/event/payload 全部折叠进技术详情，
`schema_version`/`graph_revision` 全库从未渲染——只存在于原始 JSON）。

---

## 2. Current Human Workflow（含 §十一 真实数据验证）

### 2.1 当前流程（as built，全部实证）

```
Case 创建（仅 Developer 控制台 / Chat 演示映射）
  → POST /api/runs → Agent 执行（eval/repair 门内环，27.7.8 已审计）
  → FINAL_REVIEW 审批（mode-gated）→ WAITING_HUMAN（100% 进人工，无 Auto Pass）
  → ReviewQueue（须手输 project_id）
  → ApprovalDetail（记录视图，纯跳板）
  → ReviewWorkspace（人类可读九区 → 人工判断）
  → DecisionPanel（Approve / Reject / Request-Fix=REJECT+"REQUEST_FIX:"前缀）
  → FeedbackPanel（localStorage，无后端，无导出）        ← 链路在此截断
  Dashboard 旁路观察；Supervisor 告警无界面
```

### 2.2 目标流程（27.7.8 已定方向落到 UI）

```
Case → Agent Run → Quality Layer(现有 card) → AI Review(27.8-R1 待授权)
  → Decision Router(decide_v2，确定性代码)
       ├─ Auto Pass → 「已自动通过」审计清单（新表面，可抽审）
       └─ Human Escalation → Review Center（为什么需要你 + 建议动作）
             → Human Decision（Decision Workspace）
             → Feedback → Issue Classification → Golden Dataset → AI Review 改进
```

### 2.3 五类真实 run × 链路支持度验证（live 数据）

| Run 类 | 实例 | 发现问题→升级→决策→反馈 | Auto Pass | 判定 |
|---|---|---|---|---|
| complete | run_9de5882e（card AUTO_PASS、restored=true） | ✅ 全链路可用（27.7.5 会话 6/6 真实决策+反馈实证；card 磁盘键控跨重启） | ❌ **无路由**——AUTO_PASS 卡仍强制 WAITING_HUMAN | 链路通，路由缺 |
| no-primary | run_447ccd4b | ✅ 升级区有真实理由（🔴1/🟡8），反馈类目 REASONING/MISSING_INFORMATION 均可锚定 | n/a | 通 |
| trace-only | run_48cc028f | ✅ 降级路径诚实（27.7.7 实证：无 run 上下文仍可决策）；AI review 将不可用→按设计升级人工 | n/a | 通（fail-closed） |
| repair | run_84f63c7c / run_381c2836 | ✅ `repair_used` 标记+DEEP_REVIEW 进高风险筛选；过程区显示失败步骤 | n/a | 通 |
| 全拒推荐 | run_dad25ef1 | ✅ 理由/provenance 完整呈现 | n/a | 通 |

**链路四个断点**（正是本提案要弥合的）：
1. **Auto Pass 无表面**（决定路由器不存在——27.7.8 R2 前提）；
2. **升级语义缺位**（queue 说"等待审核"，不说"为什么需要你"）；
3. **Request Information 无原生动作**（状态机冻结；现为 REJECT+前缀约定）；
4. **反馈环在 localStorage 截断**（无后端实体→无分类→无金标集）。

---

## 3. Review Center Architecture（§六）

统一入口：**审核中心 Review Center** 取代"审核队列"成为 review 模式
首页（队列语义降级为其中一个视图）。五个区，全部由现有数据源支撑
（无新 schema 前提下的映射标注 ✅/⚠）：

```
Review Center
├─ 1 Case Overview    客户画像/核心需求/当前保障/主要风险/Agent建议/当前状态
│    ← ReviewWorkspace 前五区 + card 审核状态（✅ 现有 viewModel 直供）
├─ 2 AI Review        状态 PASS|NEEDS_INFO|NEEDS_HUMAN_ESCALATION
│    检查项（需求匹配/风险依据/推荐理由…）+ 发现（severity/description/
│    evidence 内联解析/confidence 非空才渲染）+ reviewer 身份 + card_agreement
│    ← ⚠ 依赖 27.7.8-R1 ai-review-result（未授权前此区显示
│      "AI 审核：暂不可用（未部署）——已按需人工审核处理"，fail-closed）
├─ 3 Human Escalation "为什么需要你"：原因（verbatim：card flags / router
│    reasons / HIGH issues）+ 建议动作（仅映射现有机制：联系客户补充信息/
│    人工重跑该阶段(RETRY)/人工复审）   ← 取代"等待审核"框定（✅ 数据齐）
├─ 4 Decision Workspace  Approve / Reject / Request Information
│    + AI建议 vs 人工判断 对照 + 决策原因结构化
│    ← ✅ 决定端点冻结不动；⚠ Request Info 仍走 REJECT+前缀（原生动作需
│      ADR-017 修订，Phase D 决策项）；"AI建议"列依赖 Phase C
└─ 5 Feedback Loop    采集（现有面板）→ 分类视图 → 金标集
     ← ⚠ 采集 ✅；分类/金标依赖 Phase D 后端实体
```

关键原则（承袭 27.7.7/27.7.8）：UI 永不自行得出结论——AI Review 区
逐字渲染 ai-review-result；Escalation 原因逐字来自 card/router；
建议动作只指向**已存在**的控制机制（ADR-017 无控制耦合）。

---

## 4. Existing Module Migration（§十，不删除任何模块）

| 现有模块 | 迁移去向 | 保留形态 |
|---|---|---|
| Review Card | Case Overview 状态行 + AI Review 的 card_agreement 交叉项 | 完整卡片原样留在技术详情（ReviewCardDetail 已存在） |
| ApprovalDetail | Decision Workspace 的"决定记录"tab；queue→detail→workspace 三跳折叠为单一表面 | 逐字记录视图原样保留（审计资产） |
| Approval 状态机 | 不动（ADR-017 冻结） | — |
| Supervisor | Case Overview 状态行（仅渲染数据支撑的：项目状态/风险级别）+ 技术详情；`active_alerts` 仅当其构成升级原因时进入 Escalation 区 | 折叠块原样 |
| Feedback（面板+localStorage） | 仍是唯一采集点；Phase D 迁移为后端实体（human-feedback-loop-v0.1 的 Decision-锚定模型），localStorage 成为离线缓冲 | 采集交互不变 |
| ReviewQueue | Human Escalation 收件箱（默认视图=待升级项；AUTO_PASS 移入"已自动通过"审计清单——路由器上线前该清单为空并如实说明） | 筛选/抽审 chips 保留 |
| Dashboard | 独立运营页保留；状态卡改为可点链接（→ 收件箱对应筛选） | 聚合逻辑不变 |
| DeveloperMode/检查器 | 原样，标注"工程与审计控制台" | L4 永久居所 |
| Chat UI | 客户面独立保留 | 仅降级 ArtifactCard 内部标识 |

---

## 5. Human-centric UI Principles（§七 上）

1. **业务先行**：任何 reviewer 面首屏第一元素必须是业务结论/业务身份
   （客户、状态、原因），内部标识（*_id/枚举/payload）永不出现在
   未折叠首屏。开发者面豁免（其用户就是开发者）。
2. **先结论后证据后实现**：每个页面按 L1→L4 分层（§7 标准）。
3. **UI 不作结论**：所有业务语句逐字来自后端字段；标签只是显示字典，
   原始值在 L4 可审计（27.7.7 已确立，推广到全站）。
4. **诚实空态**：缺失=暂无信息+原因+下一步，绝不编造（§7.3）。
5. **动作可循**：reviewer 面每个终态都要有下一步（决定、升级、补充
   信息、查看记录），不允许死胡同数据表。
6. **GAP 不上脸**：内部 API 缺口注记从终端用户界面移入技术详情
   （对工程的诚实≠对用户展示内部欠账）。

## 6. Page Redesign Recommendations（每页未来定位已列 §1.2 表；此处列改造要点）

- **ReviewQueue→收件箱**：默认项目记忆+空态引导替代手输死路；行首=
  客户行+升级原因 chip；枚举全部走显示字典（原始值 L4）；卡片拉取
  失败显式重试；"已自动通过"清单 tab（Phase C 前如实为空）。
- **ApprovalDetail**：降为 tab，删除必经跳板地位；时间本地化；
  context JSON 留在折叠。
- **ReviewWorkspace**：F/G 编号并入连续区序；风险行展开的
  `riskId·gapId` mono、产品 `type:ref`、交付物原始 status 降入 L4/翻译；
  产物加载保留骨架态（可感知进度）。
- **DecisionPanel→Decision Workspace**：中英混排统一；提交后导航到
  反馈区（闭环引导）；增加 AI 建议 vs 人工判断 两列（Phase C 前 AI 列
  显示"未部署"）；身份 GAP 注记移入 L4。
- **FeedbackPanel**：保存后显示"已记录（本机）+ 如何导出"指引
  （Phase D 前如实说明单机限制）；内部 bookkeeping 行移入 L4。
- **Dashboard**：枚举卡→可点链接+中文标签；决定色三态
  （approve/fix/reject）；两个相同入口按钮合并。
- **Chat**：ArtifactCard 内部标识降入详情；演示映射披露保持并常驻化。
- **Developer**：不动。

## 7. Information Hierarchy Standard（§七/§八/§九）

### 7.1 四层标准（全站统一）

| 层 | 回答 | 内容 | 呈现 |
|---|---|---|---|
| L1 结论 | 发生了什么？ | 状态/客户/核心诉求/主要缺口/建议/升级原因 | 首屏第一视口，业务语言 |
| L2 解释 | 为什么？ | reason/objective/取舍/不确定性（逐字） | L1 下方/展开 |
| L3 证据 | 依据是什么？ | 证据原文+来源/引用解析/产物业务视图 | 展开/二级页 |
| L4 技术详情 | 系统如何实现？ | run/approval/task id、事件、payload、JSON、eval、card 全文、schema | 折叠 details/钻取/开发者控制台 |

规则：L1 不得出现任何 §1.3 标记；L4 内容**一项不删**（审计完整性）；
层间可追溯（L1 结论可一路点到 L4 原文——workspace 已示范）。

### 7.2 内部标识处置（§八 判定表）

| 标识/枚举 | 处置 |
|---|---|
| project_id 输入、queue 行 approval_id/Run:、detail task_id | **默认隐藏**（记忆默认项目+行内用客户/原因标识；id 移 L4/复制可用） |
| 英文状态/级别/类目枚举 | **默认隐藏原文**——显示字典渲染，原始值 L4 |
| payload/Context JSON、事件日志、产物注册表、证据链原文、card 全文、supervisor 状态 | **折叠展示**（现状已对，保持） |
| run/artifact/eval id、复制 JSON、血缘、trace 全字段 | **永久保留审计**（L4 + 开发者控制台；删除=违背证据链原则） |
| schema_version / graph_revision | 从不渲染——正确，仅存于原始 JSON |
| 内部 GAP 注记（身份/端点缺失） | 移 L4（原则 6） |

### 7.3 空态标准（§九）

统一三段式：`暂无信息` + `原因`（必须数据驱动：本运行未产出该产物 /
上游未提供 / 后端未实现该接口 / 未链接运行上下文）+ `下一步`
（仅当存在真实动作：补充客户资料 / 联系客户确认 / 前往决定区；无动作
则省略，不编造）。清除现状违规：dashboard "No approval records
available"（英文且无因）、queue "—"（无因无动作）、detail 缺省静默跳过
（应显式说明缺上下文）、chat/dev 英文空态（dev 豁免）。null 泄漏风险点
（agent 报告所列：PilotDashboard 非空判断、TraceTimeline 时间切片等）
纳入 Phase A 修缮清单。

## 8. Data Gap Analysis（UI 视角汇总）

承前合并（27.7.7 §5 + 27.7.8 §11 仍全部有效）+ 本阶段新增 UI 级缺口：

| Gap | 级别 | 影响的区 | 归属 |
|---|---|---|---|
| 无身份 API（who-am-I） | 后端 | Decision/Feedback署名 | 既有（ADR-017 记录） |
| 无全局审批端点（必须按项目） | 后端 | 收件箱默认视图 | 既有 API GAP |
| 反馈无后端（GAP-27.7-01） | 后端 | Feedback Loop | Phase D |
| Request Information 无原生动作（状态机冻结） | 后端/ADR | Decision Workspace | Phase D 决策（REJECT+前缀为过渡） |
| 无 URL 路由（状态链不可寻址/不可分享） | 前端 | 全站 | Phase A |
| supervisor active_alerts 有类型无数据消费 | 前端（待数据） | Escalation 原因 | Phase B（仅当数据支撑） |
| Auto Pass 无路由器/无清单 | 后端（27.8-R2） | 收件箱·已自动通过 | Phase C 前提 |
| AI Review 产物（ai-review-result+provider） | 后端（27.8-R1） | AI Review 区 | Phase C 前提 |
| 客户姓名/保额/健康告知/测算过程/金标集… | 后端 | Case Overview 等 | 见 27.7.7 §5 / 27.7.8 §11 |

原则不变：**不修改后端补数据**；缺口如实呈现（暂无信息/未部署），
等待逐项授权。

## 9. Implementation Roadmap（§十三）

| | **Phase A** Human-centric UI Foundation | **Phase B** Review Center Migration | **Phase C** AI Review Integration | **Phase D** Feedback Learning Loop |
|---|---|---|---|---|
| 目标 | 统一信息架构：L1–L4/空态/枚举字典/GAP 下脸/URL 路由骨架 | 统一 Review 工作流：收件箱+五区单表面，模块迁移（§4） | 接入 ai-review-result：AI Review 区+router 展示+已自动通过清单 | 反馈成环：后端实体+分类+金标集 |
| frontend | queue/dashboard/decision/feedback/chat 按 §6 改造；显示字典模块共享；App 引入轻路由（URL↔mode/选中项） | Review Center 容器组件；ApprovalDetail→tab；Dashboard 联动；supervisor 条件渲染 | AI Review 区 + Decision Workspace AI 列 + 清单 tab | 分类视图+金标集运营页+导出 |
| backend | **无** | **无**（仍按项目拉取；默认项目来自记忆/URL） | 增量：GET /api/runs/{id}/ai-review（镜像 card 端点模式）；依赖 **27.7.8-R1 已交付** | 反馈实体+端点（human-feedback-loop-v0.1 模型）；Request-Info 原生动作=ADR-017 修订决策 |
| schema | 无 | 无 | 消费 ai-review-result（27.7.8 §9，R1 产出） | feedback schema（锚定 Decision，refs 结构化） |
| tests | vitest：层级断言（L1 无内部标识）、空态三段式、字典覆盖、URL 恢复 | vitest：迁移后链路（收件箱→Center→决定→反馈）、旧断言迁移、不删信息断言 | vitest+后端契约测试：渲染 verbatim、fail-closed 未部署态、清单为空态 | 后端实体测试+vitest；金标集数据质量断言 |
| 前置 | 无 | Phase A | **27.7.8-R1 + provider 政策** | 无（可与 C 并行） |

依赖链：A→B→C；D 独立可并行。每阶段仍守 ADR-017（无控制耦合、
决定走既有端点）/ADR-018（反馈=证据）/ADR-004（确定性门不被 LLM 翻转）。

---

## STOP

本阶段仅输出本审计+架构提案（本文档）。未修改任何代码/UI/schema/
API/runtime/审批状态机；未创建 Agent。等待下一阶段授权。
