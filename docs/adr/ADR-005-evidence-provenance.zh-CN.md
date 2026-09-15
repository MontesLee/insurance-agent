> 🌐 **Language:** 🇺🇸 [English](ADR-005-evidence-provenance.md) · 🇨🇳 中文

<a id="adr-005-evidence-provenance"></a>
# ADR-005 · 证据溯源

<a id="context"></a>
## 背景

智能体很容易抛出“来自模型记忆”的保险知识（例如“该产品保证续保 20 年”）——听起来有理，却可能出错。在保险领域，一个无出处（unsourced）的结论，等同于误导客户。

<a id="decision"></a>
## 决策

知识必须以**证据（Evidence）**的形式进入系统，每条证据携带
`evidence_id / document_name / chunk / source`。
- 一个共享的证据提供者（Evidence Provider）（当前位于 `knowledge/evidence/` + `knowledge/rag/`）；查询由 `(domain, purpose)` 模板生成，且该回路只读；
- **V0.2 属性级溯源（attribute-level grounding）**：关键的声称产品属性（`coverage_type / eligibility_age / renewal_period / deductible / coverage_term`）逐条与证据核对，得出 `SUPPORTED / UNSUPPORTED / CONFLICT / NOT_CHECKABLE`；
- **NOT_CHECKABLE 是一个显式的第三态**，绝不并入 SUPPORTED；
- 候选产品必须来自产品目录（Catalog）；推荐必须可追溯到证据。

<a id="alternatives"></a>
## 备选方案

- 直接基于模型知识作答：不可验证——相当于给幻觉发许可证。
- 仅做文档级溯源（即 Step 2 的现状）：只能证明“参考了本领域的某份文档”，而非“该属性被支持”。
- 要求证据覆盖整个产品体系：O(attributes × products) 的工作量——现阶段不现实。

<a id="why"></a>
## 理由

“有出处”把“可说”变成“可查”。属性级溯源回答那个最致命的问题：“我们声称该产品保证续保 20 年——是哪条证据说了这句话？”如果没有任何片段提及，即为 UNSUPPORTED。

<a id="trade-offs"></a>
## 取舍

- 属性匹配使用的是“声称值的可检索变体”（含金额-单位归一化，例如 `10000元` 与 `1 万元`）；它仍是**字符串命中（string hit）**，而非语义蕴含（semantic entailment）——存在漏检（假阴性，false negatives），因此设计规定“不确定时判为 NOT_CHECKABLE / UNSUPPORTED，绝不判为 SUPPORTED”。
- V0.2 仅覆盖 5 个关键属性；其他属性不参与判定。
