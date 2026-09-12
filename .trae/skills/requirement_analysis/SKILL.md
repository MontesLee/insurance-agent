---
name: "requirement_analysis"
description: "保险需求分析。基于 client_intake 产出的客户画像进行信息充分性判断、需求识别、需求优先级分析与后续问题生成。严格停留在 Requirement 层，不推荐产品/公司/话术。"
argument-hint: "<客户画像目录 或 结构化 Input JSON>"
---

# Requirement Analysis Skill

读取 `client_intake` 已整理的客户事实，判断信息是否足以支撑需求分析，输出结构化需求分析结果，并严格区分事实 / 推理 / 假设 / 未知。

## Scope（负责）

- 信息充分性判断（加权打分 + Blocking/Conflict Fields）
- 需求识别与风险映射
- 需求优先级分析
- 主动追问生成与多轮补充
- Evidence 证据链生成

## Non-scope（不负责）

- 修改 `client_intake` 任何文件/逻辑
- 推荐具体保险产品、保险公司、销售话术
- 把 `UNKNOWN/ESTIMATED/ASSUMED` 当成 `KNOWN`

## Preconditions

- 输入来自 `client-intake-data/clients/<客户目录>/CLIENT_PROFILE.md`，由 `scripts/adapter-from-client-profile.ps1` 确定性转成结构化 Input（见 `schemas/input.schema.json`）
- 字段词汇映射表内置于 Adapter 脚本，**不得反向改 client_intake**

## Workflow 骨架

1. Adapter：`scripts/adapter-from-client-profile.ps1` 把 CLIENT_PROFILE → 结构化 Input（事实标 KNOWN/ESTIMATED/UNKNOWN/ASSUMED；UNKNOWN 绝不进 `answered_fields`）
2. Sufficiency：算 `information_sufficiency`（见 `references/04`）
3. Analysis：信息足够时输出 risk_map/coverage_gaps/requirements/priorities/evidence（见 `references/06`）
4. Questioning：信息不足时生成 ≤2 条追问，多轮补充（见 `references/05`）
5. Eval：确定性检查 5 维度（见 `evals/eval-policy.md`）
6. Repair Loop：FAIL → 针对 issue 修复 → 重跑，最多 `MAX_RETRY=2`，否则 `HUMAN_REVIEW_REQUIRED`（见 `references/07`）

## Knowledge Routing 表

| 何时需要 | 读哪份 |
|---|---|
| 判边界 / 与 client_intake 接口 | `references/01-boundary.md` |
| 输入结构 / 事实-推理-假设-未知分离 / 证据链 | `references/02-information-model.md` |
| 状态/需求类型/优先级枚举 | `references/03-status-enums.md` |
| 信息充分性引擎与评分阈值 | `references/04-information-sufficiency.md` |
| 主动追问与多轮策略 | `references/05-questioning.md` |
| 需求分析与风险映射规则 | `references/06-analysis.md` |
| 修复闭环与 MAX_RETRY | `references/07-repair-loop.md` |
| Eval 维度 / 失败类型 / 运行方式 | `evals/eval-policy.md` |
| 使用指南与 PowerShell 调用模板 | `resources/usage-guide.md` |

## Domain Overlays（险种扩展层）

通用层只讲方法论，险种专有规则一律下沉到 `overlays/<险种>/`：

| 需求类型 | Overlay | 维度文档 |
|---|---|---|
| life | `overlays/life/` | `requirement-dimensions.md` |
| critical_illness | `overlays/critical-illness/` | `requirement-dimensions.md` |
| medical | `overlays/medical/` | `requirement-dimensions.md` |
| accident | `overlays/accident/` | `requirement-dimensions.md` |
| savings | `overlays/savings/` | `requirement-dimensions.md` |

- `overlay.yaml` 声明：必填事实 / 证据引用 / 缺口公式 / 优先级档位 / 污染术语 / 边界红线
- `scripts/resolve-overlays.ps1`：确定性解析本次激活哪些险种
- 新增险种：复制 `overlays/_template/`，协议见 `overlays/README.md`
- 通用层出现险种专有术语 = 架构退化，守卫 `B2` 判 FAIL
## Output Contract

- 结构契约：`schemas/output.schema.json`
- Eval 输出契约：`schemas/eval-output.schema.json`
- 状态枚举 5 态：`COMPLETE / PRELIMINARY / NEED_MORE_INFORMATION / CONFLICTING_INFORMATION / FAILED`
- 需求类型 5 类：`medical / critical_illness / accident / life / savings`
- 优先级 4 级：`P0_CRITICAL / P1_HIGH / P2_MEDIUM / P3_LOW`
- 硬边界：`guardrails.product_recommendation_included` 必须为 `false`

## Failure Handling

- 结构错误 / 运行错误 → `analysis_status = FAILED`
- 信息不足或冲突 → 不输出正式 requirement，保留 `question_plan / next_actions`
- Eval FAIL → Repair Loop（见 `references/07`）；两次仍失败 → `HUMAN_REVIEW_REQUIRED`

## Quality Check（生产就绪判据）

- `scripts/check-skill-anatomy.ps1`：Skill Anatomy 守卫（SKILL.md ≤100 行、frontmatter 完整、引用存在的 references）
- `scripts/test-requirement-analysis-adapter.ps1`：Adapter 4 case 回归（结构契约 / 三 Scope 闭环 / 诚实 NEED_MORE / 空模板不崩）
- `scripts/test-requirement-analysis-schema.ps1`：输入输出 Schema 校验
- `scripts/run-requirement-analysis-dataset.ps1`：18 case 全量回归（基线 `evals/fixtures/dataset-report.json`）
- 每个守卫都有负向测试：注入污染 → 报红 → 清理 → 复绿

## 严格边界（再次强调）

绝对不输出具体产品、保险公司、比较方案、销售话术。越界即 `PRODUCT_RECOMMENDATION_LEAK`。
