# Phase 28.K.12 — Batch-1 Real User Pilot（窗口开启报告）

Date: 2026-09-27 · 性质：**Controlled Real-User Observation**（零代码
改动·零 commit·未扩大 cohort）。本报告=运行就绪+窗口开启+首段观察
（零流量如实）；真实用户观察将在 Owner 物理分发两把 key 且用户使用后
持续进行。

## 1. Cohort

```text
Batch-1 = 2 名受邀用户（pilot-user-01/02·独立 identity/key/ownership/
不共享凭据与会话）。REGISTRY.md 已标 Batch-1 distributed-ready；
其余 6 把（03..08）保持 UNDISTRIBUTED（Batch-2/3 仅 Owner 可授权）。
分发说明：tmp/pilot-keys/HANDOFF-batch1-final.md（Owner 物理分发；
本会话零打印 raw key）。观察规则遵守：不指导用户测试内容/不预告
易失败问题——用户自然使用。
```

## 2. Preconditions（逐项核对）

```text
Safety=PASS（K.8 五零+K.11 复核）· S-1=PASS（K.8 live A-D）·
S-2=PASS（K.8 9 VALID+34.6KB 交付）· Negative=PASS（fail-closed
契约套件锁定）· F2 Observability=PASS（K.11 live 实证）·
Provider=YELLOW（如实——已知风险：QA 突发窗口偶见诚实"稍后再试"；
非 GREEN）。
关键部署动作：观察依赖 F2 记录，而原孤儿 :8123/:5273 跑 K.7 前码
（无 F1/F2）→ 已停止（PID 27356/16460）并以**当前代码（K.7+F1+F2）**
重启：backend PID 5840（startup 2026-09-27T03:34:43Z·strict 预检过）
·frontend :5273（PID 略）·env=runbook 原样（controlled_pilot·
WeKnora·pilot full 临时）。REAL_USER 语义=本实例受邀 key 流量
（subject 前缀 pilot-user-01/02）。
```

## 3-9. User Journey / Request / Routing / Workflow / Grounding /
Artifact / Latency / Provider

```text
首段观察（~15 分钟轮询×3）：bus=0·无新 run 目录·无新 llm.call
——REAL_USER 流量=0（如实：key 待 Owner 物理分发，不冒充）。
上述各维度将在用户进入后按观察字段记录（timestamp·user_subject·
request_id·intent·workflow status·latency·error class·retry·
artifact outcome·needs_review）；治理边界=现有 Data Governance+
F2 记录（request_id/correlation_id/purpose/duration/timeout/
error_code/error_class/retryable/attempt/status）；禁记字段维持
（key/Authorization/凭据/不必要 PII/完整 prompt/response）。
```

## 10. F2 Call-Log Evidence（就绪态）

新实例 llm.call 记录已带完整契约（K.11 实证）；若出现
llm_unavailable：先保存证据→按 timeout/rate_limit/connection/
provider_exception/unknown 分类（不立即重启·不现场修）。

## 11-12. Safety / P0-P1-P2

当前全零（无流量）。Incident 规则装载：P0→立即暂停 Batch-1；
P1→暂停新增用户；P2→仅记录。No-Code Rule 全程遵守。

## 13. User Friction

待用户样本。

## 14. Recommended Next Step

```text
Owner：①向两位受邀用户物理分发 key（HANDOFF-batch1-final.md）
②用户自然使用 ③观察窗口期间（或结束后）回到会话读取台账
（F2 记录/run 目录/治理审计/metrics）出 Batch-1 观察报告。
```

## 15. Batch-2 Gate（预置判据）

```text
Batch-1 完成后检查：P0=0·P1=0·cross-user=0·hallucination=0·
grounding bypass=0·internal leakage=0 + 两用户完成核心任务情况 +
Provider failure/重复 needs_review/artifact 生成/用户理解度/
人工介入需求。满足且 Owner 单独授权 → Batch-2（3 用户）。
```

```text
Phase 28.K.12 Status: COMPLETE（运行就绪+窗口开启；观察段待
真实用户进入——不冒充样本）

Users Invited: 2（staged·key 待 Owner 物理分发）
Users Active: 0 · Users Completed: 0

P0: 0 · P1: 0 · P2: 0（无流量）
Cross-user Exposure: 0 · Hallucination: 0 · Grounding Bypass: 0 ·
Internal Leakage: 0

Provider Failures: 0 · llm_unavailable: 0 · Needs Review: 0 ·
Artifacts Delivered: 0（窗口内无流量——如实）

Batch-2: OWNER_DECISION（判据预置；待 Batch-1 数据）

Code Changes: NONE · Commit: NONE
（部署动作：pilot 重启至当前代码——运行时操作非代码改动）
REAL_USER: 0（待分发后用户进入）· Pilot: :8123 PID 5840 + :5273
LIVE（当前代码）· 监管：harness 任务 bq1vdxuop/brah35bgc
```
