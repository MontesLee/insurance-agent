# Phase 28.K.9.1 — Final Provider Stability Window

Date: 2026-09-27 · 性质：**VERIFICATION ONLY**（零改动·零 commit·未
启动 pilot·未触碰孤儿·未分发 key·无业务状态创建[QA 探针经 run_qa_turn
纯函数路径：检索+生成+引用门，无 chat/run/artifact]）。问题描述遵
勘误：**供应商间歇性长请求失败 / llm_unavailable**（非"429 问题"；
确认 HTTP 429=0）。

## 1. Objective / 2. Test Window

```text
窗口：2026-09-27 本地 ~02:4x-03:0x（13 个有效受控请求，顺序执行，
     无并发；连续 2 硬失败即止[未触发]）
call_log = unavailable（网关内部重试/错误类未持久化——全程如实）
```

## 3-4. Request Matrix & Raw Summary（tmp/k91-window.json 全量）

```text
A-short×6（主模型小请求）：全部 normal · 2.0/2.2/2.2/2.4/2.4/3.8s
B-qa×3（治理 QA 代表路径·已传 provider）：
  1) citation_gate 49.6s（ret=1·attempts=2·生成完成被引用门诚实拒）
  2) insufficient_evidence 4.3s（ret=0·语料缺口·快拒·非供应商）
  3) llm_unavailable 177.3s（ret=1·attempts=2·P3——窗口内失败复现）
C-long×3（~4K 上下文代表生成·同 prompt）：全部 normal ·
  30.6s / 34.8s / 56.2s
探针缺陷披露：B 首轮 2 例 internal_error 为探针未传 provider（契约
拒绝），已剔除并正确重跑——非供应商证据。
```

## 5-6. Latency / Error Distribution

```text
延迟：短请求 2.0-3.8s（中位 2.3）·长生成 30.6/34.8/56.2s（同
prompt 方差 ±25s·最大值=60s QA 预算的 94%）·QA 全链正常路径
49.6s·失败路径 177.3s（含重试消耗）
错误：P3 llm_unavailable ×1（1/13 总·1/3 QA 类）·P1 provider HTTP
=0·P2 应用超时直接观测=0（表现于 P3 内部成因）·P4=0·P5=0
```

## 7-9. Provider Error / Timeout / llm_unavailable Evidence

```text
provider HTTP error：无（0 例；响应均 200 类——错误以延迟/挂起形态
  出现而非状态码）
timeout 证据（间接）：C#1 56.2s→预算 94%；B#3 177.3s ≈ 2×generate
  attempts ×（≤3×60s 看门狗）部分耗尽——与 K.9 法证签名一致
llm_unavailable 证据：B#3（P3）——生成层耗尽后诚实"暂不可用"文案
  （ans_len=40 拒答体）；网关内部重试次数/退避是否触发=UNKNOWN
  （call_log=unavailable）
```

## 10. Comparison with K.9 Historical Failures

```text
同签名复现：177.3s ∈ 历史 125-216s 聚类；成因画像不变=QA 长生成
（证据块+引用要求）延迟 23-56s 高方差 vs 60s 看门狗→部分轮耗尽。
K.8 子集 3/8 → 本窗口 1/3 QA 类——发生率随窗口波动但模式稳定。
规划链/长上下文本身持续健康（C 3/3·K.8 双链成功）。
```

## 11. Stability Classification：**YELLOW**

```text
非 GREEN：窗口内出现 1 次 llm_unavailable（复现历史模式）+长生成
  贴近预算（56.2s/60s）
非 RED：孤立单发（13 中 1）·无连续失败·A/C 全稳·无持续不可用·
  无 provider HTTP 错误模式
判定：YELLOW（孤立失败+其余稳定+失败类型=已知超时族）
```

## 12. Batch-1 Gate

```text
Safety=PASS · S-1=PASS · S-2=PASS · Negative=PASS（K.8/K.9 沿用，
零改动）
Provider stability=YELLOW → **Batch-1 = OWNER_DECISION**
```

## 13. Remaining Risks

```text
①QA 类轮 llm_unavailable 率：观测窗口 1/3~3/8 波动——真人体验为
  诚实"稍后再试"死路（无假成功·无安全问题）
②长生成延迟方差（同 prompt 30-56s）→ 60s 预算余量随答案长度恶化
③根因精确分层（超时 vs 瞬态错误占比）受限于 call_log 未持久化
④语料缺口（accident/savings + 部分问法）仍产生快拒答（非供应商）
```

## 14. Follow-up Items（FOLLOW-UP——本阶段未动）

```text
F1 QA timeout_s / 生成长度校准（config/qa-grounding-rules.yaml·
   需授权+基线同步[B6 三段纪律]）
F2 网关 call_log 持久化（可观测性）
F3 供应商套餐/配额核实（administrative）
F4 D-04 引用合规轨道（本窗口 citation_gate 1 例再现）
```

## 15. Owner Decision

```text
证据型判断（供裁决）：失败模式已充分定性——系统性预算/延迟失配
（QA 长生成 vs 60s 看门狗），不会自愈；影响面=QA 类轮的诚实死路
（≈12-40% 按窗口）；规划链健康；安全零风险。
选项 A：接受该风险 → 授权 Batch-1 分发（用户将偶见"稍后再试"）。
选项 B：先授权 F1（timeout/生成长度校准·小配置变更+B6 基线同步）
   → 复验窗口 → 再裁决。
选项 C：择时再开一个验证窗口（供应商负载时段差异假设）。
```

```text
Phase 28.K.9.1 Status: COMPLETE
Provider Stability: YELLOW
Safety: PASS · S-1: PASS · S-2: PASS · Negative Evidence: PASS
Batch-1: OWNER_DECISION
REAL_USER: 0 · Keys Distributed: 0 · Pilot Runtime: NOT STARTED
（孤儿未触碰）· Code Changes: NONE · Commit: NONE
```
