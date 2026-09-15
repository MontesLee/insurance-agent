> 🌐 **Language:** 🇺🇸 [English](ADR-005-evidence-provenance.md) · 🇨🇳 中文

# ADR-005 · Evidence provenance

## Context
Agent 很容易「凭模型记忆」说出保险知识（例如某产品保证续保 20 年），听起来合理但可能完全错误。
在保险场景，无来源的结论等同于误导。

## Decision
知识必须以 **Evidence** 形式进入系统，且每条证据携带 `evidence_id / document_name / chunk / source`。
- 共享 Evidence Provider（当前位于 `knowledge/evidence/` + `knowledge/rag/`），查询由 `(domain, purpose)` 模板生成，回环只读；
- **V0.2 属性级 grounding**：产品声明的关键属性（`coverage_type / eligibility_age / renewal_period / deductible / coverage_term`）逐条对照证据，给出 `SUPPORTED / UNSUPPORTED / CONFLICT / NOT_CHECKABLE`；
- **NOT_CHECKABLE 是独立第三态**，绝不折成 SUPPORTED；
- 产品候选必须来自 Catalog，推荐必须能溯源到证据。

## Alternatives
- 直接用模型知识回答：不可验证，等于放行幻觉。
- 仅 document 级溯源（Step 2 现状）：只能证明「查过这个领域的文档」，不能证明「这条属性被支持过」。
- 要求证据覆盖整个产品体系：工作量为 O(属性 × 产品)，本阶段不现实。

## Why
「有出处」把可说性变成可核查性。属性级 grounding 进一步回答最要命的问题：
「我们声称这个产品保证续保 20 年，哪条证据说了这句话？」——如果没有任何 chunk 提到，就是 UNSUPPORTED。

## Trade-offs
- 属性级匹配用「声明值的可搜索变体」（含金额单位归一，如 `10000元` vs `1 万元`），本质仍是**字符串命中**，不是语义蕴含 —— 会漏判（假阴性），故设计为「不确定时判 NOT_CHECKABLE / UNSUPPORTED，不判 SUPPORTED」。
- V0.2 只覆盖 5 个关键属性，其余属性不参与判定。
