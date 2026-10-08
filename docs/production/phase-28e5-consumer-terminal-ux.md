# Phase 28.E-5 — Consumer Terminal UX 报告

Date: 2026-09-26 · 范围：web/** only。

## Status

```text
E-5 STATUS: PASS
```

## Objective

建立确定性的**消费者终态呈现**：answer / refusal / clarification /
needs_review / error 五态自然语言化 + 优先级规则（绝不矛盾共存）+
保守回退文案——纯 presentation，后端 status 契约零改动。

## Pre-Audit

E-3 后终态呈现分散于：consumerTerminalHeader（卡片头）· 服务端回复
文本（answer/refusal/clarification 正文=后端诚实文案）· agent-unavailable
横幅 · stream 错误文案（E-3 已消费者化）· finalize 回退「（本轮无回复）」。
缺：统一分类 + 确定性优先级 + refused/answered 区分（run_completed
data.result_status 可用但未消费）。

## Implementation

`consumerView.ts` 新增 `consumerTerminalView(status, resultStatus,
replyText, hasArtifact)` → `{state, message, artifact}`：

- **优先级（固定）**：failed→error · needs_review→needs_review ·
  waiting→clarification · completed+QA_REFUSED→refusal · completed→
  answer。终态 status 支配一切；**artifact 仅 answer&&真实事件**——
  refused/failed/waiting 即使被投毒 hasArtifact=true 也强制 false。
- **文案**：服务器文本优先（它本身就是消费者级诚实文案：答案/拒答
  说明/澄清问题）；空缺时按态回退（拒答/核实/补充信息/稍后再试——
  无事实、无原因、无内部词）。
- ChatLayout finalizeAgent 接线：文本经 terminalView（含
  result_status 分类）；getChat 失败 → error 回退（原「无法读取
  Agent 回复。」）。

## Boundary Changes

无新边界；terminal 呈现纳入 consumerView allowlist 体系。

## Tests（7 新增，全绿）

```text
E5-T1 success（含空回复诚实回退） ✓  T2 clarification ✓
T3 refusal（诚实文案+artifact 强制关）✓ T4 needs_review（无审批内部物）✓
T5 error（保守文案）✓ T6 优先级投毒（failed/waiting/needs_review/
refused × hasArtifact=true 全部矛盾组合=不可信输入→确定性输出）✓
T8/T9/T10 输出零内部状态码/id + 无伪成功 + 无伪产物 ✓
（T7 refresh/reconnect=既有 consumerDom remount 用例维持绿）
```

## Regression

```text
web: 204 passed + 2 skipped（E-4 基线 197+2 → +7）
tsc: PASS · backend: 729/729（BATTERY_E5，零 runtime 改动）
E-2/E-3/E-4 回归：全绿（含于 204）
```

## Leakage Audit

终态输出：QA_REFUSED/WAITING_USER/INTERNAL_ERROR/run_/case_/trace/
approval/review/HITL/eval/httpx/timeout/stack/provider/model/runtime/500
= **0**（T4/T5/T8 断言）。

## Architecture Invariants

后端 status 契约 UNCHANGED ✓ · 无伪成功/伪产物 ✓ · Completion≠Artifact
维持 ✓ · 单 Runtime ✓ · allowlist 体系维持 ✓。

## Files Changed

```text
M web/src/state/consumerView.ts（terminalView + 回退表）
M web/src/state/consumerView.test.ts（+7）
M web/src/components/chat/ChatLayout.tsx（finalize 接线）
```

## Deferred

终态视觉布局精修（文案已消费者级，视觉=§49 保持现状）· waiting 轮
多轮续答体验细节（E-7 Journey D 验证）。

## Owner Decision Required

无新增。

## Final Gate

```text
E-5 STATUS: PASS → 自动进入 E-6
```
