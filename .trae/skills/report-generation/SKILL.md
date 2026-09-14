---
name: report-generation
description: >
  Assemble the structured upstream Canonical Artifacts (ClientProfile / RequirementAnalysis /
  RiskAssessment / CoverageGapAnalysis / SolutionPlan / KnowledgeEvidence /
  ProductRecommendation) into the fixed 8-section 《客户保险需求分析报告》 + evidence appendix.
  Single responsibility: collect, normalize, render, validate — never re-analyze, re-rate,
  re-recommend, or fabricate facts.
argument-hint: <client_profile + requirement_analysis + risk_analysis [+ coverage_gap_analysis] [+ solution_plan] [+ knowledge_evidence] [+ product_recommendation]>
---

# Report Generation

## 何时调用
仅当已具备 `client-intake`（ClientState）、`requirement-analysis`、`risk-analysis` 结构化输出，且需要一份**汇总成稿**的客户分析报告时调用。
**不用于**：采集客户事实、重做需求/风险/缺口分析、重做策略或产品推荐、生成销售话术、替客户做承保/投保决定、自行测算保额。

## 输入
见 `schemas/report-input.schema.json`。前三必填，其余可选：
- `client_profile`（CanonicalClientState：画像 / 财务 / 责任 / 已有保障 / 健康）
- `requirement_analysis`（需求、优先级、信息缺口）
- `risk_analysis`（R1–R5 风险暴露、保障评估、下一步所需信息）
- `coverage_gap_analysis`（**Canonical 缺口的唯一事实源**；提供时 04 章节只用它，不再从 risk/requirement 推导）
- `solution_plan`（解决策略：objective / coverage_direction / 取舍 / 未采用方向）
- `knowledge_evidence`（证据，等价于 legacy `knowledge_search`）
- `product_recommendation`（推荐方向，等价于 legacy `recommendation`）

**别名规则**：canonical 键优先于 legacy 键；仅使用 legacy 键时行为不变（向后兼容）。

## 输出
见 `schemas/report-output.schema.json`：
- `status`：`success` / `INSUFFICIENT_INPUT`
- `structured_report`：8 个固定章节 + `coverage_gap_derivation` / `solution_strategies` / `evidence_summary`
- `rendered_report`：8 章节 Markdown 成稿 + 附录 A 证据来源
- `validation`：结构 / 完整性 / 溯源 / 幻觉 / 一致性 / 冲突 六维校验结论
- `metadata`（source_skills / upstream_status（canonical 名）/ conflicts / warnings）
- `provenance[]`：关键陈述 → 上游来源溯源

## 核心工作流
`Validate → Adapt（upstream-results-adapter）→ Build 8 Sections → Detect Conflicts → Render → Validate → Output`。
引擎在 `scripts/report_generation_engine.py`，所有权重/映射/阈值/禁则外置于 `resources/config/report.rules.json`，**零 LLM 依赖**。

## 边界 / 不做什么（AGENTS.md §3 / §9）
- 不重分析：需求优先级、风险结论、**缺口等级**、**解决策略**、产品推荐一律**照搬上游**，不重排、不重算、不重评。
- **04 章节 canonical-first**：提供 `coverage_gap_analysis` 时它是唯一来源（`derivation="canonical"`）；缺失时回退推导并强制打标 `derivation="derived"` + `GAP_SOURCE_DERIVED_NOT_CANONICAL` 警告。两者永不混淆。
- 不编造：事实缺失 → 渲染「待确认」；不臆造收入 / 资产 / 房贷 / 保费 / 具体产品名（幻觉扫描）。
  **策略文本逐字复制**——改写策略等于生成另一条策略。
- 不越界：只回显 ProductRecommendation 的候选方向（candidate_id + fit + reason_codes + provenance），**不扩展为具体产品名或推销语**。
- 不裁决：上游结论冲突（含跨 Artifact 冲突）→ 显式 `UPSTREAM_CONFLICT` 并提示经纪人确认，本报告不自行择一。
- 不改动上游：adapter 只读，`no_upstream_mutation` 不变量强制。

## References（渐进加载）
- `references/01-report-schema.md` — 输入/输出 schema 与字段语义
- `references/02-report-writing-rules.md` — 成稿规则（不编造 / 不越界 / 溯源 / 冲突显式化）
- `references/03-report-section-rules.md` — 8 章节逐项生成规则
- `references/04-report-validation-rules.md` — 六维校验规则与负向断言
- 权重与映射：`resources/config/report.rules.json`（外置，引擎只读）

## Eval
见 `evals/eval-policy.md`。
- V1 回归：`scripts/run_report_dataset.py`（8 用例）+ `scripts/test-report-generation.py`（含 2 项负向自检）
- V2 数据集：`scripts/run_report_v2_dataset.py`（6 用例，清单 `evals/cases/v2-dataset-manifest.json`）
- V2 架构不变量：`scripts/test_report_v2.py`（10 项，含「无业务判断权」断言）
