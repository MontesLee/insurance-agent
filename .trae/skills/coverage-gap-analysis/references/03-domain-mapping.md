# 03 · 风险域 → 保障域 → 目标覆盖方向

`risk-analysis` 的 `risk_category`（R1–R5）是**风险分类**，不是产品分类。
本层将其映射到保障域，并给出策略级覆盖方向（`target_coverage.direction`，**不含具体产品/公司名**）。

| risk_category | 保障域 (domain) | 标签 | 目标覆盖方向（策略级） |
|---|---|---|---|
| R1 | medical | 医疗 | 补充百万医疗险，覆盖社保外大额医疗支出与免赔额缺口 |
| R2 | critical_illness | 重大疾病 | 配置重疾险，保额覆盖 3-5 年家庭年收入 |
| R3 | accident | 意外 | 配置综合意外险（含意外医疗与伤残给付） |
| R4 | life | 寿险/家庭责任 | 建立定期寿险，保额覆盖家庭责任（房贷+子女教育+赡养），期限覆盖责任期 |
| R5 | savings | 储蓄/长期财务 | 建立长期储蓄/年金规划，覆盖退休与子女教育刚性支出 |

映射与方向均外置于 `resources/config/coverage-mapping.rules.json`，便于在不改动引擎逻辑的前提下调整。

## 关联需求
`requirement_analysis.requirements[].requirement_type`（medical / critical_illness / accident / life / savings）
与保障域一一对应，用于填充 `related_requirement_ids`。

## 需求无对应风险
若某 `requirement_type` 在 `RiskAssessment.risks` 中无对应风险域，则**不**生成保障缺口，
而是记入 `information_gaps`（提示需补充该域的风险评估），避免凭空造缺口。
