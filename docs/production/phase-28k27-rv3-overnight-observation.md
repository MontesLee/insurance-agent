# K.27-RV3 Overnight Observation

Date: 2026-09-28（Owner 长时授权·OBSERVATION ONLY·零代码改动）。
Cycles：3（快照/审计 → 10min 轮询+一致性审计 → 8min 终轮+Exit
重算）。

## Status

```text
K.27-RV3 CONTINUES
（原因：No natural user traffic sufficient to establish B/C/F——
  三轮窗口（~30 分钟）零新增真实用户流量·如实·不补造）
```

## Runtime

```text
backend:    :8123 PID 23880 LIVE（startup 2026-09-27T17:02:19Z）
            · K.26(46dbe0f)+K.27-S1 代码（served 断言 direct write
            ABSENT ✓）· controlled_pilot · knowledge=weknora
frontend:   :5273 200 · WeKnora :8080 401-alive · PG :5433 OPEN
REAL_USER:   ON（Batch-1 2 用户·key 有效）
code rev:    46dbe0f + S1 未提交修复（runtime/server.py 1 处）
authority:   full（pilot 临时）
git:         34 tracked-modified + 135 untracked（既有 span 原样·
            每 Cycle 前后核验零意外变化）
```

## Evidence Matrix

| Scenario | Real User | Probe | Status | Evidence |
| -------- | --------: | ----: | ------ | -------- |
| A | 3 | — | **PASS** | 2×诚实拒答+1×通用思路披露（K.27 台账） |
| B | 0 | 0 | **MISSING** | 零真实产品事实样本（探针亦无产品事实专项） |
| C | 0（完整） | 9/9 VALID | **MISSING** | 真实用户两轮止于澄清；探针 R4=完整链但≠真实用户 |
| D | 2 | — | **PASS** | 结构化澄清正确（K.27 台账） |
| E | 4 | — | **PASS** | 含 K.26 后 u02 一家三口轮+RV2 详录 |
| F | 0 | R1/R2 | **MISSING** | K.26 后真实用户唯一轮=5s 快拒（无生成期）——探针 T_first<T_final 已证技术成立但≠F |

## Safety

| Signal      | Count |
| ----------- | ----: |
| Internal ID | 0 |
| CoT         | 0 |
| Reasoning   | 0 |
| Tool        | 0 |
| Skill       | 0 |
| Agent       | 0 |
| Raw Event   | 0 |
| Exception   | 0 |
| Cross-user  | 0 |

（全窗口维持·含 S1 live 验证的 content-only 复扫）

## G-1

```text
cumulative: 3 real-user observations（儿童重疾配置/医疗vs重疾概念/
            一家三口保险——全部 0 hit→诚实拒答/披露）
latest:     obs#3（09-27 14:56Z·K.26 代码）
direction:  完全一致（主流保险问法零命中）
recommendation: 达专项治理启动证据门槛（3 obs 方向一致）——
            语料/分词/嵌入轨道待 Owner 授权（本轮未动检索）
```

## Reliability

```text
GLM:       本轮窗口零调用（零流量）——历史间歇沿袭（YELLOW）
retrieval: WeKnora 401-alive；G-1 3 obs
latency:   无新样本（历史：拒答 5-8s·澄清 39s·生成首 delta 24-34s）
SSE:       无断连证据
artifact:  无新规划（历史探针 9/9 VALID）
terminal events: 全历史恰一（S1 live 复证=1）
```

## Feedback

```text
explicit feedback: 无（通道未接线——FEEDBACK_CHANNEL_NOT_CONNECTED）
repeated query:    历史一例（u02 同题新会话重问→仍澄清·P3 观察项）
re-engagement:     同上
no natural feedback: 本轮窗口零用户活动
```

## New Issues

```text
P0: 无
P1: 无（S1 已修复+live 复证）
P2: G-1 达治理门槛（上述）·B/C/F 样本持续缺失（观察性缺口非缺陷）
P3: 无新增
```

## Exit Decision

```text
K.27-RV3 CONTINUES
——B/C/F 三类真实用户证据仍缺；无 P0/P1；S1 LIVE PASS 维持。
下一步（Owner）：引导两位用户各完成一次①产品事实问答②完整规划
（提供家庭信息走完 8 阶段）③自然长答问题（体验 K.26 流式）——
或直接裁决 Exit 条件豁免/调整。
```
