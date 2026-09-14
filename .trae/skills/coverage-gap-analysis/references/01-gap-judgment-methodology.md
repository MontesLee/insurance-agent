# 01 · 保障缺口判定方法论（Gap Judgment Methodology）

## 本层回答什么
`coverage-gap-analysis` 只回答一个问题：

> **针对已经识别的风险（RiskAssessment）与已经声明的需求（RequirementAnalysis），
> 客户当前保障覆盖到什么程度？缺口在哪里？**

它**不**回答：
- 这个家庭有哪些风险？（→ `risk-analysis`）
- 应该采用什么解决策略？（→ `solution`）
- 哪些产品可以实现策略？（→ `product-recommendation`）

## 为什么是一个独立层
保障缺口是**独立的业务判断**，不是 Risk 的某个字段拆出来。理由：
1. 风险量化（severity/likelihood/residual/priority）描述的是「发生什么、多大概率、多严重」。
2. 保障缺口描述的是「针对该风险，现有保障接得住多少、还差多少」。
   同一个风险，不同家庭的现有保单不同 → 缺口不同，但风险本身不变。
3. 把缺口判断独立成层后，未来「保单体检 / 家庭保障盘点 / 旧保单分析 / 保障额度计算」
   都可以挂在这一层，而不必回改 `risk-analysis`。

## 输入 → 输出映射
```
ClientProfile (existing_protection 补充证据)
RequirementAnalysis (requirements → related_requirement_ids)
RiskAssessment (risks → 逐条判定)
        │
        ▼
CoverageGapAnalysis
  gaps[]:  domain / subject / related_*_ids / current_coverage / target_coverage / gap_level
  priorities[] / information_gaps[] / status
```

## 不变量（架构纪律）
- **Risk ≠ Gap**：不重算、不复制风险层量化字段。
- 只通过 `related_risk_ids` 引用风险，保证可溯源。
- 信息不足时 `status=UNKNOWN`，记入 `information_gaps`，绝不臆测覆盖程度。

## 判定总览
详见 `02-coverage-status-logic.md`（覆盖状态如何判定）与 `03-domain-mapping.md`
（风险域 → 保障域 → 目标覆盖方向）。
