# Requirement Analysis Eval Policy

> 来源：原 EVAL.md + Lawgent 评估纪律（skill-hardening Step 7/Step 8）。
> 本文件是 Eval 的唯一真源：定义检查维度、失败类型、运行方式与「不弄虚」的判定纪律。

---

## 1. Eval 目标

Eval 不重新做需求分析，只检查：

1. 分析结果是否完整
2. 重要结论是否有证据支撑
3. 逻辑是否前后一致
4. 信息不足时是否越界输出确定结论
5. 是否泄漏到产品推荐层

## 2. 五类检查（确定性）

- **Completeness**：当前可分析 scope 是否遗漏 `risk_map`；`requirements / coverage_gaps / priorities` 是否与 scope 匹配。失败：`MISSING_RISK`
- **Evidence Grounding**：`risk_map.evidence_refs` 是否存在、evidence id 是否真实、是否引用事实上游字段、requirement/priority 能否追溯到 evidence。失败：`UNSUPPORTED_CONCLUSION`
- **Logical Consistency**：`risk_map.priority` 与 `requirements.priority` 一致；`coverage_gaps.priority` 与 requirement 一致；`analysis_status` 与输出内容不矛盾。失败：`LOGICAL_INCONSISTENCY`
- **Information Sufficiency**：当 `analysis_status = NEED_MORE_INFORMATION / CONFLICTING_INFORMATION` 时是否仍输出正式 requirement；`information_sufficiency.sufficiency_status` 与分析结果是否冲突。失败：`INSUFFICIENT_INFORMATION`
- **Requirement / Product Separation**：是否出现产品推荐、保险公司、购买建议等越界内容。失败：`PRODUCT_RECOMMENDATION_LEAK`

附加失败类型：`INVALID_OUTPUT`（结构错误）。

## 3. Eval 输出

结构化输出（`schemas/eval-output.schema.json`）：`eval_status`(PASS/FAIL) / `score`(0-100) / `checks`(5 维分) / `issues`(类型+位置+原因+证据) / `repair_required`。

## 4. 运行方式（确定性、无 LLM 依赖）

本 Skill 的 Eval 是**纯确定性 PowerShell + 配置规则**管道，不依赖任何 LLM 调度，因此可离线、可回归、可复现：

- 全量数据集回归：`scripts/run-requirement-analysis-dataset.ps1` —— 读 `evals/cases/requirement-analysis.dataset.json`（15 case），自动处理三类场景（正常分析 / 多轮补充后再分析 / 先分析再造错再 eval），产出 `evals/fixtures/dataset-report.json`。
- 单元测试（按阶段）：`scripts/test-requirement-analysis-{schema,sufficiency,questioning,analysis,eval,repair-loop}.ps1`，用例在 `evals/fixtures/unit/`。

## 5. Lawgent 评估纪律（三条，不能妥协）

1. **可机检断言**才判 PASS/FAIL。
2. **自然语言断言**记 MANUAL（需人工/Agent 判定），**一律不计为通过**。
3. **未真正执行**的 case 记 NOT_EXECUTED，其断言记 UNVERIFIED，**一律不计为通过**。

> 本 Skill 的既有 eval 已是确定性机检，故数据集 PASS 率（历史 15/15、均分 >93）是**真绿**，不是硬编码。每次重构/改动后必须重跑 §4 脚本确认无回归。

## 6. 真实基线维护

- 最近一次全量回归报告：`evals/fixtures/dataset-report.json`（提交入库作为基线证据）。
- 任何导致 `dataset-report.json` 退化的改动，必须先修复再合入。
- 负向自检：构造违反硬约束的样例（如 `PRODUCT_RECOMMENDATION_LEAK`、缺 evidence 的 `risk_map`），必须被对应 issue 捕获并 FAIL，否则 Eval 视为失效。
