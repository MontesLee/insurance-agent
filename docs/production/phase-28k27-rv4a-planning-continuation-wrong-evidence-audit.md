# K.27-RV4-A Audit · Planning Continuation + Wrong-Evidence

Date: 2026-09-28 · AUDIT ONLY / NO CODE CHANGE · 真实会话
`chat_02a2693e2e9d42c4`（内部 ID·不进 Consumer 面）。

## 1. Executive Summary

第二轮用户补充信息被 rules-only 意图层按**消息内产品名词**判为
`insurance_qa`（无规划延续机制），QA 切片以**补充消息原文**为检索
query，WeKnora 仅回 1 个治理命中=《农业保险条例》→ 被升级为 E1 →
模型第二次尝试以 **15×[E1] 引用塞满**（含用户自述事实与一般建议）
通过"引用存在性"门 → `grounding_status=grounded` 交付。

## 2. Real Conversation（脱敏复述）

Turn1 07:20:34Z run_c7487dc42a3246ad：家庭保障缺口请求（40岁/孩子5/
重疾200万/年收入30万/房贷/预算2万/担忧收入中断+大病）。
Turn2 07:23:56Z run_df99313701674835：逐条回答追问（200万重疾=本人/
夫妻有百万医疗/孩子无险/房贷余100万/配偶35岁100万重疾/收入主要靠本人）。

## 3. Execution Trace（intent-shadow + run 目录实证）

```text
Turn1: msg → intent=insurance_plan(conf1.0 rule·plan动作词+家庭/孩子ctx)
       → router registry_lookup → insurance-planning-agent
       → legacy ask_user（5 问）✓ Terminal WAITING_USER
Turn2: msg（纯补充·无规划动作词）→ 规则序 1-4 全不中
       （plan 规则强制动作词；modify 需改动词；product/unknown 不符）
       → 规则5 qa signals 命中[重疾险,医疗险] → insurance_qa conf=1.0
       → router registry_lookup → insurance-qa-agent
       → authority=full → knowledge-qa 切片 FIRED
       → query=补充消息原文（qa_agent:95 无 query 构造）
       → WeKnora vector_search top8 → 治理后命中仅 1：《农业保险条例》=E1
       → generate_grounded attempts=2（首试门败→重生成）
       → 15×[E1] 塞满版过门 → grounded → QA_ANSWERED 交付
```

## 4-6. Intent / Context / Router Evidence

Turn1：`insurance_plan·conf1.0·rule·[rule:plan:保障,plan_ctx:家庭,
plan_ctx:孩子]`·agent=planning ✓
Turn2：`insurance_qa·conf1.0·rule·[rule:qa:重疾险,rule:qa:医疗险]`·
agent=qa·slice=knowledge-qa(fired,authority)
Context：server 传 `_recent`（含 Turn1 规划追问）——**已接线但规则
引擎未使用**；`active_case_id=None`（调用点写死 None·ADR-024 阻塞）
→ 分类器签名有该参数却无规划延续分支（仅 modify 用它设 clarify）。
Router：registry_lookup·deterministic ✓（ADR-020 合规——按 intent
选对表，错在 intent）。

## 7. Actual Agent

insurance-qa-agent（qa_answered 事件+qa-answer-context.json 在案）；
无 Planning→QA 内部旁路（规划 agent 未参与 Turn2）。

## 8-9. Retrieval / Wrong Evidence

query=原文；命中：E1=《农业保险条例》(2012) 法律责任条款（rank 1 of 1
治理后命中）。成因：补充消息作为知识 query 语义错位（本非知识问题）
+ 语料向量相似质量（G-1 族）。

## 10. Grounding Analysis

门只验证「句含 marker→句内有 [E#]∈evidence_map」（gate.py:82）——
**无 claim-evidence 支持性/相关性检查**。Attempt2 策略=每句附 E1
（含"配偶35岁[E1]"等用户自述、"定期寿险…[E1]"等一般建议）→ 形式
合规 → grounded。模型自身多次声明证据不相关（"本批证据中无相关规则
依据"）——**模型知道，系统不知道**。

## 11. Root Cause

**I — Multiple Root Causes**（按偏离顺序）：
- **A 意图延续缺陷（首个偏离点）**：无"补充=延续规划"语义；产品名词
  即 qa conf=1.0。违反 ADR-019 精神（context 已传未用·active case 空）。
- **F 证据资格缺陷**：retrieved→evidence 无相关性下限；无关法规升级 E1。
- **G 门范围缺陷**：citation presence ≠ 支持；塞引用即过。

C/D/E 非根因：Router 确定性正确；无 agent 旁路；检索按 query 如实返回。

## 12. Severity

**P1**：不相关法规被系统标记为 authoritative evidence
（grounding_status=grounded + 交付真实用户的建议句携带法规引用
[E1]）——满足 §21 P1 判据；缓解因素（模型内联免责"非证据结论·仅供
参考"）降低但不消除消费者误读风险。安全扫描：内部 ID 泄漏 0·CoT 0·
跨用户 0 ✓（E1 为消费者安全引用标签）。

## 13. Recommended Next Owner Decision（不实施）

1. 意图延续：补充消息的 plan-continuation 规则/LLM 候选启用评估
   （ADR-019 补裁决）或 ADR-024 case 生命周期解锁排期。
2. 证据资格：retrieved→evidence 间最小相关性下限（属 28.C 线）。
3. 门范围：claim-support 抽查或"仅 1 证据且引用密度异常"启发告警
   （ADR-022 附裁决·先影子）。

## 14-15. Code Changes / Tests

**NONE / NO CODE TEST CHANGES**（数据源：tmp/intent-shadow/shadow.jsonl
两条目标记录·tmp/webui-runs/run_df99313701674835/qa-answer-context.json·
run-profiles·classifier.py:150-260·intent-rules.yaml）。
