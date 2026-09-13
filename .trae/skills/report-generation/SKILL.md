---
name: report-generation
description: >
  Assemble the structured upstream results (ClientState / Requirement Analysis / Risk Analysis /
  Knowledge Search / Recommendation) into the fixed 8-section 《客户保险需求分析报告》.
  Single responsibility: organize, express, validate, deliver — never re-analyze, re-rate,
  re-recommend, or fabricate facts.
argument-hint: <client_profile + requirement_analysis + risk_analysis + knowledge_search + recommendation>
---

# Report Generation

## 何时调用
仅当已具备 `client-intake`（ClientState）、`requirement-analysis`、`risk-analysis` 结构化输出，且需要一份**汇总成稿**的客户分析报告时调用。
**不用于**：采集客户事实、重做需求/风险分析、重做产品推荐、生成销售话术、替客户做承保/投保决定、自行测算保额。

## 输入
见 `schemas/report-input.schema.json`。核心五块（前三必填，后两可选）：
- `client_profile`（CanonicalClientState：画像 / 财务 / 责任 / 已有保障 / 健康）
- `requirement_analysis`（需求、优先级、保障缺口、信息缺口）
- `risk_analysis`（R1–R5 风险暴露、保障评估、下一步所需信息）
- `knowledge_search`（可选，知识检索结果，供参考）
- `recommendation`（可选，首选 / 备选保障方向 + provenance）

## 输出
见 `schemas/report-output.schema.json`：
- `status`：`success` / `INSUFFICIENT_INPUT`
- `structured_report`：8 个固定章节（client_profile / financial_profile / risk_exposure / coverage_gaps / requirement_priorities / recommended_directions / information_gaps / next_actions）
- `rendered_report`：8 章节 Markdown 成稿
- `validation`：结构 / 完整性 / 溯源 / 幻觉 / 一致性 / 冲突 六维校验结论
- `metadata`（source_skills / upstream_status / conflicts / warnings）
- `provenance[]`：关键陈述 → 上游来源溯源

## 核心工作流
`Validate → Adapt（upstream-results-adapter）→ Build 8 Sections → Detect Conflicts → Render → Validate → Output`。
引擎在 `scripts/report_generation_engine.py`，所有权重/映射/阈值/禁则外置于 `resources/config/report.rules.json`，**零 LLM 依赖**。

## 边界 / 不做什么（AGENTS.md §3 / §9）
- 不重分析：需求优先级、风险结论、产品推荐一律**照搬上游**，不重排、不重算、不重评。
- 不编造：事实缺失 → 渲染「待确认」；不臆造收入 / 资产 / 房贷 / 保费 / 具体产品名（幻觉扫描）。
- 不越界：只回显 Recommendation 的候选方向（candidate_id + fit + reason_codes + provenance），**不扩展为具体产品名或推销语**。
- 不裁决：上游结论冲突 → 显式 `UPSTREAM_CONFLICT` 并提示经纪人确认，本报告不自行择一。

## References（渐进加载）
- `references/01-report-schema.md` — 输入/输出 schema 与字段语义
- `references/02-report-writing-rules.md` — 成稿规则（不编造 / 不越界 / 溯源 / 冲突显式化）
- `references/03-report-section-rules.md` — 8 章节逐项生成规则
- `references/04-report-validation-rules.md` — 六维校验规则与负向断言
- 权重与映射：`resources/config/report.rules.json`（外置，引擎只读）

## Eval
见 `evals/eval-policy.md`；运行 `scripts/run_report_dataset.py`（全量回归，8 用例）+ `scripts/test-report-generation.py`（含负向自愈）。
