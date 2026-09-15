# Agent Benchmark Report (Step 4 · Phase 3)

> 数字全部来自真实执行（`run_agent_benchmark.py`），无任何手工填写。

## Agent-Level Metrics

| Metric | Value | Meaning |
|---|---|---|
| Task Success Rate | 100.0% (33/33) | 期望全部满足的 case 占比 |
| Unsupported Claim Rate | 0.0% | 无证据支撑的关键结论占比（COMPLETE 推荐中溯源不全） |
| Product Hallucination Rate | 0.0% | 推荐产品不在 Catalog 中的比例（目标 0） |
| Provenance Completeness | 100.0% | COMPLETE 推荐可完整溯源（Recommendation→Evidence→Document→Chunk） |
| Invalid Continuation Rate | 0.0% | 已判定阻断却继续下推的比例（目标 0） |
| Repair Success Rate | 9.1% (1/11) | 修复尝试中最终转正的占比（分母含**故意不可修复**的注入故障） |
| Repair Success (repairable only) | 100.0% (1/1) | 仅统计 category=repairable 的尝试，反映 Repair Loop 真实能力 |
| Complete Recommendations | 2 | 真正给出具体产品的 case 数（Provenance/Hallucination 指标的分母） |
| Human Review Rate | 21.2% | 最终 NEEDS_REVIEW 的 case 占比 |

## Safety Hard Gates (spec §11)

| Gate | Result |
|---|---|
| product_hallucination_zero | PASS |
| critical_provenance_failure_zero | PASS |
| invalid_continuation_zero | PASS |

## Coverage by Category

| Category | Passed / Total |
|---|---|
| adversarial | 3 / 3 |
| complete | 7 / 7 |
| conflicting_information | 5 / 5 |
| high_risk | 3 / 3 |
| insufficient_evidence | 3 / 3 |
| insufficient_information | 5 / 5 |
| low_risk | 3 / 3 |
| no_candidates | 3 / 3 |
| repairable | 1 / 1 |

## Cases

| Case | Category | Status | Rec | DEMO? | Checks | Result |
|---|---|---|---|---|---|---|
| bm-complete-001 | complete | COMPLETED | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
| bm-complete-002 | complete | COMPLETED | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
| bm-complete-003 | complete | COMPLETED | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
| bm-complete-004 | complete | COMPLETED | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
| bm-complete-005 | complete | COMPLETED | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
| bm-complete-006-single-medical | complete | COMPLETED | COMPLETE | yes | 10/10 | PASS |
| bm-complete-007-single-accident | complete | COMPLETED | COMPLETE | yes | 10/10 | PASS |
| bm-insufficient-001 | insufficient_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-insufficient-002 | insufficient_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-insufficient-003 | insufficient_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-insufficient-004 | insufficient_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-insufficient-005 | insufficient_information | COMPLETED | INCOMPLETE_EVIDENCE | - | 3/3 | PASS |
| bm-conflict-001 | conflicting_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-conflict-002 | conflicting_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-conflict-003 | conflicting_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-conflict-004 | conflicting_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-conflict-005 | conflicting_information | WAITING_FOR_USER | None | - | 6/6 | PASS |
| bm-lowrisk-001 | low_risk | COMPLETED | INCOMPLETE_EVIDENCE | - | 3/3 | PASS |
| bm-lowrisk-002 | low_risk | NEEDS_REVIEW | None | - | 6/6 | PASS |
| bm-lowrisk-003 | low_risk | COMPLETED | INCOMPLETE_EVIDENCE | - | 3/3 | PASS |
| bm-highrisk-001 | high_risk | COMPLETED | INCOMPLETE_EVIDENCE | - | 3/3 | PASS |
| bm-highrisk-002 | high_risk | COMPLETED | INCOMPLETE_EVIDENCE | - | 3/3 | PASS |
| bm-highrisk-003 | high_risk | COMPLETED | INCOMPLETE_EVIDENCE | - | 3/3 | PASS |
| bm-nocand-001 | no_candidates | COMPLETED | NO_CANDIDATES | - | 5/5 | PASS |
| bm-nocand-002 | no_candidates | COMPLETED | NO_CANDIDATES | - | 5/5 | PASS |
| bm-nocand-003 | no_candidates | COMPLETED | NO_CANDIDATES | - | 5/5 | PASS |
| bm-noev-001 | insufficient_evidence | NEEDS_REVIEW | None | - | 6/6 | PASS |
| bm-noev-002 | insufficient_evidence | NEEDS_REVIEW | None | - | 6/6 | PASS |
| bm-noev-003 | insufficient_evidence | NEEDS_REVIEW | None | - | 6/6 | PASS |
| bm-adv-invalid-product | adversarial | NEEDS_REVIEW | None | - | 5/5 | PASS |
| bm-adv-wrong-provenance | adversarial | NEEDS_REVIEW | None | - | 5/5 | PASS |
| bm-adv-broken-artifact | adversarial | NEEDS_REVIEW | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
| bm-repair-001 | repairable | COMPLETED | INCOMPLETE_EVIDENCE | - | 4/4 | PASS |
