# CONTRACT — report-generation

## 边界

- **输入**：`client_profile`（ClientState）+ `requirement_analysis` + `risk_analysis`（必填）+ `knowledge_search` + `recommendation`（可选）
- **输出**：固定 8 章节《客户保险需求分析报告》（见 `schemas/report-output.schema.json`）
- **不**：重新做客户访谈 / 重新做需求分析 / 重新做风险分析 / 重新做产品推荐 / 自行测算保额 / 编造收入·资产·房贷·保费 / 扩展出具体产品名或销售话术 / 代表保险公司做承保决定

## 上游不可变（AGENTS.md §4）

- 不修改 `client-intake` / `requirement-analysis` / `risk-analysis` / `knowledge-search` / `recommendation` 任何文件
- 上游数据缺失或不兼容 → 在 adapter（`scripts/upstream_results_adapter.py` 的 `adapt_*`）内归一化并标记 `missing`，**严禁反向给上游加字段**
- 上游结论（优先级 / 风险 / 推荐方向）一律照搬；本 Skill 只做「组织 + 表达 + 校验 + 交付」，不重排、不重算、不重评
- `requirement-analysis` 契约要求 `guardrails.product_recommendation_included=false`；若上游越界携带产品推荐，本 Skill 拒绝采信并在 `warnings` 标注

## 单一职责（AGENTS.md §3 / §9）

- **No hallucination**：事实只能源自上游结构化产物；缺失 → 渲染「待确认」；渲染文本中的金额表达式经幻觉扫描（与上游允许金额集合做子串比对），命中违禁产品/公司名立即报错
- **Upstream priority**：结论直接采用上游；`risk_analysis` 与 `requirement_analysis` 对同一风险域的优先级不一致、或 RA / RK / Rec 首要风险域不一致 → 显式 `UPSTREAM_CONFLICT`，提示经纪人确认，**本报告不自行裁决**
- **Provenance**：每个关键章节陈述保留 `source`（如 `risk-analysis.R1-001`、`requirement-analysis.REQ-MED`、`client_state.financial_profile.annual_income`），成稿中每条事实带「（来源：…）」

## 确定性优先（AGENTS.md §5）

- 标签、映射（requirement_type→risk_category、priority→short/label、importance→category）、未知占位符、禁则全部外置于 `resources/config/report.rules.json`，引擎只读不算，零 LLM 依赖，可离线回归
- 所有结构化断言由 `scripts/validate_report.py` 做确定性校验（schema + 业务不变量）

## 双层产物

- `structured_report`：核心数据载体（机读、可校验）
- `rendered_report`：Markdown 成稿（人读），为 `structured_report` 的纯模板渲染，不含任何自主判断
- `status=INSUFFICIENT_INPUT`：仅当三路核心输入全部缺失时返回的最小化、合规（validation.passed=true）终端态
