# Phase 28.E-4 — Consumer Artifact Delivery 报告

Date: 2026-09-26 · 范围：web/** only。

## Status

```text
E-4 STATUS: PASS
```

## Objective

消费者侧真实 Artifact 交付：识别（真实 artifact_created 事件，E-2 已
建立）→ 查看（复用 Markdown Modal）→ **导出（Markdown 下载，零新后端
契约）**；allowlist/fail-closed/内部 id=0 全面测试化。

## Pre-Audit

ArtifactCard/ReportModal（E-2 白名单化）· consumerView.toArtifactView
（insurance-report 唯一消费者类型）· finalize 门控 hasRealArtifact
（completed && artifact_created@report-generation）· artifact API=
GET /api/runs/{id}/artifacts[/{type}]（以 run_id 寻址——**深链不可
消费者安全实现**）。

## Implementation

1. **导出**：ReportModal 新增「下载」按钮——对**已合法获取**的
   rendered_report 构造 Blob（text/markdown）下载，文件名=
   消费者标题（客户保险需求分析报告.md，无 id/类型）；内容加载完成
   前禁用；无新后端契约、无新 Artifact Contract 消费。
2. **可访问性**：modal aria-label=消费者标题；下载/关闭按钮
   aria-label 均消费者文案（无 id/类型）。
3. **深链：DEFERRED**——现有 artifact 寻址仅 run_id；消费者 URL 不
   得含内部 id，且为 artifact 造 opaque token=新契约 → 按 §11/§12
   记录 DEFERRED — requires Owner/architecture authorization。

## Boundary Changes

无（allowlist/门控/Modal 均为 E-2 既有；本轮仅新增导出动作与 a11y）。

## Tests（8 新增，全绿）

```text
E4-T1 真实报告→卡片+Modal+内容 ✓  T6 markdown 渲染（年龄等）✓
E4-T2 无 artifact 消息→零卡片 ✓   T3 未知类型→零渲染 ✓
E4-T4 卡片+Modal 内部 id/类型=0 ✓ T5 artifact 类路由→消费者回落 ✓
E4-T7 remount(刷新等价)卡片保持+Modal 重开 ✓
E4-T8 投毒/取回失败→消费者文案（无 ECONNREFUSED/trace/run id）✓
E4-T9 内部类型(knowledge-evidence/client-profile)不可见 ✓
下载可用性+消费者安全文件名 ✓
```

## Regression

```text
web: 197 passed + 2 skipped（E-3 基线 189+2 → +8）
tsc: PASS · backend: 729/729（BATTERY_E4，零 runtime 改动）
E-2/E-3 回归：全绿（既有 12+31 项含于 197）
```

## Leakage Audit

卡片/Modal/aria/文件名：run_/case_/artifact_id/type/version/provider/
eval/approval/trace = **0**（T4/T8 断言）。

## Architecture Invariants

单 Runtime ✓ · Artifact Contract UNCHANGED ✓ · Completion≠Artifact
维持 ✓ · 未知类型 fail-closed ✓ · 无第二 artifact 系统 ✓。

## Files Changed

```text
M web/src/components/chat/ArtifactCard.tsx（下载+a11y）
A web/src/components/chat/artifactDelivery.test.tsx
M web/src/app/route.test.ts（E4-T5）
```

## Deferred

深链（需 Owner/架构授权 opaque artifact 寻址）· HTML/PDF 导出
（后端契约）· 旧持久化会话的历史卡片（用户数据不动）。

## Owner Decision Required

无新增（深链/PDF 属既有 Deferred 项）。

## Final Gate

```text
E-4 STATUS: PASS → 自动进入 E-5
```
