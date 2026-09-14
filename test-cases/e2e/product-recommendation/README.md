# Step 2 E2E — Product Recommendation

```text
Solution → Evidence → Candidate → Recommendation
```

## 执行策略（规格 §二十一）

**真实执行**（不是 fixture 回放）：

1. `evidence.request.from_solution()` —— 由 Solution 真实构造 Evidence Request
2. `evidence.provider.provide_evidence()` —— 真实检索（`domain/insurance/references` 语料）
3. `product_candidate_engine.run()` —— 真实 Catalog 筛选
4. `invoke-product-recommendation.run()` —— 真实推荐引擎

**允许 fixture**：`RequirementAnalysis` / `RiskAssessment` / `CoverageGapAnalysis` /
`SolutionPlan` 上游产物（受执行环境限制，且其自身已有各自 eval 保障）。

## 运行

```bash
python test-cases/e2e/product-recommendation/run_product_recommendation_e2e.py
# 换语料：STEP2_KB_DIR=<path> python ...
```

`manifest.json` 是**单一真源**：案例清单 + 期望断言都写在里面。

## 案例

| 案例 | 场景 | 期望 |
|---|---|---|
| `case-001-happy-path` | 30 岁 / 寿险缺口 / 定期寿险策略 | `COMPLETE`，主推 **P007**；P008 因方向不符被拒 |
| `case-002-no-evidence` | 候选存在但无对应领域证据 | `INCOMPLETE_EVIDENCE`，无主推 |
| `case-003-no-candidate` | Catalog 无对应险种 | `NO_CANDIDATES` + `next_information_needed` |
| `case-004-ineligible-product` | 85 岁客户，超出全部医疗险年龄 | 全部 `product_ineligible`，无主推 |

## 断言覆盖（规格 §二十三）

- evidence provenance（`document_id` / `chunk_id` / `provenance[]` 可解析）
- candidate validity（全部来自 Catalog、全部 `is_demo`）
- eligibility（不可准入者绝不主推）
- coverage match（方向不符者被拒）
- no hallucinated products（候选 ⊆ Catalog）
- no unsupported recommendation（无证据不产出主推）
- recommendation provenance（Recommendation→Product→Candidate→Solution→Gap→Evidence）

## 防假通过机制

runner 会校验 manifest 的期望键**全部被实现**：

```python
unknown = set(exp) - RECOGNIZED_EXPECT_KEYS - {"id"}
```

出现无法识别的键直接 FAIL。
（早期版本曾因传错 `expect` 层级导致 8 类断言静默不执行，这是针对该缺陷的守卫。）
