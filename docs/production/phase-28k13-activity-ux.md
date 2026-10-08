# Phase 28.K.13 — Consumer Real-Time Agent Activity UX

Date: 2026-09-27 · 零后端改动·零新依赖·零 commit。

## Step 1 审计结论（现有链路）

```text
EventBus → GET /api/runs/{id}/stream（SSE·既有）→ useRunStream →
runReducer("events") → consumerActivities() 折叠（E-3 DTO·单一映射
系统·upsert-by-key·未知 fail-closed·真实顺序）→ AgentActivity 渲染
（✓/● 已区分：completed=✓·running=●+进行中徽标+头部当前项）
→ 终态走 consumerTerminalView（E-5 优先级不变）
缺口实测：①✓/● 与增量本已存在——真正的静默源=QA 轮事件稀疏
（run_started→intent_classified→[60-200s 生成静默]→qa_answered）
②规划期的 eval_started/passed/failed 真实事件此前未入 DTO（被
default 隐藏）③无等待心跳
```

## 实施（最小改动·2 个源文件）

```text
web/src/state/activity.ts
  · eval_started/eval_passed/eval_failed → 折叠到既有 verify 活动键
    （复用既有文案表：正在核实相关信息/已完成信息核实+新增 failed
    文案"信息核实未完成"）——规划期每阶段校验=真实增量行
web/src/components/chat/AgentActivity.tsx
  · useActivitySilence 钩子：live 且 12s 无新事件（events.length
    不变）→ 渲染「● 这一步需要一些时间，请稍候」（data-testid=
    activity-heartbeat）；新事件到达即消失；终态不显示
  · 纯 UI 存活反馈——零后端操作声明·零伪造进度（文案常量·测试锁定）
未动：EventBus/SSE/Router/Intent/业务/grounding/WeKnora/artifact/
auth/ownership/终态优先级（consumerTerminalView 原样）·流式答案
面板原样（仅 content 流·reasoning 永不渲染——既有）
```

## 测试（新增 6 + 更新 1 期望）

```text
activity.test.ts +3：eval→verify（顺序/中途/失败文案）·T1 式规划
  全轨迹（understand→work→stage→verify→…→report 真实顺序）
AgentActivity.test.tsx +3：心跳阈值后出现（精确文案）·新事件清除·
  终态永不显示
更新 1：既有 planning 用例 fixture 本含 eval_passed——期望如实
  +1 行「✓已完成信息核实」（本阶段目标行为，非掩蔽）
T5/T6（未知事件/泄漏）=既有套件（activity.test T2-T6 + consumerDom
  FORBIDDEN 族）全绿复跑
```

## 回归

```text
web **227 passed + 2 skipped**（=221+6）· tsc clean
backend **794 passed + 2 skipped（零失败）**（本阶段零后端改动——
  记录性复跑）
Pilot :5273=vite dev（HMR 自动生效，无需重启）·:8123 未动
```

```text
Phase 28.K.13 Status: COMPLETE
Scope: Consumer 活动可见性（QA 静默期心跳 + 规划期 eval 真实增量行）
Files Changed: 4（activity.ts·AgentActivity.tsx·两测试文件）
Architecture Reused: EventBus/SSE/runReducer/consumerActivities DTO/
  consumerTerminalView/AgentActivity（零新引擎/通道/第二映射）
New Consumer Activity States: eval→verify 三态（复用既有键）·心跳等待行
Heartbeat Behavior: live+12s 无事件→固定文案；新事件即清；终态不显
Terminal State Behavior: 不变（failed>needs_review>waiting>completed）
Security/Leakage Tests: 未知事件 fail-closed+FORBIDDEN 族全绿（0 泄漏）
Consumer Regression: 227+2 · Backend Regression: 794+2 ·
Web Regression: 同 consumer · TypeScript: clean
Code Changes: 4 · Commit: NONE
Known Limitations: QA 轮生成期（最长 ~90-360s）仍只有心跳可显示——
  后端切片在生成期间本就不发事件（如需切片内真实里程碑=后端事件
  增发，属另阶段 Owner 决策）
STOP / NEXT OWNER DECISION: 观察 Batch-1 用户对进度可见性的实际
  反馈；（可选）是否授权 QA 切片生成期后端里程碑事件增发
```
