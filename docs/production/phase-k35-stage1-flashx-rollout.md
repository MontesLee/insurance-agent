# K.35 Stage 1 FlashX Rollout

## Status

**STAGE1_ACTIVE_WITH_OBSERVATIONS**（生产配置已切换并验证；smoke 全过；
观察项=K.34 既知三项，非阻断）。

## Before

Step1: glm-5.3 · Step2+: glm-5.3-flash · QA: glm-5.3-flash（qa 回落 fast）

## Stage 1 Config（`.env`·经 Owner K.35 任务书授权）

```text
LLM_MODEL=glm-5.3            # 不变
LLM_FAST_MODEL=glm-5.3-flash → glm-5.3-flashx
LLM_QA_MODEL=                # 新增显式 = glm-5.3-flash
```

重启后 `/api/agent/config` 实测：`model=glm-5.3 · fast=glm-5.3-flashx ·
qa=glm-5.3-flash` ✓ · health 200 ✓

## Smoke Run

scenario: D（K.33 已用场景·原输入未改）
run_id: `run_fbe7c2ac8f13486e`
terminal status: completed/**COMPLETED**（E2E 69.3s·首内容 38.0s·观察 only）

## Actual Routing（agent.llm_call 逐调用实测）

Step1: glm-5.3（G1 ✓ 1/1）
Step2+: **glm-5.3-flashx（G2 ✓ 9/9 调用·零 flash 泄漏）**
QA: NOT EXERCISED（D 走规划路径·qa_answered=0；QA=flash 已由 K.34
执行级证据单独验证——15.9/14.7s flash 波段）

## Reliability

agent_step_error: 0 · schema rejection: 0 · invalid continuation: 0 ·
repair: 0 · needs_review: 0 · terminal failure: 0 → **SMOKE PASS**

## Known Observations（不修复·沿 K.34）

- G-1 citation baseline：本轮未触发 QA；出现时按既知签名区分，不归因
  FlashX
- provenance.model=""（QA 拒答路径·28.C-1 起预存）：KNOWN DEBT
- C early clarification：Product decision required（维持）

## Rollback Point

`tmp/env.rollback.k35`（切换前 `.env` 快照：LLM_FAST_MODEL=glm-5.3-flash·
LLM_QA_MODEL 未设）。回滚步骤：恢复快照（或改回 flash+删 QA 行）→
重启 → `/api/agent/config` 复证（K.32-C Case C 契约 + K.34 resolver
VERIFIED 先例）。

## Rollback Verification

未触发回滚（smoke 通过）——resolver 级验证已在 K.34 完成
[REUSED]；本阶段按规则未跑第二次真实 run。

## Production State

:8123 后端 **LIVE 于 Stage 1 配置**（.env 驱动·qa=flashx 泄漏防护
=显式 LLM_QA_MODEL=glm-5.3-flash）；:5273 前端未动；生产代码零改动
（K.35 仅 `.env` 两行）。

## Next Step

Stage 1 观察期（Owner 决定时长·建议 1-3 天）：probe-alpha 合成流量 +
真实用户小样本；观测=agent.llm_call（model/duration/status）+ K.32 §7
回滚阈值；期间补齐 QA provenance model 1 行（KNOWN DEBT）。观察期满
且无触发 → Owner 裁决 Stage 2（pilot 常驻已达成——实质为确认维持）/
Stage 3（正式默认迁移的 git 提交与文档化）。
