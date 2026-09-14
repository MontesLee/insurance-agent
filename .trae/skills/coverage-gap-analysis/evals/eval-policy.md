# CoverageGapAnalysis — Eval Policy（Skill 04）

## 原则
- **可机检才判 PASS**；`MANUAL` / `NOT_EXECUTED` 不计通过。
- **单一真源**：所有用例与断言在 `evals/cases/manifest.json`，运行器（`scripts/run_coverage_gap_dataset.py`）与契约校验都读它。
- **确定性优先**：判定逻辑在 `coverage_gap_engine.py` + `resources/config/coverage-mapping.rules.json`，无随机性、无 LLM 调用。

## 数据集（5 case）
| case | intent | 关键断言 |
|---|---|---|
| case-01-basic | 混合覆盖 | COMPLETE；≥4 缺口；含 CRITICAL/HIGH/MEDIUM；不含 UNKNOWN；life 充分被跳过 |
| case-02-partial | 全部部分覆盖 | COMPLETE；≥5 缺口；含 HIGH/MEDIUM/LOW；不含 CRITICAL/UNKNOWN |
| case-03-no-coverage | 全部无覆盖 | COMPLETE；≥5 缺口；含 CRITICAL/HIGH/MEDIUM |
| case-04-unknown | 身故保障未知 | NEED_MORE_INFORMATION；含 UNKNOWN+CRITICAL；information_gaps 非空 |
| case-05-preliminary | risk 为 PRELIMINARY | PRELIMINARY；≥1 缺口；life 充分被跳过 |

## 契约校验
每个 case 的引擎输出包裹成 Canonical Artifact 后，必须通过
`contracts/coverage-gap-analysis.schema.json`（Draft7Validator）。

## 架构不变量单测（`scripts/test_coverage_gap.py`）
对任意输出强制：
1. 不得含风险层字段（severity / likelihood / residual_risk / risk_priority）→ **Risk ≠ Gap**。
2. 每个 gap 必须 `related_risk_ids` 非空。
3. `confidence ∈ [0,1]`。
4. `SUFFICIENT` 覆盖不得产生缺口。

## 运行
```bash
python scripts/run_coverage_gap_dataset.py   # 数据集 + 契约校验 + 断言
python scripts/test_coverage_gap.py          # 架构不变量
```

## 判定
- 数据集全 PASS 且契约全通过且单测全 PASS → 本 Skill 通过。
- 任一 FAIL → 先查 `rules.json` 映射与 `coverage_gap_engine.py` 状态机，不得靠放宽契约蒙混。
