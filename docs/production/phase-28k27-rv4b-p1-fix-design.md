# K.27-RV4-B · P1 Fix Design Audit（Planning Continuation + Evidence Qualification）

Date: 2026-09-28 · DESIGN ONLY（零代码/零重启/零数据修改）。

## 1. Executive Summary

两个 P1 属**独立 failure domain**（意图层/证据层），可分别实施与回滚。
FIRST DEVIATION=意图层无规划延续（补充消息落入 qa 产品名词规则）；
SECOND SAFETY BOUNDARY FAILURE=证据层两级缺失（retrieved→E1 无相关性
下限 + 门只验引用存在性）。最小修复=Phase1 双独立小改：①确定性延续
规则（conversation 域·不需 ADR-024）②QA 证据相关性资格下限（复用
既有 insufficient_evidence 拒答路径）。claim-support 与 user-fact 语义
=Phase2/Deferred（需 ADR-022 附裁决）。

## 2-3. Root Cause Confirmation（RV4-A 证据复用+本轮补证）

P1-A：classifier 规则链（classifier.py:150-260）plan 需动作词、qa
产品名词即中 conf=1.0；`active_case_id=None` **调用点写死**
（server.py:636 注释 "no persistent cases yet (ADR-024 blocked)"）——
非 schema 缺失、非未传，是 ADR-024 阻塞下的显式置空。
P1-B：①qa_agent:95 query=原文→build_evidence→治理（R1-R9=**纯元数据
资格**：registry/authority/window/hash——**无主题相关性层·MISSING**）
→items 即 E#（qa_agent:133-137）②gate.check（gate.py:82）=引用
**存在性**（marker 句内 [E#]∈evidence_map），无 claim-support——
**Citation Presence Gate ≠ Grounding Gate（代码实证）**。
Retry：attempts=2；attempt1 违规明细未持久化[UNKNOWN]；终稿 15×[E1]
（含用户自述+建议）=**仅提高引用覆盖即过门，无任何资格复核**。

## 4. Architecture Boundary

**Q1 独立可分修 ✓**：A 在 intent 层（classifier+server 输入）；
B 在 evidence 组装层（qa_agent）与门语义（Phase2）。回滚互不影响。
**Q2 无 Planning→QA 旁路 ✓**：规划环 knowledge-search 工具
（tools.py:325）→同一 KnowledgeService→**canonical evidence 工件**
（空结果 fail-closed），不经 generate_grounded/引用门——P1-B 的
"grounded+无关 E1"签名为 QA 路径特有；规划残留风险=检索质量喂分析
（弱形态·非本 P1）。**Q3 是**——证据修复不解决意图：本次会话仍会
错误进 insurance_qa（链路证据）。

## 5. Current Evidence Pipeline（逐层）

| 层 | 实现 | 判断条件 | 失败行为 |
|---|---|---|---|
| Query | qa_agent:95 | 原文 strip | — |
| Retrieval | weknora.py search | vector top_k | ProviderError→kb_unavailable |
| 治理资格 | governance R1-R9 | 元数据（registry/authority/时间窗/hash） | 拒命中（K002） |
| **主题相关性** | — | — | **MISSING** |
| Evidence 组装 | qa_agent:129-137 | 治理后 items→E# | 0 项→insufficient_evidence |
| Generation | loop.py attempts≤2 | — | llm_unavailable |
| 门 | gate.py:82 | marker 句引用存在性 | 违例→重生成→仍违例拒 |
| **claim-support** | — | — | **MISSING** |

E1 语义=「第 1 个治理后检索命中」（enumerate 赋号）同时充当检索秩+
引用锚+grounding 基础——**contract ambiguity（三义一号）**。

## 6. Minimal Safe Fix

**P1-A（Phase 1）·确定性延续规则（Option A）**
- 修改：`classifier.py`（新增规则 4.5·置于 qa 规则前）+
  `server.py`（classify 调用传入 `pending_clarification`：同 chat 上一
  run 终态 WAITING_USER + 其 intent=insurance_plan——server 已有
  run/chats 状态可查）+ `config/intent-rules.yaml`（延续信号外置）。
- 信号：pending_clarification 存在 ∧ 当前消息**无**新意图信号
  （无 plan 动作词/无问句标记/无产品评价词）→ insurance_plan
  continuation·conf=1.0·reason=[rule:plan_continue:pending_clarification]。
- topic-switch：显式问句/定义词/产品评价词→正常走原规则链（QA 等）；
  歧义（混合）→clarification_required=True（fail-closed 问用户）。
- 不修改：Router/Registry/agent/gateway/SSE/K.26/K.27-S1。
- 需 ADR：**ADR-019 附裁决**（continuation 语义冻结）。
- 需 Case：**否**（conversation 域 pending 标志即够；ADR-024 全生命
  周期=Deferred——Phase1 不依赖）。
- Rollback：撤 classifier 规则+server 参数（两文件·行为即回现状）。
- Option B（LLM 候选）=Deferred 增强（机制在库·INSURANCE_AGENT_INTENT_LLM
  关闭·候选仍过 schema+resolver）；Option C（ADR-024）=Deferred。

**P1-B（Phase 1）·证据相关性资格下限**
- 修改：`qa_agent/agent.py`（evidence 组装处：items→**QualifiedEvidence**
  过滤——查询↔证据主题兼容性下限，如领域词项重叠/嵌入相似；
  **阈值=OWNER DECISION REQUIRED**）+ `config/qa-grounding-rules.yaml`
  （阈值外置）。全落选→复用**既有** insufficient_evidence 诚实拒答
  （零新拒答路径）。
- 不修改：gate.py（Phase1 不动门）/grounding/loop.py（重试语义不变）/
  WeKnora/planning/治理 R1-R9。
- Evidence Contract（设计冻结·实施属 Phase1）：**RetrievedEvidence≠
  QualifiedEvidence**——治理通过=可溯源资格；主题兼容=可用资格；
  仅 Qualified 进 evidence_refs。
- Grounding Contract（Phase2 目标冻结）：citation presence≠support；
  user-provided fact 免引用（fact-source 分类：user_fact/insurance_fact/
  product_fact/advice——本例"配偶35岁[E1]"强贴即此缺陷）。
- Rollback：撤过滤（阈值关=现状直通）。

**Phase 划分**：Phase1=A 规则+B 资格下限（互相独立可单独上线）；
Phase2=门 claim-support 抽查/引用密度异常告警（影子先行）+user-fact
免引用+prompt 事实源标注；Deferred=ADR-024 case 生命周期·LLM 意图
候选·attempt1 违规明细持久化。

## 7. File-level Scope

P1-A：runtime/intent/classifier.py·runtime/server.py·
config/intent-rules.yaml·tests/runtime/test_agent_intent.py（+
shadow.py 记录字段含 pending 标志）。
P1-B：runtime/qa_agent/agent.py·config/qa-grounding-rules.yaml·
tests/runtime/test_k22_qa_streaming.py 或新 qa 资格测试。
**NOT**：gate.py·grounding/loop.py·router.py·agent_registry.py·
planning_agent·tools.py·weknora.py·web/*·schema/（Phase1 零 schema
变更）·K.26/K.27-S1 相关文件。

## 8. Test DoD（MUST PASS·未运行）

Planning：延续正例（RV4 真实 Turn2）·延续负例（新独立 QA 问句）·
topic-switch（规划中插"重疾险是什么"→QA·不混淆）·歧义追问
（clarify）·多轮上下文（≥3 轮）。
Evidence：无关检索（农业条例×规划补充→NO qualifying→拒答）·相关
检索→qualified·user-fact 不强贴 E1·unsupported claim 拒·citation-only
attack（塞 [E#] 无支持→Phase1 不拦·Phase2 必须）·retry attack
（重生成仍不合格→拒）。
Regression：K.26 流式（T_first<T_final 不回归）·K.27-S1 单写卫生·
既有 QA 测试（test_k22 等）·既有 Planning（test_agent_loop）·
intent 既有 golden cases·安全九零（internal ID/CoT/…）。

## 9. ADR Decision

不新建 ADR；两处**附裁决**：①ADR-019 附录=conversation continuation
语义（pending-clarification 延续·topic-switch 边界·歧义 fail-closed）
②ADR-022 附录=RetrievedEvidence≠QualifiedEvidence + citation
presence≠claim support + user-fact 免引用（衔接 28.C-5 命题语义线）。

## 10. Rollback Plan

A：撤两文件改动→无 pending 参数→规则链回现状（QA 关键词命中）。
B：阈值配置置 0/删过滤→items 直通（现状）。均不涉及数据迁移/
服务架构；重启即生效、再重启即回滚。

## 11. Deferred Work

ADR-024 case 全生命周期·LLM 意图候选启用评估·attempt1 违规明细
持久化（gate 观测增强）·claim-support NLI/LLM 判定影子·引用密度
异常告警·query 构造（延续场景的检索 query 重写）。

## 12. Owner Decisions Required

①P1-B 相关性下限**阈值与判定法**（词项重叠 vs 嵌入相似——建议
先词项重叠·零新依赖）②两 ADR 附裁决文案批准③Phase1 上线顺序
（建议 A 先·B 次日·各自独立观察）④RV4 真实会话回归验证授权
（Owner 复测同两轮消息）。
