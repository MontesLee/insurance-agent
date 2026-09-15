> 🌐 **Language:** 🇺🇸 [English](ADR-004-deterministic-eval.md) · 🇨🇳 中文

<a id="adr-004-deterministic-eval"></a>
# ADR-004 · 确定性评估

<a id="context"></a>
## 背景

一个 Skill 产出的产物是否“可信”，需要一把标尺。最偷懒的做法：让生产者自行声明 `"status": "ok"`，或让另一个 LLM 来打分。

<a id="decision"></a>
## 决策

评估是一个**独立于 Skill 的确定性 Eval Engine（评估引擎）**（`runtime/eval_engine.py`），执行 6 类可由机器判定的检查族：
`schema / required_fields / required_non_empty / contamination / provenance / cross_artifact / invariant`。
规则外置于 `runtime/resources/config/eval.rules.json`，并可通过 `-RulesPath` 进行负向注入。
**任何无法被评估的检查都被记录为 FAIL——绝不以 MANUAL/UNKNOWN 通过。**

<a id="alternatives"></a>
## 备选方案

- Skill 自评：被检查方给自己的答卷打分；不可信。
- LLM-as-judge：在高风险领域中不稳定且不可复现；掩盖确定性问题。
- 仅做 schema 校验：会漏掉语义错误，例如“结论引用了不存在的证据”。

<a id="why"></a>
## 理由

“保险代理是高风险的决策场景”——这把标尺必须**可复现、可回归、可证伪**。确定性评估把“这次改动是否真的改善了结果”变成一个可比较的问题（Before/After），而非凭直觉。

<a id="trade-offs"></a>
## 取舍

- 确定性检查无法覆盖主观维度，例如“语气是否过于推销” / “措辞是否易懂”（目前刻意超出范围）。
- 外置规则增加了一层间接性，且规则本身也可能出错——通过负向探针（被篡改的规则副本）反向验证。
- 严格性带来“宁可 FAIL 也不要通过”：某些本应由人工判定的场景会被判为 FAIL → `NEEDS_REVIEW`，以自动化率为代价换取正确性。
