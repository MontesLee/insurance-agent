# Phase 28.K.15 — Batch-1 User Access & Handoff Readiness

Date: 2026-09-27 · READ-ONLY（零改动·零重启·零 synthetic·零业务请求）。

## Status

```text
READY（本地访问模型下；唯一 Owner 动作=交付两把 key+确认用户位置）
```

## Pilot

```text
REAL_USER=ON · Batch-1=2 invited · backend :8123 LIVE（K.13+F1+F2·
startup 03:34:43Z）· frontend :5273 200 · WeKnora :8080 401-alive ·
PG :5433 OPEN · authority=pilot full（临时·未动）
```

## User 01

```text
identity: READY（consumer:pilot-user-01·CONSUMER·authenticated——
  whoami 实证；且已真实使用过一次：run_50389328）
key: READY（distribute 文件存在·token 唯一·whoami 通过）
access: READY（本机 localhost 模型——其真实轮即经 127.0.0.1 进入）
```

## User 02

```text
identity: READY（consumer:pilot-user-02·CONSUMER·authenticated——
  whoami 实证）
key: READY（同上·token 唯一）
access: READY（若与本机同机）——⚠ 若用户 02 在其他电脑/手机：
  REMOTE_USER_ACCESS = BLOCKED（reason = localhost URL is not
  remotely reachable；需 Owner 提供可访问地址——未自行搭建任何
  tunnel/代理/公网服务）
```

## Access Model

```text
LOCAL（用户 01 已实证经本机使用；vite 绑定 [::1] 仅 loopback）
```

## 核验明细（§2-§6）

```text
Key/安全：key 文件 gitignored ✓·git tracked=0 ✓·status 零行 ✓·
  分发 token 无重复分配 ✓·后端访问日志 0 Bearer 行 ✓·obs 结构化
  日志 0 敏感行 ✓
Consumer UI 边界（引用既有证据）：#/chat 默认产品面（E-1 fail-safe+
  shell 测试）·无 Dashboard/Developer/operator 路由暴露·无内部
  id/provider/tool（consumerDom FORBIDDEN 族+K.4 审计）
Auth/Ownership（引用既有证据）：B-02 套件 15/15（统一 404·跨用户
  隔离·spoof 忽略·401 fail-closed）·K.3/K.12 live 复核·ownership
  随 chat/run 绑定（服务端）
```

## 极简用户交接说明

已生成 `tmp/pilot-keys/USER-INSTRUCTIONS.txt`（8 条：地址/自己的
key/真实问题/不共享/无需按题目问/慢可等/错误截图反馈/不刻意试探；
含受控试点重启提示）。未向用户透露任何测试目标/内部概念/已知问题。

## Safety（引用既有证据）

```text
cross-user=0 · hallucination=0 · grounding bypass=0 ·
internal leakage=0 · wrong routing=0（K.8-K.14 全程；首条真实轮
NO_ISSUE）
```

## Required Owner Action

```text
1. 将 tmp/pilot-keys/distribute/pilot-user-01.key 私下交付用户 01
2. 将 tmp/pilot-keys/distribute/pilot-user-02.key 私下交付用户 02
3. 确认两位用户都在本机使用（http://localhost:5273）；若任一用户
   在远程设备，需 Owner 自行提供可达 URL（当前未建任何远程访问）
4. 交付时附 tmp/pilot-keys/USER-INSTRUCTIONS.txt
其余：无需任何代码/配置变更。
```
