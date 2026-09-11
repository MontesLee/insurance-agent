# Requirement Analysis Eval

> 状态：Phase 5 Implemented
> 目标：为 `requirement_analysis` 建立独立于主分析逻辑的 Eval 层。

---

## 1. Eval 目标

Eval 的职责不是重新做需求分析，而是检查：

1. 分析结果是否完整
2. 重要结论是否有证据支撑
3. 逻辑是否前后一致
4. 信息不足时是否越界输出确定结论
5. 是否泄漏到产品推荐层

---

## 2. 当前实现范围

当前 Phase 5 实现：

- Deterministic Eval
- 结构化 Eval Output
- Issue taxonomy
- 造错测试

当前 Phase 5 未实现：

- 稳定可复现的 LLM-based Eval 运行时

原因：

当前项目的主执行形态是 `Markdown + JSON + PowerShell`，尚无稳定、可回归、可离线复现的 LLM Eval 调度层。

因此本阶段采用：

1. 先把 deterministic eval 做实
2. 把 LLM Eval 作为未来可插拔层，而不是现在硬塞一个不稳定组件

---

## 3. 五类 Eval

### 3.1 Completeness

检查：

- 当前可分析 scope 是否遗漏 `risk_map`
- `requirements / coverage_gaps / priorities` 是否与 scope 结果相匹配

失败 issue：

- `MISSING_RISK`

### 3.2 Evidence Grounding

检查：

- `risk_map.evidence_refs` 是否存在
- evidence id 是否真实存在
- evidence 是否引用事实上游字段
- requirement / priority 是否能追溯到 evidence

失败 issue：

- `UNSUPPORTED_CONCLUSION`

### 3.3 Logical Consistency

检查：

- `risk_map.priority` 与 `requirements.priority` 是否一致
- `coverage_gaps.priority` 与 requirement 是否一致
- `analysis_status` 与输出内容是否矛盾

失败 issue：

- `LOGICAL_INCONSISTENCY`

### 3.4 Information Sufficiency

检查：

- 当 `analysis_status = NEED_MORE_INFORMATION / CONFLICTING_INFORMATION` 时，是否仍然输出正式 requirement
- `information_sufficiency.sufficiency_status` 与分析结果是否冲突

失败 issue：

- `INSUFFICIENT_INFORMATION`

### 3.5 Requirement / Product Separation

检查：

- 是否出现产品推荐、保险公司、购买建议等越界内容

失败 issue：

- `PRODUCT_RECOMMENDATION_LEAK`

---

## 4. Issue Types

当前至少支持：

- `MISSING_RISK`
- `UNSUPPORTED_CONCLUSION`
- `LOGICAL_INCONSISTENCY`
- `INSUFFICIENT_INFORMATION`
- `PRODUCT_RECOMMENDATION_LEAK`
- `INVALID_OUTPUT`

---

## 5. Eval Output

结构化输出示例：

```json
{
  "eval_status": "PASS",
  "score": 92,
  "checks": {
    "completeness": 95,
    "evidence_grounding": 90,
    "logical_consistency": 95,
    "information_sufficiency": 100,
    "requirement_product_separation": 100
  },
  "issues": [],
  "repair_required": false
}
```

失败示例：

```json
{
  "eval_status": "FAIL",
  "score": 71,
  "checks": {
    "completeness": 90,
    "evidence_grounding": 60,
    "logical_consistency": 80,
    "information_sufficiency": 100,
    "requirement_product_separation": 100
  },
  "issues": [
    {
      "type": "UNSUPPORTED_CONCLUSION",
      "location": "risk_map[0]",
      "reason": "Risk entry missing valid evidence refs",
      "evidence": "risk_map[0].evidence_refs = []"
    }
  ],
  "repair_required": true
}
```

---

## 6. 运行脚本

- `scripts/invoke-requirement-analysis-eval.ps1`
- `scripts/test-requirement-analysis-eval.ps1`
