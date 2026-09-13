# Reference 04 — Report Validation Rules（六维校验）

校验由 `scripts/validate_report.py` 提供两层：`validate_structure`（Draft7 对照 `report-output.schema.json`）+ `validate_consistency`（业务不变量）。引擎内部 `validate_report()` 另做完整性/溯源/幻觉/冲突检查，结果写入输出 `validation`。

## 维度一：结构（STRUCTURE）
- 8 固定章节必须全部存在于 `structured_report`：client_profile / financial_profile / risk_exposure / coverage_gaps / requirement_priorities / recommended_directions / information_gaps / next_actions。
- 缺失任一 → `STRUCTURE: missing section`。

## 维度二：完整性（COMPLETENESS）
- 上游 `client_state` 存在但 `client_profile.fields` 为空 → `COMPLETENESS` 错误。
- 上游 `risk_analysis` 存在但 `risk_exposure` 五个类别全 `present=false` → `COMPLETENESS` 错误。
- 缺失字段已在章节内渲染「待确认」（见 Reference 02 R1），不计入此处错误。

## 维度三：溯源（PROVENANCE）
- `status=success` 且 `provenance` 为空 → `PROVENANCE` 错误（有上游数据却无溯源，属异常）。
- 逐条 provenance 必须含 `source` 指向上游（client_state / requirement-analysis / risk-analysis / recommendation）。

## 维度四：幻觉（HALLUCINATION）
- 金额扫描：成稿中的金额表达式必须命中 `structured_report` 允许金额集合（子串比对）。未命中 → `HALLUCINATION` 错误（参 Reference 02 R1）。
- 违禁产品/公司名扫描：`forbidden_product_names` / `forbidden_company_names` 命中 → `HALLUCINATION` 错误。
- 仅 `status=success` 时启用（`INSUFFICIENT_INPUT` 不做金额约束）。

## 维度五：一致性（CONSISTENCY，`validate_consistency`）
- `status ∈ {success, INSUFFICIENT_INPUT}`。
- 8 章节齐全。
- `status=success` 时 `provenance` 非空。
- `validation.passed` 必须为 `true` 且 `validation.errors` 必须为空（否则 `OUTPUT_INVALID`）。

## 维度六：上游冲突（CONFLICT）
- 冲突由引擎 `detect_conflicts()` 计算，写入 `metadata.conflicts` 与 `validation.conflicts`。
- 冲突**不致命**：报告仍可 `validation.passed=true`（冲突被显式 surface，而非拦截）。
- 两类冲突：(a) 同一 risk_category 在需求侧与风险侧优先级不一致；(b) RA / RK / Rec 首要风险域不一致。

## 负向断言（AGENTS.md §6，防橡皮图章）
- 负向#1：构造 `status=success` 但 `provenance=[]` 的破损输出 → `validate_output` 必须拒绝（exit≠0）。
- 负向#2：构造成稿含臆造金额（如「客户年收入 9999万」）且上游无该数据 → 必须报 `HALLUCINATION`。
- 两断言均在 `scripts/test-report-generation.py` 中机检，确保校验器真正生效而非放行。
