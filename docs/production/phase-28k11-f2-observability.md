# Phase 28.K.11-F2 — Gateway Call Log Observability

Date: 2026-09-27 · 性质：**observability-only**（纯观测层——重试/超时/
业务结果分支字节级不变；零 commit·未启动 pilot·未分发 key·孤儿未触碰）。

## 1. Current Observability Gap（审计修正）

```text
K.9/K.10 的"call_log=unavailable"表述不准确（勘误）：
  · 能力大部分已存在——gateway._log（元数据 call_log）+ _observe →
    obs.log("llm.call") → JsonlLogger → tmp/obs/agent.jsonl（追加式
    JSONL·构造脱敏·Phase 25B 既有机制）
  · 真实缺口=字段退化：错误以【字符串】传入 → obs.errors 分类投影
    不触发（error_class/retryable 全空）；失败尝试无时长（duration
    仅取自 response.latency）；无 request_id/purpose/timeout 旗标
  · 实证：tmp/obs/agent.jsonl 中 02:49-02:53（K.9.1/K.10 失败窗口）
    记录存在但 err=None/dur=None——归因瓶颈的确切机制
```

## 2. Existing Mechanisms Audited（不重复建设）

```text
runtime/obs/log.py JsonlLogger（字段契约+PII denylist+凭据形值脱敏）
runtime/obs/errors.py 分类表（LLMError 族→error_code/error_class/
  retryable/safe_to_retry/operator_action/user_visible）
gateway._log/_observe（单一观测咽喉——每终局与每重试恰过一次）
LLMRequest.request_id/correlation_id/metadata.purpose（复用）
持久化=tmp/obs/agent.jsonl（既有·gitignored·无需新增基础设施）
```

## 3. Call-log Contract（实施后每条 llm.call）

```text
timestamp · level · event=llm.call · status(OK/RETRY/FAIL/EXHAUSTED)
request_id · correlation_id · purpose（如 qa-answer）· provider · model
attempt(0 基) · max_attempts · duration_ms（含失败尝试的墙钟时长）
timeout 旗标（错误类含 Timeout）· error{error_code/error_class/
retryable[类级]/safe_to_retry/operator_action/user_visible/message
[脱敏截断]} · tokens
注：error 块 retryable=taxonomy 类级视角；实例级重试【决策】由
status 表达（FAIL=不重试·RETRY=重试·EXHAUSTED=预算耗尽）——两者
并存已由 T5 语义锁定。
```

## 4. Persistence Mechanism

复用 tmp/obs/agent.jsonl（多进程追加；观测到 1 条历史交错损坏行
——低风险记录于 §11）。未新增任何基础设施。

## 5. Security / Privacy Analysis

```text
仅元数据+计时+状态+分类+关联 id；无 prompt/response/messages/
authorization/api_key（sink denylist 构造强制+值级凭据形脱敏）；
T6 以注入密钥/提示词/响应的错误对象实测零泄漏。
```

## 6. Error Classification / 7. Retry Visibility

```text
分类：经 obs.errors（LLM-RATELIMIT/LLM-TIMEOUT/LLM-GENERIC/
  LLM-UNAVAILABLE…；不可判定=unknown 语义保留）——不猜测
重试：每 attempt 一条记录（att=0,1,2…）+ EXHAUSTED 终局标记；
  重试行为零修改（仅观测）
```

## 8. Tests（tests/runtime/test_k11_f2_observability.py·7/7）

```text
T1 成功记录（request_id/purpose/duration 在）✓
T2 超时分类（timeout=True·error_class·失败时长保留）✓
T3 可重试（att 0,1·RETRY·retryable）✓
T4 持续失败（RETRY×3+EXHAUSTED 全迹·att 0,1,2,2）✓
T5 不可重试（单调用单 FAIL·无假重试；类级 vs 实例级 retryable
   语义注记）✓
T6 零泄漏（注入 SECRET/prompt/response 的错误→记录全无）✓
T7 业务结果不变（同脚本输入同响应/同异常）✓
```

## 9. Regression

```text
backend 全量 **794 passed + 2 skipped（零失败）**（=F1 后 787+7；
含 B4/B6/GOV/M3/M4/HD-2/E-6/B-02/K.7/p25 观测与故障注入套件 48/48）
web/tsc：本阶段零 web 改动——沿用本日新鲜基线（web 221+2·tsc
clean，F1 后复跑，此后 web 无 delta）
```

## 10. Controlled Verification（最小确定性+单次 live）

```text
脚本化：T1-T7（上）——确定性失败注入=既有 Fake/Scripted provider
  机制（未压测真实供应商）
live 单轮 QA（治理路径）：39.6s·citation_gate（业务行为与既往
  一致）→ 新 schema 记录两条：
  OK att=0 dur=11542ms req=llm_req_085c purpose=qa-answer
  OK att=0 dur=23362ms req=llm_req_33ce purpose=qa-answer
并行电池失败记录（新 schema）：RETRY/EXHAUSTED 带
  err=LLM-RATELIMIT/RATE_LIMIT retryable=True + request_id ✓
  ——历史退化字段（err=None/dur=None）已消除，实证成立
```

## 11. Remaining Unknowns

```text
①K.9.1/K.10 历史失败的真实错误类（发生时记录已退化——不可回溯，
  只能等下一次瞬态以新 schema 捕获；02:49 窗口 att 间隔 ~164s 的
  线索提示某尝试超看门狗长——待新记录确证）
②tmp/obs/agent.jsonl 多进程并发追加偶发交错（194K 行见 1 条损坏）
  ——低风险；如需强一致=后续小项
③taxonomy 类级 retryable 与实例旗标并存（语义已注记·T5 锁定）
```

## 12. F3 Recommendation

```text
下一次 llm_unavailable 发生时读取新记录即可回答"发生了什么"（错误
类/每次尝试时长/超时旗标/退避是否触发）。若显示 LLM-TIMEOUT 且
单尝试时长>90s→F3 供应商长生成问题；若 LLM-RATELIMIT→配额/并发；
若 LLM-GENERIC 且 message 含供应商错误→按文处理。在此之前 F3
无需行动。
```

## 13. Batch-1 Status

```text
不改变 K.10 判定：Provider=YELLOW·Batch-1=OWNER_DECISION（A 接受
/B 本 F2 已就绪——瞬态可归因后快速裁决 / C 90s 保留或回退）。
```

```text
Phase 28.K.11-F2 Status: COMPLETE
Observability: PASS · Secret Leakage: 0 · Behavioral Regression: 0
Safety: PASS · S-1: PASS · S-2: PASS
Provider: YELLOW · Batch-1: OWNER_DECISION（沿用 K.10）
REAL_USER: 0 · Keys Distributed: 0 · Pilot Runtime: NOT STARTED
Code Changes: 2（runtime/llm/gateway.py[纯观测层]·新增
tests/runtime/test_k11_f2_observability.py）
Commit: NONE
```
