# Reference 02 — Report Writing Rules（成稿规则）

本文件定义《客户保险需求分析报告》的成稿纪律。引擎是纯模板，以下规则由 `resources/config/report.rules.json` 固化并由 `validate_report.py` 机检。

## R0 单一职责（最高优先级，AGENTS.md §9）
报告只做「组织 + 表达 + 校验 + 交付」。任何重分析、重评级、重推荐、产品推销、保额测算都属越界。

## R1 不编造（No Hallucination）
- 所有数值、陈述**逐字复制**自上游 `factValue.value` 或上游字符串字段。
- 上游 `status=UNKNOWN` 或 `value=null` → 渲染占位符 `未知状态 token`（`report.rules.json` 的 `unknown_status_token`，默认「待确认」），**绝不**填入猜测数字。
- **金额幻觉扫描**：渲染文本中的金额表达式（正则 `money_regex`：`[0-9][0-9,]*(\.[0-9]+)?\s*(万元|元|万)`）必须与 `structured_report` 全部字符串叶子中的允许金额做子串比对；扫描出的金额若不在允许集合 → `HALLUCINATION` 错误。
  - 原理：引擎只逐字拷贝上游，故成稿中出现的任何合法金额必然已存在于 `structured_report` 叶子中 → 合法数据不会误报；只有被注入/臆造的金额会被捕获。
- **违禁词扫描**：`forbidden_product_names` / `forbidden_company_names`（默认空）若出现在成稿 → `HALLUCINATION` 错误。

## R2 不越界（推荐保障方向 ≠ 具体产品）
- `06 推荐保障方向` 只回显 Recommendation 的 `candidate_id`（如 `MED+CI`、`ACC`）+ `fit` + `reason_codes`（映射为中文：`covers_high_priority_risk→覆盖高优先级风险` 等）+ `provenance`。
- **绝不**把候选方向扩展为具体产品名（如「百万医疗险」「重疾险」「定期寿险」）或推销语句。成稿中不得出现保险商品品牌/产品名。

## R3 溯源（Provenance）
- 结构化层 `provenance[]` 记录每条关键陈述 → 上游 `source`（如 `risk-analysis.R1-001`、`requirement-analysis.REQ-MED`、`client_state.financial_profile.annual_income`）。
- 成稿（Markdown）中每条事实后附「（来源：…）」。

## R4 上游优先 + 冲突显式化（Upstream Priority / Conflict）
- 结论直接采用上游；不重排优先级、不重算风险、不重评推荐。
- 当 `requirement_analysis` 与 `risk_analysis` 对同一 `risk_category` 的优先级不一致，或 RA / RK / Rec 的首要风险域不一致 → 在 `metadata.conflicts` + `validation.conflicts` 写入 `UPSTREAM_CONFLICT`，成稿追加「上游结论冲突提示」章节。
- **不自行裁决**：冲突只提示经纪人确认，本报告永不替上游择一。

## R5 缺失显式（Missing Explicit）
- 上游整块缺失 → `metadata.warnings` 标 `MISSING_UPSTREAM_RESULT: <skill>`。
- 三路核心全缺 → `status=INSUFFICIENT_INPUT`，返回最小化但合规（validation.passed=true）的报告，不生成空洞成稿。

## R6 客观中立（Tone）
- 使用克制、客观的书面语；不出现「建议立即购买」「最划算」等推销/诱导性措辞。
- 报告头部固定声明：事实来自 ClientState / Requirement Analysis / Risk Analysis，推荐方向来自 Recommendation，不包含自主保险判断或产品推销。
