---
name: risk-analysis
description: 家庭风险分析。基于 Canonical Client State 与已确认需求，判断家庭暴露在哪些风险、后果多大、现有缓冲能吸收多少、剩余风险有多高、哪些应优先处理。当已有 Requirement Analysis 输出、需要进入风险层（Risk）而非需求层（Requirement）或产品层（Product）时使用。
argument-hint: 提供 RiskAnalysisInput JSON（ClientState + requirements），可选指定 analysis_scope（R1–R5）
---

# Risk Analysis

**核心问题**：这个家庭真正暴露在哪些风险上？风险有多大？哪些值得优先处理？

> 契约 [`CONTRACT.md`](CONTRACT.md)｜调用模板 [`resources/usage-guide.md`](resources/usage-guide.md)｜项目约定 [`AGENTS.md`](../../../AGENTS.md)

## Identity

| 项 | 值 |
|---|---|
| 层 | `risk_analysis`（FACT → REQUIREMENT → **RISK** → GAP → SOLUTION → PRODUCT） |
| 上游 | `client-intake`（事实，经 ClientState）、`requirement-analysis`（需求） |
| 下游 | `coverage-gap-analysis`（消费 `residual_risk`） |
| 产物 | `Risks`（severity / likelihood / residual_risk / priority） |
| 引擎 | 确定性 PowerShell，零 LLM 依赖，可离线回归 |

## Trigger

✅ 已有 `requirement-analysis` 输出，需判断**风险**时。
❌ 不用于采集事实、识别需求、推荐产品。

## Input / Output

- 输入：`RiskAnalysisInput` = ClientState + `requirements`（不自由双读两份上游 output）
- 输出：`RiskAnalysisOutput` JSON（**唯一事实源**）；Markdown 报告为渲染层（9 节，见 `references/06-output-schema.md`，未内置渲染器）

## Workflow

```text
INPUT → 充分性（依赖图） → 发现（R1–R5 三态） → 量化（severity×likelihood→residual→priority）
      → Eval(7 项机检) ──PASS──→ OUTPUT
                       └─FAIL──→ Repair(≤2) → 复评 → 仍失败 → NEEDS_REVIEW
```

## Safety Boundary

- ❌ 推荐产品 / 险种 / 保额｜❌ 重产 `requirement`｜❌ 修改上游文件｜❌ 恐吓、夸大、为卖而抬级
- ✅ 允许"建议进一步解决该风险 / 评估收入替代能力 / 量化长期责任"
- **最高优先级：`UNKNOWN > fabricated certainty`。宁可不知道，不得假装知道。**

## References

| 文件 | 内容 |
|---|---|
| `references/01-provenance.md` | 证据溯源与 5 态 status ✅ |
| `references/02-sufficiency.md` | 风险依赖图与充分性判定 ✅ |
| `references/03-risk-taxonomy.md` | R1–R5 定义与发现规则（V1.0，非 overlay）✅ |
| `references/04-risk-scoring.md` | Severity / Likelihood / Residual / Priority 档位 ✅ |
| `references/05-questioning.md` | EIV 追问协议 ✅ |
| `references/06-output-schema.md` | Markdown 报告渲染契约（9 节）✅ |
| `references/07-repair-loop.md` | Repair 红线与动作清单 ✅ |
| `references/08-dataset.md` | 端到端数据集设计、探针纪律 ✅ |
| `references/09-review.md` | Phase 9 终审：审计发现、处置、残余风险 ✅ |

## 质量闸门

**Eval**（7 项独立机检）：`completeness` / `evidence_grounding` / `reasoning_consistency` / `separation` / `unknown_integrity` / `priority_consistency` / `anti_sales`。
纪律：可机检才判 PASS；`MANUAL` / `NOT_EXECUTED` **不计通过**。规则与词典外置 `evals/eval-policy.md`、`resources/config/anti-sales.rules.json`。

**Repair**：只做确定性重算与降级撤回，**绝不发明事实、绝不清洗立场问题**。
AUTO：`CLAMP_NOT_IDENTIFIED_BANDS` / `RECOMPUTE_RESIDUAL` / `RECOMPUTE_PRIORITY` / `DROP_DANGLING_REFS`；
REVIEW：`MISSING_RISK` / `UNKNOWN_AS_KNOWN` / `SALES_BIAS` / `PRODUCT_RECOMMENDATION_LEAK` / `INVALID_OUTPUT` / 无证据结论。

**Dataset**：15 个端到端用例（7 原型 / 3 降级 / 5 变异），五维评分全部由 `EvalResult.checks` 换算；3 个反橡皮图章探针注入篡改规则，数据集**必须**掉分。

## Scripts

| 脚本 | 作用 |
|---|---|
| `invoke-*-{sufficiency,discovery,analysis,eval,repair}.ps1` | 五个阶段引擎（`-RulesPath` 可注入规则做负向测试） |
| `run-risk-analysis-dataset.ps1` / `test-risk-analysis-dataset.ps1` | 全链路数据集运行器 / 回归+探针 |
| `test-risk-analysis-<stage>.ps1` | 各阶段单元测试 |
| `test-risk-analysis-anatomy.ps1` | 架构守卫的负向自检（注入污染必须 FAIL） |
| `check-skill-anatomy.ps1` | 架构守卫：骨架 / 命名 / 悬空引用 / 死配置 / BOM / 不写上游 |
| `verify-contract.py` | 契约校验 §1–§10（schema + 金样本 + 负向 + 红线） |
| `gen-dataset-cases.py` / `gen-repair-fixtures.py` | 用例与夹具的可复现生成器 |
| `fix_ps1_bom.py` | 开发期工具：给 .ps1 补回 UTF-8 BOM（Edit 会剥 BOM） |
| `build-client-state.ps1` / `build-risk-input.ps1` | ⏳ 未实现：从 `CLIENT_PROFILE.md` 直接开工的 adapter，v1 不需 |

## Phase 进度

| Phase | 内容 | 状态 |
|---|---|---|
| 1–2 | Reconnaissance / Contract（5 schema + CONTRACT.md） | ✅ |
| 3–5 | Sufficiency / Discovery / Scoring | ✅ |
| 6–8 | Eval / Repair / Dataset | ✅ |
| 9 | Review（假外置治理 + 架构守卫 + 文档收口） | ✅ |
