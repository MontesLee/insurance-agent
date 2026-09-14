# 保险领域包 Playbook（Domain Pack 使用手册）

> 本文件指导「如何使用 `domain/insurance/` 领域包」：从客户情境到险种/证据查询的推理路径、
> evidence_type 与各 Skill 阶段的对应、冲突与时效策略、以及如何扩展本包。
>
> 本 Playbook **不承载业务判断**——只描述领域知识如何被检索与引用。真正的判断在各 Specialist Skill 内。

---

## 1. 领域推理的主链路

保险分析的主链路（见 AGENTS.md §2）是单向的：

```text
FACT → REQUIREMENT → RISK → GAP → SOLUTION → PRODUCT
```

领域包在每一环提供**可被检索的事实证据**，但不替任何环节做决策：

| 阶段 Skill | 需要的领域知识 | 典型 evidence_type | 典型 domain |
|---|---|---|---|
| risk-analysis | 医学定义、既往症认定 | MEDICAL_FACT | health / critical |
| coverage-gap-analysis | 条款约定、保障范围 | POLICY_FACT | 对应险种 |
| solution | 策略适用性事实 | STRATEGY_FACT | 对应险种 |
| product-recommendation | 产品责任/对比 | PRODUCT_FACT / COMPARISON_FACT | 对应险种 |
| report-generation | 汇总引用（不重推理） | 任意（只呈现） | 任意 |

---

## 2. 从客户情境到检索查询

1. 先确定**险种 code**（见 `references/00-product-taxonomy.md`）。
   - 若上游/调用方给的是别名（如 `critical_illness`），先经 `pack.yaml: alias_to_code` 映射为 `critical`。
2. 确定**目的 purpose**（SOLUTION_VALIDATION / PRODUCT_VALIDATION / POLICY_FACT / MEDICAL_FACT / REGULATORY_FACT / COMPARISON / OTHER）。
3. 由 `(domain, purpose)` 经 evidence-request 模板生成查询——**不接受调用方自由文本**，防止注入与幻觉。
4. 检索在 rag 知识库（可由 `seed_rag.py` 从本包 `references/` 生成）上进行；结果按 `product_type` 过滤命中对应险种。

---

## 3. 冲突与时效策略

- **冲突透传**：同一事实在不同来源表述冲突时（如等待期天数不一致），保留双方证据并标记 `conflict=true`，交上层判断，不自动合并。
- **时效优先**：带 `effective_date` 的知识优先于无日期知识；旧版本知识在 pack 升级后由 `version` 标记淘汰，种子库重建时覆盖。
- **来源等级**：S（监管/官方）> A（公司条款）> B（内部通识）> C（第三方）> D（未验证）。检索加权遵循 knowledge-search `ranking.rules.json`。
- **诚实弃权**：检索无足够可靠知识时返回 `insufficient_evidence`，**绝不**用 LLM 自补事实。

---

## 4. 扩展本包（新增险种 / 新事实）

1. 在 `pack.yaml` 的 `product_types` 登记新 code + `alias_to_code`（如需别名）。
2. 在 `references/` 新增 `NN_<name>.md`，文件头保留 domain-pack 标记：
   `<!-- domain-pack: version=1.0 effective_date=YYYY-MM-DD source_level=B code=<code> -->`
3. 若新增证据类型，同步 `evidence_types`。
4. 运行 `scripts/seed_rag.py` 重建生产知识库。
5. 运行 `scripts/validate_pack.py` 全量校验（taxonomy 一致性、版本、可被 rag 摄取、无 overlay 泄漏）。

---

## 5. overlay 引入条件（默认不使用）

按 AGENTS.md §8：**默认不使用 overlay**。仅当确证存在 Context-specific modification——例如某地区监管细则、某客群核保规则、某公司业务规则——才引入：

1. 新建 `overlays/<name>/` 目录；
2. 在 `pack.yaml: overlays.available` 登记，并将 `overlays.enabled` 置为对应范围；
3. overlay = Base（`references/`）+ 增量覆盖，不修改 Base。

当前 `overlays/` 为空，符合默认策略。

---

## 6. 与各 Skill references 的关系

各 Specialist Skill 自己的 `references/NN-*.md` 描述**该 Skill 的方法论与判定规则**（如 risk-taxonomy、gap-judgment-methodology），
而本包的 `references/` 描述**跨 Skill 共享的险种事实知识**。两者职责不同、互不替代：

- Skill references = 怎么做判断（流程/规则/模板）
- Domain Pack references = 判断所依据的事实（知识/定义/条款通识）

Skill references 可**引用**本包的 taxonomy/evidence_types 作为规范，但不应把本包事实再抄一遍。
