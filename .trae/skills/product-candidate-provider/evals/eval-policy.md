# Eval Policy — product-candidate-provider

Eval 唯一真源。只有**可机检断言**判 PASS；`MANUAL` / `NOT_EXECUTED` **不计通过**（AGENTS.md §6）。

## 运行方式

```bash
# 单元 / 不变量 / 负向（19 项）
python .trae/skills/product-candidate-provider/scripts/test_product_candidate_provider.py

# Catalog 结构与 demo 标记
python .trae/skills/product-candidate-provider/scripts/invoke-product-candidate-provider.py --validate-catalog

# Step 2 E2E（61 项，含 Evidence 与 Recommendation）
python test-cases/e2e/product-recommendation/run_product_recommendation_e2e.py
```

日志落 `evals/cases/_candidate_unit_log.txt`。

## 断言清单

### A. Step 2 负向测试（规格 §二十）

| # | 场景 | 断言 |
|---|---|---|
| 1 | `requested_product_ids=["FAKE-001"]` | 不进入 candidates；`rejected` 含 `PRODUCT_NOT_IN_CATALOG` |
| 2 | 客户 85 岁 | 全部候选 `ELIGIBILITY_INELIGIBLE`；`admissible_candidate_ids` 为空 |
| 3 | 寿险策略下的 P008（储蓄/传承方向） | `COVERAGE_DIRECTION_MISMATCH`；`admissible=false`；P007 仍 `MATCH` |
| 4 | `knowledge_evidence.evidence=[]` | 全部候选 `EVIDENCE_MISSING`；无可准入候选 |
| 5 | `lookup_product("不存在的万能险X")` | `NOT_FOUND`（绝不模糊匹配或自动创建） |

### B. 不变量

- 候选 `product_id` ⊆ Catalog
- 所有候选 `is_demo=true`
- `INELIGIBLE` 绝不进入 `admissible_candidate_ids`
- 年龄未知 → `UNKNOWN`（不静默 `ELIGIBLE`）
- 空保障方向 → `UNKNOWN`（不静默 `MATCH`）
- `GENERAL` + 缺口域 `general` → 无产品类型

### C. 反向探针（证明守卫活着）

篡改 `solution_type_to_product_types["MEDICAL"] = ["savings"]` 后，候选集**必须改变**。
若不变，说明引擎没真正读规则文件 —— 该测试必须 FAIL。

> 反橡皮图章纪律：一个不可能失败的测试不是测试。

### D. Catalog 校验

`--validate-catalog` 用 `schemas/product-catalog.schema.json` 校验：12 个产品、
`is_demo` 必须为 `true`、`product_id` 匹配 `^P\d{3}$`、`product_type` 在枚举内。

## Repair 纪律

沿用项目既有机制：`FAIL → Repair → Rerun`，`MAX_REPAIR_ATTEMPTS = 2`，仍失败 → `NEEDS_REVIEW`。

红线：
- 派生量算错 → AUTO 修
- 事实或立场有问题 → REVIEW，不清洗
- 禁止通过修改 baseline 让测试变绿（§二十五）
