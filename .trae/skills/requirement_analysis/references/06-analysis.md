# 06 — 需求分析（Analysis）

> 来源：原 ANALYSIS.md。
> 本文件定义在信息足够或可做初步分析时，如何输出结构化的风险映射、保障缺口、需求优先级和证据链。

---

## 1. 链路

`Sufficient Information` → `Risk Mapping` → `Financial Impact` → `Existing Protection` → `Coverage Gap` → `Requirement Priority` → `Evidence`。

## 2. 分析前提

### 2.1 可进入分析的状态

- `COMPLETE`
- `PRELIMINARY`

### 2.2 不直接进入正式分析的状态

- `NEED_MORE_INFORMATION`
- `CONFLICTING_INFORMATION`
- `FAILED`

当输入仍处于明显信息不足或冲突状态时，只允许输出空分析结果或保留下一步动作，**不得伪造完整需求结论**。

## 3. 五类分析对象

当前支持：`medical` / `critical_illness` / `accident` / `life` / `savings`。每类都输出：`risk_exposure` / `potential_financial_impact` / `existing_protection` / `coverage_gap` / `priority` / `reasoning` / `evidence_refs`。

## 4. 风险映射原则

### 4.1 必须从事实出发

风险判断必须由可追溯事实支持（收入、房贷、子女、家庭责任、健康情况、已有保障、资产/支出/现金流）。

### 4.2 不允许过度推理

- “收入高”不能直接推出“风险承受能力低”
- “已婚”不能自动推出“寿险需求极高”
- “健康有异常”不能自动推出“一定买不到保障”

## 5. Financial Impact

`potential_financial_impact` 不是精算值，而是需求分析层面的结构化判断（收入中断对家庭现金流的影响、大病治疗和康复阶段的支出压力、意外事故造成的职业收入损失、储蓄目标受现金流与负债约束的影响）。若缺少关键数值，必须显式写出 `UNKNOWN` 或“信息不足以精确判断”。

## 6. Existing Protection

`existing_protection` 只根据当前已知事实写。若没有明确提供，必须写 `UNKNOWN`，**不能默认客户“没有保障”**。

## 7. Coverage Gap

Coverage Gap 不能只写“客户需要某类保险”，必须表达：当前风险是什么 / 风险可能造成什么财务影响 / 当前已知保障是什么 / 缺口在哪里 / 优先级为什么是当前级别。

## 8. Requirement Priority

优先级必须真实区分：`P0_CRITICAL` / `P1_HIGH` / `P2_MEDIUM` / `P3_LOW`。主要根据：风险暴露是否明显、家庭责任是否集中、财务影响是否显著、当前已有保障是否明显不足或未知、当前信息是否仍存在关键不确定性。

## 9. Evidence Grounding

每个重要结论都必须有对应 `evidence`（`fact_refs` / `value_status` / `reasoning` / `conclusion`）。没有证据支持的结论，不得进入 `risk_map` / `coverage_gaps` / `requirements` / `priorities`。

## 10. Unknown Handling

遇到以下情况时必须保留 `UNKNOWN` 或不确定性：没有明确事实 / 只有估计值 / 只有假设 / 已有冲突但未解决。分析引擎不能为了让答案看起来完整而补猜。

## 11. Product Boundary

Phase 4 仍严格停留在 Requirement 层：可以输出哪类需求存在、风险级别、缺口方向、优先级；**不能输出**具体产品、保险公司、比较方案、销售话术。
