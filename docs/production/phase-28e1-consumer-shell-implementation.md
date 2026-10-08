# Phase 28.E-1 — Consumer Shell + Navigation Boundary Implementation 报告

Date: 2026-09-26 · 范围：**web/ only**（+ 本报告）。runtime/schema/config/
治理文档零触碰（git 实证：runtime 3 文件 diff=既有 M 系列 span，非本
阶段产物）。

## 1. Executive Summary

三空间产品壳建成：**Consumer Space（#/chat，默认）**与 **Internal
Space（#/operator/review · #/developer/dashboard · #/developer/console）**
由 **URL（hash 路由）**划分——未知/畸形路由一律回落消费者面（fail-safe，
URL 永不可能意外打开内部面）；legacy `webui:mode` localStorage 不再
参与空间选择。消费者面零内部入口、零内嵌 Inspector（实测快照 0 内部
标记）；内部面完整保留（审核/审批/工作台/Dashboard/运行控制台/Debug/
Demo 均未删除，仅移入内部导航之后）。chat 复用既有 Runtime——实测
grounded 交付探针（U3：insurance_qa → Router authority → knowledge-qa
slice → grounded 答案+[E1][E2][E4] 引用，31s）。**AUTH POLICY =
DEFERRED OWNER DECISION**（导航边界≠安全边界；未创建 CONSUMER 角色，
未改 auth 策略）。

## 2. Pre-Implementation Snapshot

branch=main @ 9407a84 · tracked-modified=9（M 系列 span，与 E-0 审计
一致，PRE_EXISTING_CHANGES=YES 未覆盖）· 前端入口 index.html→
src/main.tsx→App.tsx（无路由库）· 旧壳=App.tsx 单壳 4-mode（state+
localStorage）· API client 单出口（src/api/client.ts）· SSE=useRunStream
（续传）· runtime/auth.py 只读确认（OWNER/REVIEWER/OPERATOR + 端点
门 + production fail-closed；未配置=dev loopback）。治理文档核对：
DECISION_FREEZE 无独立文件（决策记录在 docs/production/decisions/，
按仓库实际结构读取）；无新架构漂移；Router Authority 无变化
（:8000 仍为 owner 授权 full 灰度，代码默认 slices）。

## 3. Current Shell Before（E-0 已审计，本阶段复核）

单壳四入口无条件渲染；chat 面无条件内嵌 RuntimeInspector（xl+）；
Agent/Demo 切换 + ⚙ Developer Mode 恒可见；mode=localStorage 持久化。

## 4. Target Shell（已实现）

```text
Web App（URL=空间边界）
├── Consumer Space  #/chat（默认；/ 与未知路由回落于此）
│   └── 保险顾问助手：会话列表 | 消息流+活动+产物卡 | 输入
└── Internal Space（独立导航+独立路由；含"← 返回对话"）
    ├── Operator   #/operator/review（队列→审批详情→工作台，子导航保留）
    └── Developer  #/developer/dashboard · #/developer/console
                   （PilotDashboard / Phase-2 运行控制台：cases/Inspector/Trace/Debug/Demo）
```

## 5. Consumer Surface（新建 `components/shell/ConsumerShell.tsx`）

产品化头部（保徽标+「保险顾问助手」+副题）+ ChatLayout（消费者化，
见 §9）。**无任何内部链接**（内部面仅可经 URL 直达——有意设计，
E-6 鉴权决策前不做"隐藏入口"假边界）。欢迎屏 4 个自然语言建议
（点击仅填充不发送）。

## 6. Internal Surface（新建 `components/shell/InternalShell.tsx`）

内部头部（INT 徽标+「内部工作台 · 非消费者面」）+ 导航（审核队列/
Dashboard/运行控制台 + ← 返回对话）。Operator 子导航（队列→详情→
工作台）原样保留（与 E-1 前行为一致）；DeveloperMode 的返回指向
Dashboard（原为 chat）。**未删除任何内部能力**。

## 7. Navigation Architecture

新增 `src/app/route.ts`（~70 行，零依赖）：`parseRoute`（纯函数）+
`useRoute`（hashchange 监听）+ `navigate`。路由表 = ROUTES 常量。
**Fail-safe 规则**：空/根/`/chat`/未知/畸形（含 `#/developer`、
`#/developer/inspector?run=x`）→ 一律 `{space:"consumer"}`。

## 8. Route Boundary

