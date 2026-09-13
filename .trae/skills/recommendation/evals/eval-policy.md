# Recommendation — Eval Policy

Eval 是独立步骤，与 Skill 同步建设（AGENTS.md §6）。所有 case 为**单一真源** `cases/dataset-manifest.json`，
运行器 `scripts/run_recommendation_dataset.py` 与校验器 `scripts/validate_output.py` 都读它。

## 五维 Eval（对齐用户 Prompt §25）

| 维度 | 验证内容 | 代表 case |
|---|---|---|
| **Completeness** | 是否评估所有 candidate、覆盖高优先级需求/重大风险/硬约束/trade-off/uncertainty | normal / partial / risk_gap |
| **Matching** | 明显适配 / 部分适配 / 明显不适配 | partial / requirement_conflict / budget_conflict |
| **Evidence** | 有证据 / 证据不足 / 证据冲突；不得凭记忆补全 | evidence_insufficient / evidence_conflict |
| **Uncertainty** | 信息不足 / 产品信息不足 / 来源冲突 → 显式 uncertainty + human_review | human_review / insufficient_input |
| **Scope** | 不重做需求/风险分析、不生成话术、缺失输入不自行假设 | insufficient_input / no_candidates |

## 验收 case（≥10，单一真源）

1. `normal_recommendation` — 清晰最优解 → primary=A, COMPLETE
2. `partial_match` — 部分需求未覆盖 → primary=A 但 requirement_fit=partial_fit
3. `budget_conflict` — 候选超预算 → 超预算者 not_recommended，另一者 primary
4. `requirement_conflict` — 候选不满足必选需求 → not_recommended
5. `risk_gap` — 推荐方案留下重大风险敞口 → remaining_gaps 非空
6. `evidence_insufficient` — 候选声称的 coverage 无知识库证据 → INCOMPLETE_EVIDENCE + human_review
7. `evidence_conflict` — 知识库标注来源冲突 → INCOMPLETE_EVIDENCE + human_review
8. `close_call` — 两候选接近 → A primary, B alternative
9. `no_candidates` — 无候选 → NO_CANDIDATES + human_review
10. `human_review` — 上游信息不足 → INCOMPLETE_EVIDENCE + human_review
11. `insufficient_input` — 缺失上游输入 → INSUFFICIENT_INPUT + human_review

## 运行

```bash
python scripts/run_recommendation_dataset.py     # 全量回归，期望 ALL GREEN
python scripts/test-recommendation.py            # 单测包装
python scripts/validate_output.py <output.json>  # 单条结构化校验
```

## 纪律

- 可机检断言才判 PASS；自然语言断言记 MANUAL 且不计通过
- 负向自检：构造"候选声称 coverage 但无 source_refs 命中"必须触发 insufficient_evidence；构造"超预算"必须触发 not_recommended
- 不得为让测试通过而修改上游 Skill 或降低校验标准
