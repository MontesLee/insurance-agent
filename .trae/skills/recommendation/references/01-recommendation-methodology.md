# 01 — Recommendation Methodology

## 这个 Skill 是什么

`recommendation` 是**决策支持层（decision-support）**，不是销售话术生成器，也不是承保决定。

它站在流水线：

```
FACT → REQUIREMENT → RISK → GAP → SOLUTION → PRODUCT
                              │
                              ▼
                    Recommendation（本 Skill）
```

它**消费**前置 Skill 已经产生的结构化结果，对候选方案做适配性分析与推荐决策：

```
已知客户需求 (requirement-analysis)
+ 已知风险分析 (risk-analysis)
+ 已知候选方案 (candidate_solutions)
+ Knowledge Search 返回的证据 (knowledge_search_results)
        ↓
   Recommendation
        ↓
   比较候选方案 → 判断适配程度 → 解释推荐原因 → 识别 trade-off
   → 识别证据不足 → 输出结构化推荐结论
```

## 它不做的事（边界，越界即失败）

- 不重新进行客户访谈 / 不重建客户画像
- 不重新做 Risk Analysis
- 不自行修改客户需求
- 不自行发明保险产品 / 不凭模型记忆创造产品条款
- 不把未验证信息当成事实
- 不直接执行购买 / 不代表保险公司做最终承保决定
- 不把"推荐"伪装成"确定性结论"

> Recommendation 是 **decision-support，不是 underwriting**。

## 核心工程原则（与 Lawgent 对齐）

1. **Skill 是 Task Contract，不是巨型 Prompt**——所有方法论下沉到 `references/`，所有约束下沉到 `schemas/`，所有判定下沉到 `scripts/`。
2. **确定性优先**：评分/分级/适配判定由 `recommendation.rules.json` 驱动，引擎只读不算，零 LLM 依赖，可离线回归。
3. **Evidence-backed**：任何重要推荐结论都尽量追溯到 Requirement / Risk / Knowledge 三路 provenance；缺证据必须 `insufficient_evidence`，绝不编造。
4. **硬约束优先于软偏好**：预算/期限/流动性等 hard constraint 违反 → 该候选原则上不能进 primary，除非显式 `exception` + `human_review_required=true`。
5. **可解释 > 黑盒分数**：最终推荐必须能回答"为什么推荐 / 为什么不推荐其他 / 依据是什么 / 代价是什么 / 不确定性是什么 / 是否需人工确认"。

## 输入 → 输出

- 输入：`requirement_analysis` + `risk_analysis` + `candidate_solutions` + `knowledge_search_results` + 可选 `constraints`
- 输出：`status` / `decision_context` / `candidate_evaluations[]` / `primary_recommendation` / `alternatives[]` / `not_recommended[]` / `tradeoffs[]` / `uncertainties[]` / `evidence_refs[]` / `human_review_required`

详见 `schemas/recommendation-output.schema.json` 与 `scripts/recommendation_engine.py`。
