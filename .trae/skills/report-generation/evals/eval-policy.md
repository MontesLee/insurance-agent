# Eval Policy — report-generation

本文件定义 Skill 6 的评估维度、用例清单与运行纪律，对应 AGENTS.md §6「可机检、非橡皮图章、单点真源」。

## 一、六维评估映射

| 维度 | 机检点 | 落在 |
|------|--------|------|
| structure（结构） | 8 章节齐全、schema 合规 | validate_report.validate_structure |
| completeness（完整性） | 上游存在时章节非空、缺失渲染待确认 | validate_report.validate_report |
| provenance（溯源） | success 时 provenance 非空且指向源 | validate_report.validate_report |
| hallucination（幻觉） | 金额子串比对 + 违禁词 | validate_report.validate_report |
| consistency（一致性） | status 枚举、validation.passed、errors 空 | validate_report.validate_consistency + 业务逻辑 |
| conflict（冲突） | UPSTREAM_CONFLICT 被 surface 而非拦截 | detect_conflicts + metadata/validation.conflicts |

## 二、用例清单（单一真源：`evals/cases/dataset-manifest.json`）

| 用例 | 维度 | 关键断言 |
|------|------|----------|
| complete_client | structure / completeness / provenance | 8 章节齐全、provenance 非空、无冲突、无幻觉；成稿禁含「百万医疗险（具体产品）」 |
| missing_financial_data | completeness / hallucination | 收入/资产/房贷/预算 UNKNOWN→渲染待确认；进入 info_gap & next_action；成稿禁含 100万/500万/10万/80万 |
| hallucination_guard | hallucination | 仅 30岁/已婚/1孩；成稿禁含 100万/500万/10万/80万/200万 |
| upstream_conflict | conflict / consistency | RA 医疗 P0 但 RK R1 P1 不一致 + 风险首要域(R2)≠需求首要域(R1)；metadata.conflicts 与 validation.conflicts 非空 |
| recommendation_boundary | recommendation-boundary | Rec 仅给方向 MED（无产品）；成稿禁含 百万医疗险/重疾险/定期寿险/意外险 |
| recommendation_missing | completeness / failure-handling | Rec 缺失；06 标注信息不足；metadata.warnings 含 MISSING_UPSTREAM_RESULT: recommendation |
| information_gap_propagation | completeness | 缺失 spouse_insurance/budget/health/parent；进入 07（required）与 08 |
| insufficient_input | failure-handling | 三路核心全缺；status=INSUFFICIENT_INPUT，不生成空洞成稿 |

## 三、运行命令

```bash
python scripts/run_report_dataset.py        # 全量回归（断言 expect）
python scripts/test-report-generation.py    # 8 用例 + 负向自愈
```

两个脚本 exit 0 + `ALL GREEN` 即通过。

## 四、负向自愈（防橡皮图章）

- **#1 破损溯源**：构造 `status=success` 但 `provenance=[]` 的输出 → `validate_output` 必须拒绝（exit≠0）。
- **#2 幻觉拦截**：构造成稿含臆造金额（「客户年收入 9999万，房贷 8888万」）且上游无该数据 → 必须报 `HALLUCINATION`。

## 五、纪律

- 所有断言必须可机检（断言 expect 字段 + 负向断言），不允许「看起来对」的人工放行。
- `dataset-manifest.json` 为唯一真源：运行器与文档都读它，改用例只改此文件。
- 改引擎/规则后必须重跑两套脚本；任一红 → 不视为完成。
