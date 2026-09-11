# Requirement Analysis Repair Loop

> 状态：Phase 6 Implemented
> 目标：把 `Analysis -> Eval -> Repair -> Re-run` 串成可执行闭环，并限制最大修复次数。

---

## 1. 主链路

正常情况：

1. Analysis
2. Eval
3. PASS
4. Final Output

失败情况：

1. Analysis
2. Eval
3. FAIL
4. Identify Issue
5. Repair
6. Re-run Eval
7. PASS or next retry

---

## 2. MAX_RETRY

当前固定：

- `MAX_RETRY = 2`

若两次 repair 后仍失败：

- `HUMAN_REVIEW_REQUIRED`

---

## 3. Repair 原则

Repair 必须针对 issue type，而不是盲目重跑。

### 3.1 UNSUPPORTED_CONCLUSION

修复方式：

- 重新对齐 `risk_map / coverage_gaps` 到真实 `evidence_id`
- 若缺少 evidence ref，则按 `requirement_type -> evidence conclusion` 重新映射

### 3.2 MISSING_RISK

修复方式：

- 若提供原始 input，则重新运行 analysis，用原始 deterministic output 补回缺失风险段
- 若没有原始 input，则无法安全补造，进入人工复核路径

### 3.3 PRODUCT_RECOMMENDATION_LEAK

修复方式：

- 删除产品/购买/公司等越界表达
- 恢复到 requirement 层表述
- 强制 `boundary = requirement_only`

### 3.4 LOGICAL_INCONSISTENCY

修复方式：

- 同步 `risk_map / coverage_gaps / requirements / priorities` 的 priority
- 保持单一来源一致

### 3.5 INSUFFICIENT_INFORMATION

修复方式：

- 清理不应存在的正式分析输出
- 保留 `question_plan / next_actions`

### 3.6 INVALID_OUTPUT

修复方式：

- 若有原始 input，则重新生成 analysis
- 若无原始 input，则进入人工复核

---

## 4. 输出

Repair Loop 输出：

- `final_status`
- `attempt_count`
- `final_analysis`
- `final_eval`
- `repair_history`

`final_status` 取值：

- `PASS`
- `HUMAN_REVIEW_REQUIRED`

---

## 5. 测试

当前覆盖：

1. `UNSUPPORTED_CONCLUSION -> Repair -> PASS`
2. `MISSING_RISK -> Repair -> PASS`
3. `PRODUCT_RECOMMENDATION_LEAK -> Repair -> PASS`
4. `两次后仍无法修复 -> HUMAN_REVIEW_REQUIRED`
