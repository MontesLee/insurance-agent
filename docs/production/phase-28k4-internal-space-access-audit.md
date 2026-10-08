# Phase 28.K.4 — Internal Space Access Audit & Owner Entry 报告

Date: 2026-09-26 深夜 · 性质：**AUDIT（Decision A → ZERO CODE CHANGE）**。
Pilot 全程未动（:8123/:5273 持续 LIVE·未重启·未分发 key·REAL_USER 保持 0）。

## 结论

**Internal Space already accessible.** 四路由全部存在且按既有 RBAC 正常
工作；Owner/Operator/Developer 经"#/chat 身份门录入内部凭据 + 直达
内部 URL"即可进入。零代码改动；无需恢复任何旧入口。

```text
Consumer:
#/chat

Operator:
#/operator/review

Developer:
#/developer/dashboard
#/developer/console
```

## Current Access（实测 2026-09-26 深夜，pilot :5273/:8123）

| Space | Route | Accessible | Auth | API Data |
|---|---|---|---|---|
| Consumer | #/chat | YES（SPA 200·jsdom 壳测试） | IdentityGate（keys 模式 401→密钥门） | whoami/chat/runs/artifacts ✓ |
| Operator | #/operator/review | YES（直达 URL·InternalShell 渲染·内部导航） | 需 ≥OPERATOR 凭据（经 #/chat 门录入后跳转） | queue 页面可达；**approvals/review-card 数据=REVIEWER 门**（OPERATOR 403=设计行为） |
| Developer | #/developer/dashboard | YES | 同上（内部值班凭据） | cases/supervisor/diagnostics/governance-audit ✓（OPERATOR 200） |
| Developer | #/developer/console | YES | 同上 | agent/config 开放·POST /api/runs OPERATOR 门过（404=未知 case 诚实） |

## Authentication（实际方式）

```text
Consumer:  8 把 pilot-user key（未分发）；IdentityGate 录入 → whoami
           解析 consumer:<user>；匿名=401 fail-closed。
Operator:  内部值班凭据（≥OPERATOR）。pilot 集=rbac:pilot-ops
           （OPERATOR）。录入路径=#/chat 身份门粘贴该 key →
           whoami=rbac:pilot-ops → 直达 #/operator/review 等 URL。
Developer: 无独立 DEVELOPER 角色（既有 RBAC=OWNER/REVIEWER/
           OPERATOR/CONSUMER——未改）；Developer 空间=任何 ≥OPERATOR
           内部凭据（同一把 pilot-ops 即可）。
Owner:     同 Operator 通道（如需 REVIEWER/OWNER 级数据见下）。
```

## Authorization（实测矩阵：anon / consumer / operator）

```text
endpoint                          anon  consumer  operator
/api/health                        200    200       200   （开放·设计）
/api/agent/config                  200    200       200   （开放·设计）
/api/cases                         401    403       200
/api/projects/x/supervisor         401    403       404（门过·x 不存在）
/api/governance/audit              401    403       200
/api/diagnostics                   401    403       200
POST /api/runs                     401    403       404（门过·诚实）
/api/approvals/x                   401    403       403  （REVIEWER 门·设计）
/api/projects/x/approvals          401    403       403  （同上）
/api/runs/x/review-card            401    403       403  （同上）
```

## Consumer Isolation

```text
Internal UI exposed in Consumer:  NO（ConsumerShell 零内部链接/零后台/
  Admin/Developer 按钮——shell+consumerDom 测试锁定）
Internal API exposed to Consumer: NO（矩阵全 403；URL 知晓≠授权——
  内部 SPA 页对 consumer 身份仅渲染壳，数据被服务端拒绝）
legacy webui:mode exposed:        NO（route.ts 不读取；负测锁"legacy
  key 不再选择空间"；旧 Dashboard/Developer Mode/Inspector 入口=
  E-1 有意移除，未恢复任何旧入口）
```

## 特别检查（§5）答录

- 登录/认证入口：存在=#/chat IdentityGate（keys 模式）；内部页共用
  该 localStorage 凭据（api client authHeaders）。
- Owner 进入方式：#/chat 录入内部 key → 直达内部 URL（InternalShell
  提供三页互导 + 返回对话）。
- Pilot key 只能用于 Consumer？——否：pilot 集 8+1+2；CONSUMER key
  只给消费者；rbac:pilot-ops 供内部面。
- Operator/Developer 需不同 credential？——内部空间共用 ≥OPERATOR
  凭据；仅 approvals/review-card 数据需 REVIEWER 级。
- 隐藏入口/webui:mode/deprecated route：无暴露（fail-safe 路由：未知
  一律落消费者）。

## 发现（记录，不修改）

> **REVIEWER 级凭据缺口**：审核队列数据（approvals/review-card）按
> 既有 RBAC 为 REVIEWER 门；pilot 凭据集未配备 REVIEWER/OWNER 级
> key（当时按"消费者试点+OPERATOR 值班"最小集配置）。若 Owner 需在
> 试点窗口查看审核队列数据，需另行授权增配一把 REVIEWER duty key
> （tmp/pilot-keys 一行级增补）——本阶段按禁令未创建。

## Tests（新鲜复跑）

```text
backend E-6 边界 5/5 · web shell/identity/consumerDom/app-route 23/23
（含：operator review 打开内部面·未知路由 fail-safe 消费者·legacy
key 失效·身份门流·consumer DOM 零内部标记）
```

## Git

```text
ZERO CODE CHANGE（tracked-modified 30=既有 span 原样；本阶段新增仅
本报告）。Pilot 未重启/未停止/未分发 key/REAL_USER 保持 0（bus=0）。
```
