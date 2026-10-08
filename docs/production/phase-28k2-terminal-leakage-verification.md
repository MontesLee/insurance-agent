# Phase 28.K.2 — Consumer Terminal Internal-Stage Leakage：验证报告

Date: 2026-09-26 · 性质：**P2① 的授权修复已在 28.K.1 完成并三层验证**；
本阶段按 Owner 授权范围执行安全门核验 + 需求逐条映射 + 新鲜回归复跑。
**本阶段零代码改动**（目标行为与既有实现完全一致，不重复改码）。

## Safety Gate（改码前置核验——通过，且本阶段无改码）

```text
REAL_USER = 0 · Pilot 服务已停止 · :8123/:5273 无 LISTENING ·
:8000 停止 · 8 把 pilot key 在库未分发（tmp/ only）
```

## Objective ↔ Implementation 映射（P2①）

K.2 要求的行为 = 28.K.1 已交付的双层修复：

| K.2 Requirement | 实现（28.K.1） |
|---|---|
| needs_review Consumer 端仅自然语言业务文案 | 后端 `runtime/agent/agent.py`：finish 消息=固定中文模板（raw 工具 summary 不再拼接）；前端 `web/src/state/consumerView.ts`：`consumerTerminalView` 对 needs_review（系统模板态）固定输出既有映射层文案「这个结果需要进一步人工核实，确认后我会继续处理。」（= 仓库既有 TERMINAL_FALLBACKS 副本，符合"use existing copy conventions"） |
| Internal 端可保留 `product_candidate_provider…` | 事件流保留 tool summary + reason=`eval_failed_after_repair`（内部诊断不变） |
| 未知内部 stage fail-closed 到通用人类可读标签 | 任意 summary 内容（含 `unknown_internal_stage`）在消息层整体不进入；前端 needs_review 恒用固定副本（不透传 replyText）；activity/stage 标签既有 guard（consumerStageLabel 未知→「处理中」） |
| 不做内部 ID 动态转写 | 全部为固定常量/allowlist 映射（E-2/E-3/E-5 既有机制；无新展示架构） |
| Consumer 禁露 provider/registry/agent/tool/skill/stage/状态码/reason code/run_id/artifact_id/eval_id/approval_id | consumerDom FORBIDDEN 断言族（E-2/E-3 既有 + K.1 扩展 5 项）+ 本报告新鲜全绿 |

## Tests（K.2 七项要求 → 既有用例，本阶段新鲜复跑）

| # | K.2 要求 | 用例 | 结果 |
|---|---|---|---|
| 1 | known needs_review stage → 人类可读文案 | `test_k1_needs_review_copy` 3×param（含 28.K 原始泄漏串）+ E5-T4 | PASS |
| 2 | 内部 provider/stage 标识符不出现在 Consumer 输出 | 同上逐 token 断言 + consumerView K.1（投毒 replyText→映射副本） | PASS |
| 3 | 未知 stage → 通用安全回退 | `unknown_internal_stage` param + 内部词族 param（run_/agent/registry/QA_REFUSED…） | PASS |
| 4 | 无禁露内部标识符 | consumerDom.test FORBIDDEN 族（+K.1 扩展）×3 用例含 K.1 终态旅程 | PASS |
| 5 | 既有 needs_review 行为不变 | §20/§44（消息含「质量校验」）· §34/§35 模板未动（test_agent_loop） | PASS |
| 6 | 既有 Consumer E2E 通过 | web 全量（221+2，含 identity/artifactDelivery/shell/seedRegression/E2E 契约） | PASS |
| 7 | 既有泄漏测试绿 | consumerDom/consumerView/consumerApiBoundary/activity（含于全量） | PASS |

## 新鲜回归（2026-09-26 本阶段复跑）

```text
targeted   test_k1_needs_review_copy + test_agent_loop → **15/15**
backend    full battery → **771 passed + 2 skipped（零失败）**
web        full suite → **221 passed + 2 skipped** · tsc → **clean**
（全部本阶段新鲜复跑；无任何并发 live 负载——pilot 已停）
```

## Forbidden-Scope Audit

```text
零触碰：Intent/Router/Authority/Registry/三 Agent/Grounding/WeKnora/
Catalog/LLM Gateway/citation/retrieval/auth/ownership/governance/
retention/persistence/artifact 语义/event 词汇/workflow/推荐逻辑/
REAL_USER 配置/Pilot 部署/pilot keys/生产部署/后端执行语义
（28.K.1 的改动本身也仅限：agent.py 消息模板 + consumerView 映射 +
测试——均在本 K.2 授权范围"Consumer presentation/mapping/terminal-copy
layer"内；本阶段在其上零新增改动）
```

## Runtime Impact

```text
本阶段启动的进程：仅测试进程（pytest/vitest/tsc，有界、已退出）
未启动任何长驻服务 · 未重启 Pilot · REAL_USER=0 · 用户数据触碰=0
```

## Final

```text
Phase 28.K.2 Status: COMPLETE（objective 已由 28.K.1 满足；本阶段=
安全门+映射+新鲜验证，零代码改动）
Commit: NONE
Next: WAITING FOR OWNER: PILOT RELAUNCH AUTHORIZATION
```
