# Phase 28.K.18 — Batch-1 Real-User UX Observation After K.17

Date: 2026-09-27 · READ-ONLY（零改动·零重启·零 synthetic·零指导）。

## 1. Status

```text
COMPLETE（新样本 1 条已分析；K.17 未被触发——该样本走 QA 快拒路径）
```

## 2. New Real Runs

```text
new_real_user_runs = 1（run_24562be1d8734159·consumer:pilot-user-01）
```

### Run 记录

```text
用户问题："我的百万医疗险和重疾险有什么区别？"（自然·概念比较题）
intent=insurance_qa（路由正确——概念区别问题）
→ QA 切片 → WeKnora 治理检索 allowed=0/denied=0（语料未命中）
→ 生成未尝试（attempts=0·fail-closed 于证据层）
→ 5.0s → QA_REFUSED："知识库暂无可靠依据…换个说法再问"
terminal=completed/QA_REFUSED · artifact=none（正确——拒答不产报告）
duration 5.0s（07:16:21.439→07:16:26.476Z）
```

## 3. K.17

```text
delta-active runs = 0（该样本无生成阶段——证据层快拒，无 LLM 调用）
heartbeat-only runs = 0（全程 5s<12s 阈值——正确地未显示心跳）
terminal cleanup = ✓（completed 即清）
activity mismatches = 0
K.17 触发情况：本样本自然条件下未进入生成路径——**尚未获得真实
delta 活性的正面样本**（不制造·继续等待自然长回答轮）
K.17 服务端可观测性=无（delta 为 transient 不持久——K.17 信号仅
存在于前端运行时；本审计只能以"是否存在生成阶段"间接推断）
```

## 4. UX

```text
用户视角（重建）：提问→5 秒内得到明确拒答+改问建议——快速诚实，
无"卡住"窗口。无重复提交/刷新/放弃的服务端证据（单轮新会话）。
用户在首条规划咨询（12:05）后约 3 小时发起第二条 QA（15:16）——
持续使用信号。
```

## 5. QA

```text
QA generation path 出现=是（但为证据层快拒——未达生成）。
Known limitation — QA generation path has no delta：本样本未触及
生成阶段，无法观察；维持已知限制记录（不修）。
```

## 6. G-1

```text
observation count = 2（真实用户自然请求）：
  ①儿童重疾配置考虑 → 0 hit → 改写 → 0 hit → 通用思路（K.12 首条）
  ②医疗险 vs 重疾险区别 → 0 hit → 5s 拒答（本条）
模式：主流概念型问题在治理语料上未命中——证据从 1 例增至 2 例，
倾向"稳定产品问题"，但仍未达 Owner 专项治理门槛（继续累计；
矩阵更新入观察台账）。
```

## 7. F2

```text
Agent-loop coverage：本样本无 agent-loop LLM 调用（QA 快拒·零
生成）——本轮无新增证据；缺口沿袭 P3 / Observability Debt。
（QA 路径本身经网关——本样本生成未尝试，无 llm.call 属正确。）
```

## 8. Safety

```text
hallucination=0（无事实交付·拒答诚实）· grounding bypass=0（证据
层 fail-closed 正确）· cross-user=0 · internal leakage=0（消费者
文案仅自然语言）· wrong routing=0（insurance_qa 判定正确）
```

## 9. Severity

```text
P0=0 · P1=0 · P2=0 · P3=沿袭（G-1[+1 例累计至 2]·F2 agent-loop·
K.17 无正面样本[观察项]）
```

## 10. Recommendation

```text
CONTINUE BATCH-1（第二条样本一切安全计数为零；G-1 证据增至 2 例
但治理决策属 Owner；K.17 正面验证仍需自然长回答轮）
```