- 刷新/直达/回退/前进均由 URL 恢复空间（实测 + jsdom 测试）。
- legacy `webui:mode` 不再读取（测试：localStorage=developer 时仍落
  消费者面）。
- **这不是安全边界**：AUTH POLICY = DEFERRED OWNER DECISION（E-0
  §12；runtime/auth.py 在位未配置、无 CONSUMER 角色——均未触碰）。

## 9. Chat Reuse（ChatLayout 消费者化重构）

保留（零行为改动）：chatsReducer/localStorage 会话存储、serverChatId
绑定、send=POST /api/chats/{id}/messages（agent 分支原逻辑）、
finalize/冲突横幅/stale-activity、SSE stop/resume（仅断开视图）。
移除（内部面迁移）：AgentInspectorPanel 内嵌（列+抽屉）、
useRunMeta、Agent/Demo 模式切换、⚙ Developer Mode 入口、demo-switch
按钮（503 横幅文案消费者化："暂时无法回答：…"）。Composer 固定
`mode="agent"`（组件本体未改；demo 分支仅在 Developer 控制台语境
不可达，代码保留待 E-2/M5-cleanup 处置）。

## 10. Activity Reuse

AgentActivity 组件与 activity.ts 映射层**零改动**（raw event 从不
直显——既有测试断言中文文案）。已知递延（E-3）：8 阶段清单对 QA 轮
不适用、"分析完成"措辞、`分析结束（waiting）`内部词、
`Portfolio Demo Mode · {caseId}` 标签（U3 实测仍在——既有泄漏，
E-2/3 范畴，壳层未新增）。

## 11. Artifact Reuse

ArtifactCard + ReportModal（insurance-report Markdown）原样复用，
在消费者面正常出现（U3 实测卡片+按钮）。已知递延（E-2/E-4）：
卡片文案 `insurance-report · run xxxxxxxx` 泄漏、QA 轮被附加虚构
报告卡（finalizeAgent 既有路径，U3 grounded 轮同样触发——记录为
**最高优先 E-2 缺陷**）。未新增类型/后端/深链/导出。

## 12. Authorization Boundary

**UNCHANGED**。只读确认：auth.py 三角色+端点门+production fail-closed；
前端未携带鉴权（与 E-1 前一致）；未创建 CONSUMER 角色；未开放公开
访问。代码注释与路由模块明示 DEFERRED OWNER DECISION。

## 13. Internal-ID Exposure Status

- **Shell 层新增暴露 = 0**（消费者面实测 grep：审核队列/Dashboard/
  Developer Mode/run_id/case_id/演示 Demo/Pipeline/Trace = 0 命中）。
- 既有暴露（递延 E-2，未修）：ArtifactCard `insurance-report · run…`；
  冲突横幅 `Run: …`；AgentActivity demo 标签 + bm-* id；会话侧栏
  罐头报告预览（U1/U3 遗留 chat state 文案）。
- Inspector（run_id/case_id/Trace 主源）已随壳重构移出消费者面。

## 14. Runtime Reuse Evidence（实测探针 U3，SCRIPTED_PROBE）

```text
消费者壳输入「百万医疗险的等待期是什么意思？」(16:45:48Z)
→ POST /api/chats/{id}/messages → intent_classified insurance_qa
  conf=1.00 src=rule → slice_decision knowledge-qa fired reason=
  authority（shadow 权威记录）→ qa_answered grounded → run_completed
  （31s）→ UI 渲染带 [E1][E2][E4] 引用的自然语言答案 ✓
实例 bus runs=3=U1/U2/U3（全探针；REAL_USER=0 维持）
```
无第二 Runtime、无前端路由/直选（发送=原样文本）。

## 15. Architecture Invariants（§22，11/11）

1 单一 Runtime（消费者仅经既有 /api；无新 origin）✓ 2-4 消费者无
Agent/Workflow/Tool 选择器（输入=自由文本；实测）✓ 5 Router 唯一
dispatch（U3 authority 实证）✓ 6 Intent≠Prompt（未触碰）✓ 7-8
Event/Artifact 契约零改动（types/runtime.ts 本阶段未动）✓ 9
Grounding/Citation 零触碰 ✓ 10 ROUTER_AUTHORITY 零变化（代码默认
slices；:8000 灰度未动）✓ 11 REAL_USER 未开放（bus=3=探针）✓

## 16. Tests（新增 13，全绿）

