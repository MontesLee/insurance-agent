# Phase 28.K.19 — Batch-1 Exit Evidence Audit

Date: 2026-09-27 · READ-ONLY（零改动·零 synthetic·零重启）。

## 1. Status

```text
COMPLETE（无新增样本——本轮 0 new REAL_USER runs；全量证据复核完毕）
```

## 2. REAL_USER Sample Summary

```text
REAL_USER run 总数 = 2（全部 pilot-user-01；pilot-user-02 = 0）
completed=2 · failed=0 · waiting=0 · needs_review=0
refused/fail-closed=1（QA_REFUSED）· artifacts=0（两轮均为咨询型）
planning requests=1（规则判 plan·Agent 内部按通用咨询处理）
QA requests=1（insurance_qa 快拒）
long-generation requests=1（首条 64s 轮含 40.1s 生成——早于 K.17）
新增样本：0（vs K.18；最新仍为 run_24562be1·15:16 本地）
```

## 3. P0/P1/P2/P3

```text
P0=0 · P1=0 · P2=0
P3=4（沿袭）：G-1 检索形态债（2 obs）·F2 agent-loop 可观测缺口·
  K.17 正面样本待自然长回答轮·intent 漂移观察（1 obs·良性）
```

## 4. G-1 Retrieval Evidence

| Run | User Query | Intent | Query Rewrite | WeKnora Hits | Final Behavior | Safety | Classification |
| --- | ---------- | ------ | ------------- | -----------: | -------------- | ------ | -------------- |
| run_50389328 | 给孩子配置重疾险前，我应该先考虑什么？ | insurance_plan（规则）→Agent 判 GENERAL_GUIDANCE | Agent 自行重查 ×1 | 0（两次） | 诚实披露"无引用"→通用思路 | 无事实编造 | P3/G-1 obs#1 |
| run_24562be1 | 我的百万医疗险和重疾险有什么区别？ | insurance_qa | 无（证据层快拒） | 0 | 5s 诚实拒答 | 无事实编造 | P3/G-1 obs#2 |

```text
G-1 状态判定：**B — 重复出现，但证据仍不足以定位根因**
依据：2 例均为"主流概念/配置型问题 0 命中"，方向一致；但 (a)样本
仅 2，(b)未做 query→检索词形→向量命中层的系统性比对（需受控复现
=另阶段），(c)两例的查询原文差异大，无法从现有证据区分"语料覆盖
缺口"vs"查询形态/分词敏感"vs"向量阈值"。未达 C（专项治理门槛：
需重复性充分+根因可定位）；远未达 D。
```

## 5. K.17 Real-User Verification

```text
状态：**未验证（真实用户正面样本 = 0）**
- Unit-tested ✓（9 项·236+2 全绿）
- Synthetic-tested ✓（jsdom 等价场景 A/B/C）
- REAL_USER verified ✗（K.17 上线后唯一真实轮为 QA 证据层快拒——
  无生成阶段→无 delta；此前 40.1s 长生成样本早于 K.17 上线）
- delta 计时/计数证据：0（本架构 delta=transient 不持久——正面
  验证只能来自真实长回答轮的前端行为/用户反馈）
- reasoning/raw delta/provider 泄漏：0（既有套件+两轮观察）
```

## 6. F2 Agent-loop Observability

```text
QA Gateway path：llm.call 记录机制在案（K.11 实证）；真实样本因
  快拒未触发生成→无记录（正确）
Agent-loop path：**P3 — Agent-loop observability coverage gap**
  （首条真实轮=agent 环·零 llm.call；沿袭，不修）
```

## 7. Consumer UX Evidence

```text
行为证据（仅服务端可观测事实）：
- 无重复提交/无同问题连发/无刷新风暴证据（每轮单次 POST）
- 持续使用信号：两轮间隔约 3 小时（12:05→15:16）·新会话发起
- 无失败后退出证据（无 third-party 信号；如实：仅两样本）
- 无"卡死"可观测证据（两轮分别 64s[含40s 静默·K.17 前]与 5s）
主观推断：不做（无用户反馈原文）
```

## 8. Safety Evidence

```text
P0=0 · cross-user=0 · hallucination=0 · grounding bypass=0 ·
internal leakage=0 · wrong routing=0（两轮全项复核：K.12 首条
NO_ISSUE+K.18 第二条五零）
```

## 9. Batch-1 Exit Criteria

```text
Safety ✓（全零）· Reliability ✓（无 P1·fail-closed 诚实·两轮终态
正确）· UX ✓（无负面行为证据）·
Knowledge：G-1=B 级（2 obs·重复但根因未定位·未影响安全——拒答/
披露方向均诚实）·
K.17：Unit/Synthetic ✓·REAL_USER ✗（区分明确·未混淆）
样本量：2 runs / 1 user / 0 artifacts / 0 planning 完整链真实样本
——**样本量与覆盖面是当前最大的证据缺口**
```

## 10. Remaining Risks

```text
①样本不足：2 轮/1 用户——Batch-2 判定与 G-1 根因定位均受限
②K.17 无正面真实样本（长回答轮未自然发生）
③pilot-user-02 未使用（半 cohort 零数据）
④G-1 若为语料覆盖缺口，将影响 QA 可用性口碑（拒答率）——但安全
  方向正确
⑤孤儿进程监管形态（harness 内存回收已五次；服务现正常）
```

## 11. Owner Decision（事实选项）

```text
Option A — BATCH-1 EXIT EVIDENCE SUFFICIENT：不成立（K.17 真实
  验证缺失+样本量 2+半 cohort 未用——证据不足以支撑退出结论）
Option B — CONTINUE BATCH-1：与当前证据一致（缺 K.17 长回答正面
  样本·样本量不足·G-1 需更多自然样本；可选：Owner 提醒 pilot-
  user-02 开始使用——非本审计动作）
Option C — PAUSE FOR P1：不适用（P1=0）
审计结论：证据状态=B（继续自然观察最符合证据现状；一切退出安全
判据已满足，缺的是"充分性"而非"安全性"）
```

## 12. STOP

```text
零代码/配置/知识库/WeKnora/embedding/Agent/EventBus/K.17 修改·
零 synthetic·零重启·零 key 分发
```
