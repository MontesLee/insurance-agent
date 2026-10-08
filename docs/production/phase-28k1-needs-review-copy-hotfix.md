# Phase 28.K.1 — Consumer P2-① Leakage Hotfix 报告

Date: 2026-09-26 · 性质：**最小 hotfix**（仅 needs_review 消费者文案边界）。
禁令清单全遵守：Intent/Router/Grounding/WeKnora/Agent workflow 语义/
Artifact/Auth/Ownership/Governance/Event 词汇/citation gate/QA·Product-QA
prompt/retrieval/embedding/CJK/Full Authority/REAL_USER 开关/Pilot 范围
——全部零触碰。

## 缺陷（28.K P2-①）

needs_review 终态消息 = 安全中文模板 + **追加的 raw 工具 summary**：

```text
这一步没有通过系统的质量校验（自动修复后仍未通过），我已停止分析并标记为需要人工复核。

product_candidate_provider did not pass evaluation after repair — needs human review
```

源头：`runtime/agent/agent.py` eval-block finish 路径将
`_clip(result.summary)` 拼进 AgentOutcome.message（工具 summary 含内部
stage/tool 名）。

## 修复（双层，各走既有层）

```text
1. 源头（backend）  agent.py — needs_review finish 消息 = 固定自然语言
   模板 ONLY；raw summary 不再拼接。内部细节保留在事件流
   （tool_* summary + 终态 agent_decision reason=
   eval_failed_after_repair）——Developer/Operator 诊断能力不变。
2. 映射层（frontend E-5） consumerView.ts — needs_review 是系统模板态
   （绝非业务内容）：consumerTerminalView 对 needs_review 固定输出映射
   层副本（"这个结果需要进一步人工核实，确认后我会继续处理。"），
   不透传服务端模板文本。业务态（answer/refusal/clarification）仍用
   服务端正文。接线点=ChatLayout finalize（transcript 终稿文本即
   terminal.message）→ 即使后端模板回归，消费者 DOM 也不会出现内部串。
```

不做的（设计裁定维持）：前端改写业务消息正文（E-2 "不改写已交付
事实文本" ruling 不变——防御在系统态映射层，不在业务文本层）。

## Tests（新增/强化）

```text
backend  tests/runtime/test_k1_needs_review_copy.py（5/5）
  Case A  28.K 原始泄漏串（product_candidate_provider…）→ 消息=固定
          模板，逐 token 零出现 ✓
  Case B  unknown_internal_stage / 内部词族（run_/agent/registry/
          QA_REFUSED…）→ 零出现 ✓
  Case C  内部诊断不变：事件流保留 tool summary + reason=
          eval_failed_after_repair；transcript 终稿=模板 ✓
  +      模板本体纯中文（零 ASCII 标识符）契约 ✓
web     consumerView.test.ts +K.1（投毒 replyText→映射层副本零内部串；
          业务态仍透传）✓
        consumerDom.test.tsx：FORBIDDEN += product_candidate_provider/
          unknown_internal_stage/"did not pass evaluation"/
          "needs human review"/eval_failed_after_repair；+K.1 终态旅程
          DOM 用例（自然语言在场+全 FORBIDDEN 零出现）✓
```

## Live 复证（隔离 pilot 实例重启后）

```text
重启 :8123（同 env：strict controlled_pilot·WeKnora·pilot full
authority；REAL_USER=0 全程——无真用户、仅探针主体；旧实例进程清理
后端口释放）。复跑 Journey C 两轮（live glm+live WeKnora）→
turn-2 终态 needs_review → **最终消息 = 纯中文模板，8 项泄漏检查
（product_candidate_provider/unknown_internal_stage/did not pass
evaluation/needs human review/eval_failed_after_repair/registry/
router/agent_id）全 False**。P2-① live = 0 occurrences。探针数据
已删（bus runs=0）。
```

## Regression

```text
web 全量    **221 passed + 2 skipped**（219→+2：consumerView+1、
            consumerDom+1）· tsc **clean**
backend     K.1 套件 5/5 · test_human_on_loop 25/25（见下）
全量电池    **干净负载复跑：771 passed + 2 skipped（零失败）**
            （=28.J 766 + K.1 5）。首跑曾 770+1 failed
            （test_human_on_loop t18 parallel_safe_barrier_pause）——
            **判定为并发负载 flake**：该跑与 live LLM 规划探针同时
            执行（CPU 争用敏感的 barrier 时序测试）；t18 单跑 0.4s
            通过、整文件 25/25 通过、无并发负载的全量复跑零失败；
            与本改动无语义关联（HOTL barrier 域，消息文案不触其路径）。
既有断言    §20/§44（"质量校验"在模板中）· §34/§35（错误/步限模板
            未动）——兼容 ✓
```

## Pilot State（hotfix 后）

```text
实例        :8123（修复后代码，LIVE·strict 预检过）· :5273 前端未动
            （vite HMR 代理同一后端；映射层修复已由测试锁定的同码
            提供——前端为源码目录服务，无需重启）
REAL_USER   = 0（窗口开启、无真用户进入——hotfix 期间保持）
ROUTER_AUTHORITY = full（pilot 临时·D-07 deferred·代码默认 slices
            未动）· WeKnora/Governance/Ownership 全不变
凭据        8 受邀 key 原样未分发（tmp/pilot-keys/）
```

## Acceptance

```text
P2-① internal stage leakage = 0（单测+DOM+live 三层证明）
P0 = 0 · P1 = 0（无新增；本轮无 unsafe delivery/cross-user/fake
artifact/wrong routing 事件——hotfix 未触碰任何相关路径，且
backend/web 全量绿）
unsafe delivery = 0 · cross-user exposure = 0 · fake artifact = 0 ·
wrong routing = 0（不变——零触碰+全量回归）
```

## Git Scope（本阶段）

```text
M runtime/agent/agent.py（+7/−3：needs_review 消息模板）
M web/src/state/consumerView.ts（needs_review 映射层副本）
M web/src/state/consumerView.test.ts · web/src/components/chat/
  consumerDom.test.tsx（测试）
A tests/runtime/test_k1_needs_review_copy.py（5）· 本报告
零触碰：intent/router/grounding/weknora/workflow 语义/artifact/
auth/ownership/governance/event 词汇/citation/prompts
```

## FINAL

```text
不自动分发 key · 不扩大用户 · 不动 P2-②③④ · 不动 citation/retrieval/
embedding/CJK/Full Authority。等待 Owner：8 keys distribution →
REAL_USER observation。
```