- `src/app/route.test.ts`（3）：解析/未知路由 fail-safe/内部路由精确。
- `src/components/shell/shell.test.tsx`（10）：默认入口=消费者；消费者
  零内部入口+零 Inspector+零 demo 切换；legacy mode 失效；未知路由
  回落；operator/developer 直达；hash 前进后退切换；内部导航切换；
  会话跨 remount 持久（刷新等价）；navigate() 驱动。
- 更新 1：Composer.test 欢迎屏断言（旧断言强制"Portfolio Demo Mode
  诚实披露"——该披露自 28.x 起失实；新断言=不含过时 demo 文案）。
- 更新 2（backend 守卫按本意强化）：B6 的
  `test_frontend_mapping_not_production_authority` 曾以字符串钉住旧
  实现细节（要求 ChatLayout 含 chatMode 切换）——E-1 后改为更强
  断言：ChatLayout **禁止** `api.createRun`（消费者 chat 不得直建
  run）+ 禁止 `chatMode`（agent-only）+ 禁止 `mapPromptToCase`
  （关键词映射不得居于消费者布局）；agent-id 禁引断言原样保留。
  守卫语义（前端不做生产路由）不变且增强。
- 既有覆盖复用：AgentActivity 中文文案测试（raw event 不直显）。

## 17. Regression

```text
backend: PASS — 729/729（首轮 728/729 唯一失败=B6 前端结构守卫钉住
         旧 chatMode 字符串；按守卫本意强化更新后复跑全绿——见
         §16 更新 2；runtime 零改动）
web:     PASS — 161 passed + 2 skipped（原 148+2 + 新 13）
tsc:     PASS — clean
（B4/M4/M3 含于 729 全绿之内）
```

## 18. Files Changed（本阶段全部）

```text
M  web/index.html                       （标题/lang 消费者化）
M  web/src/App.tsx                      （路由壳重写）
M  web/src/components/chat/ChatLayout.tsx（消费者化：去 Inspector/模式/入口）
M  web/src/components/chat/WelcomeScreen.tsx（移除失时 demo 声明段）
M  web/src/components/chat/Composer.test.tsx（欢迎屏断言更新）
A  web/src/app/route.ts + route.test.ts
A  web/src/components/shell/ConsumerShell.tsx
A  web/src/components/shell/InternalShell.tsx
A  web/src/components/shell/shell.test.tsx
```

## 19. Files Explicitly Not Changed

runtime/**（含 intent/router/agents/grounding/orchestrator/server）·
schema/** · config/** · docs/production/architecture/** · ADR* ·
web/src/types/runtime.ts（事件契约类型）· runReducer/chatState/
activity.ts/ArtifactCard/AgentActivity/Composer 本体 · api/client.ts ·
ReviewQueue/ApprovalDetail/ReviewWorkspace/PilotDashboard/DeveloperMode
（内部组件原样）· runtime/auth.py。

## 20. Owner Decisions Deferred

① Consumer 鉴权模型（公开/CONSUMER 角色/登录）——E-6；② 内部空间
访问控制激活（auth 配置=Owner 凭据动作）；③ E-2..E-7 逐段授权；
④ 助手身份文案（现用「保险顾问助手」壳标题——可调）。

## 21. Known Limitations（递延，非本阶段缺陷新增）

1. QA 轮虚构报告卡 + 卡片 run 泄漏（E-2 最高优先——grounded 轮亦
   触发，实测证据在案）。2. AgentActivity 规划时代模板/demo 标签
   （E-2/E-3）。3. 会话列表=localStorage（PERSISTENCE 部分缺口，后端
   立项待 Owner）。4. 内部面无鉴权（URL 即达；E-6）。5. hash 路由
   无嵌套子路由（operator 子导航为组件内状态——刷新回队列列表，
   可接受 v1 形态）。

## 22. Next Phase Recommendation

**28.E-2 Consumer Rendering**（consumerView DTO + QA 终态模板修复 +
ID/文案清除——最高优先缺陷即在此段）；E-3/E-4/E-5 可随后并行。

## 23. Scope Confirmation

```text
Business code changes = web/** only（上列 10 文件）
Runtime changes = 0 · Router changes = 0 · Agent changes = 0
Contract changes = 0 · Architecture changes = 0（壳内重组，无新引擎）
Authorization policy = UNCHANGED（DEFERRED OWNER DECISION）
CONSUMER role = NOT CREATED · WeKnora = NOT CONNECTED
REAL_USER = NOT ENABLED · ROUTER_AUTHORITY = UNCHANGED
```
