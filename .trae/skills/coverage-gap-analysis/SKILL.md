---
name: coverage-gap-analysis
id: coverage-gap-analysis
version: "1.0"
type: analysis
layer: coverage_gap
status: active
---

# Coverage Gap Analysis（保障缺口分析）

## 一句话定位
回答 **"针对已识别的风险与已声明的需求，客户当前保障覆盖到什么程度（缺口在哪）？"**
它是独立的**业务判断层**，不是 Risk Analysis 的字段拆解。

## 上游 / 下游
- **输入（Canonical Artifact）**：`ClientProfile` + `RequirementAnalysis` + `RiskAssessment`
- **输出（Canonical Artifact）**：`CoverageGapAnalysis`（契约见 `contracts/coverage-gap-analysis.schema.json`）
- **下游消费者**：`solution`（解决策略）、`product-recommendation`（产品）、`report-generation`（汇总）

## 何时调用
在 `risk-analysis` 产出 `RiskAssessment` 之后、`solution` 之前调用。数据链单向：
`FACT → REQUIREMENT → RISK → GAP → SOLUTION → PRODUCT`。

## 核心边界（硬约束）
1. **Risk ≠ Coverage Gap**：本 Skill **不重算** severity / likelihood / residual_risk / priority，
   只通过 `related_risk_ids` 引用风险。`risk-analysis.coverage_assessment` 是风险层辅助判断，
   **最终缺口结论由本 Skill 负责**。
2. **不推荐产品、不制定策略**：只产出 `current_coverage.status` + `target_coverage.direction`，
   具体产品/保险公司名由 `product-recommendation` 负责。
3. **不改上游**：只读 `client_profile / requirement_analysis / risk_assessment`，绝不回写。
4. **SUFFICIENT 不产生缺口**：已充分覆盖的风险直接跳过。
5. **不创造事实**：覆盖判定只能基于上游 `coverage_assessment` 或 `existing_protection` 文本，
   信息不足时 `status=UNKNOWN` 并记入 `information_gaps`，不得臆测。

## 判定逻辑（确定性）
`resources/config/coverage-mapping.rules.json` 外置：
- `coverage_assessment`（protected/unprotected 金额）为主信号；否则关键词扫描 `existing_protection`。
- `current_coverage.status` ∈ {NONE, PARTIAL, SUFFICIENT, UNKNOWN}。
- `gap_level` 由 `gap_level_matrix[priority][status]` 映射（SUFFICIENT 跳过；UNKNOWN→UNKNOWN）。

## 运行方式
```bash
python scripts/invoke-coverage-gap-analysis.py --input <composite.json> [--output <artifact.json>]
python scripts/run_coverage_gap_dataset.py     # 5 case 数据集
python scripts/test_coverage_gap.py            # 架构不变量单测
```

## 评估
- 数据集：`evals/cases/manifest.json`（5 case，单一真源）
- `status=COMPLETE` 需所有覆盖已知且 risk 为 FORMAL；出现 UNKNOWN 缺口 → `NEED_MORE_INFORMATION`。
- 单测用「禁止属性存在」断言强制 Risk≠Gap。

## 参考
- `references/01-gap-judgment-methodology.md`
- `references/02-coverage-status-logic.md`
- `references/03-domain-mapping.md`
- `CONTRACT.md`
