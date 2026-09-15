# ADR-004 · Deterministic eval

## Context
Skill 产出的 artifact 是否「可信」，需要一个判据。
最省事的做法是让产出方自己声明 `"status": "ok"`，或者让另一个 LLM 打分。

## Decision
Eval 是**独立于 Skill 的确定性引擎**（`workflow/eval_engine.py`），执行 6 类机器可判的检查：
`schema / required_fields / required_non_empty / contamination / provenance / cross_artifact / invariant`。
规则外置在 `workflow/resources/config/eval.rules.json`，可用 `-RulesPath` 做负向注入。
**无法评估的检查一律记 FAIL，绝不记 MANUAL/UNKNOWN 通过。**

## Alternatives
- Skill 自评：等于让被检查方自己批卷，不可信。
- LLM-as-judge：对高风险场景不稳定、不可复现、且会掩盖确定性问题。
- 只做 schema 校验：抓不到「结论引用了不存在的 evidence」这类语义错误。

## Why
「保险 Agent 是高风险决策场景」，判据必须**可复现、可回归、可反证**。
确定性 Eval 使「修改后是否真的变好了」变成可对比的问题（Before/After），而不是直觉。

## Trade-offs
- 确定性检查覆盖不了「语气是否推销」「表述是否易懂」等主观维度（当前有意不做）。
- 规则外置增加一层间接，且规则本身可能写错 —— 用负向探针（篡改规则副本）反向验证。
- 严格性会导致「宁可 FAIL 也不及格」：某些本该人工判断的场景会被判 FAIL → 进 `NEEDS_REVIEW`，牺牲自动化率换正确性。
