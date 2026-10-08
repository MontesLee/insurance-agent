# Phase 28.E-6 — Consumer Auth & Internal Space Boundary 报告

Date: 2026-09-26 · 范围：web/** + **runtime/server.py（仅端点角色声明，
R-06 既有机制的完成——STOP-4 例外条款：现有架构明确允许且属本阶段
必要范围）**。零新角色、零契约变更。

## Status

```text
E-6 STATUS: PASS
```

## Objective

使 Consumer/Operator/Developer 边界不止于 UI 隐藏，而是**实际访问
边界**：内部数据端点角色化（生产 fail-closed），消费者 API 面收窄
且测试固化。

## Pre-Audit（runtime/auth.py + server.py 实测）

- 认证机制完整（Phase 13 R-06）：静态 key（key:role:user）· 秩级
  OWNER(3)⊇REVIEWER(2)⊇OPERATOR(1) · `_identity_dep` **keys 已配置时
  缺失/未知凭据 → 401 fail-closed** · production 无 key 拒启动 ·
  无 key=文档化 loopback dev 模式（ident None 全放行）。
- 已挂门：diagnostics/metrics/create-run/control=OPERATOR ·
  approve/reject=REVIEWER。
- **缺口**：approvals list/detail、review-card、supervisor、alerts、
  notifications、control-commands、cases 七类内部**读取**端点无
  ident 依赖——keys 配置下无凭据亦可读（API boundary 洞）。
- Chat/runs 读/SSE 端点无 ident 依赖 → 消费者免钥可用（消费者鉴权
  模型=Owner 决策，维持 DEFERRED，不引入任何隐式模型）。

## Implementation

1. **后端**：上述 8 个端点补 `ident=Depends(_identity_dep)` +
   `_require_role`（REVIEWER：approvals list/detail/review-card；
   OPERATOR：supervisor/alerts/notifications/control-commands/cases）。
   无新角色、无 API 形状变更（401/403=auth.py 设计内响应）、
   dev 模式行为零变化。
2. **前端**：消费者 API 白名单**源扫描测试**（chat/shell 组件仅可
   调 agentConfig/createChat/getChat/postChatMessage/getRun/
   runEvents/getArtifact/streamUrl；approvals/supervisor/control/
   reviewCard/cases/createRun/metrics/diagnostics 禁引）。

## Boundary Changes

内部数据端点从"UI 不可见但仍可直连"→"生产 keys 模式下 401/403"。
Operator/Developer UI 行为不变（dev 模式 / 持 key 用户照常）。

## Tests（后端 5 + 前端 2，全绿）

```text
E6-T5/T6 无凭据读内部端点=401（8 端点） ✓
角色矩阵：REVIEWER 门 vs OPERATOR key=403；秩级 REVIEWER⊇OPERATOR ✓
E6-T7 无效 key=401 ✓  消费者面（POST /api/chats）免钥保持=201 ✓
dev 模式（无 key）内部读取照常（200/404） ✓
前端 API 白名单源扫描（chat+ConsumerShell 全组件）✓
（E6-T1..T4 路由边界=E-1 shell/route 测试 13 项维持绿；T9/T10=
consumerDom 禁词/DOM 测试维持绿）
```

## Regression

```text
backend: 734/734（729 基线 + 5 新增；server.py 改动后全量复跑）
web: 206 passed + 2 skipped（+2）· tsc: PASS
```

## Leakage Audit

消费者面不变（0 内部物）；内部面照常可用——未删除任何 Operator/
Developer 能力，仅生产鉴权语义补全。

## Architecture Invariants

无新 Runtime/角色/契约 ✓ · auth 策略=完成 R-06 既有声明 ✓ ·
消费者鉴权模型仍为 Owner 决策（未擅自引入 CONSUMER role）✓ ·
单 Runtime ✓ · 失败关闭（keys 模式 401/403；production 无 key 拒启）
✓。

## Files Changed

```text
M runtime/server.py（8 端点角色声明——R-06 完成）
A tests/runtime/test_e6_space_api_boundary.py（5）
A web/src/components/chat/consumerApiBoundary.test.ts（2）
```

## Deferred

CONSUMER 角色 / 消费者鉴权模型（Owner Decision——现有 chat 面免钥
是**现状**而非本阶段决定）· 内部空间前端鉴权 UX（登录/401 提示）。

## Owner Decision Required

消费者鉴权模型（公开 chat vs CONSUMER 角色 vs 登录）——E-0 起既列，
未自行决定。

## Final Gate

```text
E-6 STATUS: PASS → 自动进入 E-7
```
