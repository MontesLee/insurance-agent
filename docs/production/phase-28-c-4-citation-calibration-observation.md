# Phase 28.C-4 · Citation Calibration Observation

Date: 2026-09-28 · OBSERVATION-ONLY（零 gate/prompt/模型/runtime 改动·
gate 包装仅存在于探针进程内·生产文件零触碰）。

## Status

**28.C-4 OBSERVATION_COMPLETE**（5 问真实生成·2 attempts/问·197 个违规句
全量分类·分布足以支撑决策候选）。

## 1. Current Gate Contract

`grounding/gate.py`：`split_sentences`（。！？；\n 切分）→ 每句
`is_fact_sentence`（含任一 fact_marker 即事实句）→ 须句内含
`\[E\d+\]` 且 label ∈ evidence_map。违例词表 4 类·上限 10 条/次。
max_regenerations=1（首试+重生成）→ 仍有违例即 citation_gate_rejected
拒答（ADR-022 fail-closed）。

## 2. Fact Marker Inventory

**marker_count=38**：A 明确事实词 **32**（保额/保费/等待期/犹豫期/
免赔额/免责/赔付/理赔/报销/费率/续保/健康告知/核保/现金价值/社保/
医保/重疾/意外/年金/寿险/身故/全残/医院/保单/生效…）；
B 泛化词 **6**（保险/条款/投保/保障/医疗/疾病）。
citation_required_when=句含任一 marker；citation_valid_when=句内
[E#]∈evidence_map。

## 3. Violation Taxonomy（实测·tmp/obs/c4_violations.json）

V1 真事实句无引用 | V2 泛/结构句误触 | V3 引用存在但提取失败 |
V4 证据在但未引 | V5 证据本身不足 | V6 其他。

## 4. Observed Distribution（197 违规句·glm-5.3-flash）

```text
结构性/过渡句被 marker 命中 = 125 (63%)   ← 标题/加粗/引导/元叙述
纯泛词-only 误触（原 C-0 假设主因）= 6 (3%)
散文事实句无引用 = 72 (37%)               ← 多为超出检索块覆盖的
                                            正确常识（V4/V5 混合）
V3 真提取失败 = 0（4 条假阳性=模型元文本提及"[E#]"→归 V6）
通过句（正确引用）= 63 —— 模型引用能力本身成立
```

关键样本：`# 百万医疗险的免赔额…解读`（标题被判事实句）·
`## 一、免赔额` · `**说明**：本次未提供任何受管证据…`（模型自述元文本
也被判）· `我无法：为保险事实句添加合法引用`（模型拒绝伪造引用）。

## 5. Generic Marker Analysis

**原假设不成立为主因**：纯泛词（保险/医疗类）误触仅 3%；但"结构句
携带具体 marker"（标题含"免赔额"）占 63%——问题不在词表宽，在
**句子切分把 markdown 结构当散文事实句**。

## 6. Prompt Analysis

PROMPT_SUPPORT: **PARTIAL**——prompt（config qa-grounding-rules v3）
明确要求事实句 [E#] 且仅用给定证据（63 个通过句证明纪律已建立）；
但**未约束答案形态**——模型自由输出长文 markdown（标题/分节/元说明），
结构句全部落入 marker 判定域。

## 7. Model Evidence

MODEL_EFFECT: **NOT_ESTABLISHED**（本观测全为 glm-5.3-flash·
K.31-A flashx n=2 同签名——样本不足，不做模型优劣判断）。

## 8. Retrieval / Evidence Analysis

5 问中 2 问 ev≤1（免赔额题 ev=1·区别题 ev=0）——模型在证据极薄时仍写
长文（参数化常识），诚实拒绝伪造引用→大面积违规。**证据深度与答案
形态系统性失配**（与 28.C-3 语料缺口直接耦合）。探针注意：直调
generate_grounded 跳过了生产 insufficient_evidence 预拒守卫（ev=0 问
在生产会 4.3s 预拒）——该问样本仅用于形态分析，非生产行为。

## 9. Fail-Closed Integrity

**PRESERVED**（零修改；拒答语义/门判定/retry 原样；探针包装委托原
check·结果逐字节一致）。

## 10. Decision Candidates

**MULTI_FACTOR**，按实测权重排序：
1. **答案形态约束**（结构句豁免 or prompt 禁 markdown 结构/元叙述）
   ——覆盖 63% 违规 → DECISION_CANDIDATE: answer-shape calibration
2. **证据深度**（28.C-3 语料解封直接消解 V5 耦合）——覆盖 37% 中的
   大部 → DECISION_CANDIDATE: KB/retrieval（已在 28.C-3 runbook）
3. **marker 泛词收窄**——实测仅 3% 收益 → 低优先（C-0 权重被证伪）

## 11. Required Decisions

①结构句是否豁免引用要求（=gate 语义变更·ADR-022 裁决）或以 prompt
约束答案形态（=prompt 变更）——二选一或组合，Owner 裁决
②28.C-3 JWT 解封（先行·与②叠加效应最大）③QA 模型档位对比实验
（flashx 纪律·样本设计 n≥10·独立阶段）

## 12. Deferred Changes

gate/markers/prompt/模型/retry/检索——全部未动，待裁决。

## 13. Tests

test_k22_qa_streaming 6 passed（门行为回归锚）·探针 5 问实跑
（tools/qa_citation_violation_probe.py·可重复）。

## 14. Evidence

tmp/obs/c4_violations.json（197 句全量·marker/引用/分类字段）·
本报告分布表·K.28/K.31-A/K.34 历史同签名拒答。
