# Reference 03 — Report Section Rules（8 章节生成规则）

固定 8 章节，顺序与标题不可变更。每章节只读取对应上游字段，逐字复制，不重算。

## 01 客户画像（`client_profile`）
- 遍历 client_state 的 `family_profile` / `employment_profile` / `health_profile` / `responsibility_profile` / `existing_protection`，按 `PROFILE_LABELS`（中文标签映射）逐字段输出。
- `status=UNKNOWN` 或 `value=null` → 值=「待确认」。
- `note`：已知 N 项 / 待确认 M 项；整块缺失 → 缺失说明。

## 02 家庭财务情况（`financial_profile`）
- 仅取 `client_state.financial_profile`，按 `FINANCIAL_LABELS` 输出为表格。
- 缺失字段渲染「待确认」，并录入允许金额集合（供幻觉扫描）。
- 整块缺失 → 缺失说明。

## 03 风险暴露（`risk_exposure` R1–R5）
- 按 `risk_category` 聚合 `risk_analysis.risks`，每类别取优先级最高（rank 最低）的一条。
- 输出：`风险状态(residual_risk)` / `风险描述(trigger+exposure)` / `严重程度` / `主要影响(potential_impact 各值)` / `现有保障` / `保障不足(coverage_assessment.unprotected_amount 或 liquidity_constraint)` / `风险结论` / `来源(risk-analysis.<risk_id>)`。
- 该类别无风险或信息不足 → `present=false` + 说明。

## 04 保障缺口（`coverage_gaps`）
- 来源一：`risk_analysis` 中 `residual_risk∈{HIGH,CRITICAL}` 的风险 → 当前保障 / 主要缺口 / 优先级 / 来源。
- 来源二：`requirement_analysis.coverage_gaps`（按 `requirement_type→risk_category` 映射），避免与来源一重复。
- 均无 → 说明「未识别到明确缺口，金额类缺口需结合补充信息进一步评估（本报告不自行测算保额）」。

## 05 需求优先级（`requirement_priorities`）
- 逐条回显 `requirement_analysis.requirements`，`priority` 经 `requirement_priority_to_short`（P0_CRITICAL→P0）+ `requirement_priority_to_label` 映射。
- 按 `priority_rank` 升序（P0 在前）。

## 06 推荐保障方向（`recommended_directions`）
- **只**回显 Recommendation：`primary_recommendation`（rank=primary）+ `alternatives[]`（rank=alternative）。
- 字段：`candidate_id` / `fit` / `rationale`（reason_codes 映射为中文）/ `covered_requirements`（provenance 中 type=requirement 的 ref）/ `covered_risks`（type=risk 的 ref）/ `source`。
- Recommendation 缺失或空 → `metadata.warnings` 含 `MISSING_UPSTREAM_RESULT: recommendation`，本章标注信息不足，**不**自行推荐产品。

## 07 信息缺口（`information_gaps`）
- 合并三源并按重要性归类（`importance_to_category` → required/suggested/optional）：
  1. `requirement_analysis.information_gaps`
  2. `risk_analysis.next_information_needed`（HIGH→required / MEDIUM→suggested / LOW→optional）
  3. `risk_analysis.unknowns`（→suggested）
  4. `client_state.missing_from_upstream`（→required）
- 同字段取更高优先级类别。

## 08 经纪人下一步行动（`next_actions`）
- 由 07 的 required / suggested 缺口生成「确认/收集：<field>」动作（priority P0/P1），`dependency` 取来源 Skill。
- 固定追加两条：P1「基于补充信息重新评估保障缺口与风险结论」（依赖 Risk Analysis）；P2「进入保障方案设计与产品匹配」（依赖 Recommendation）。
