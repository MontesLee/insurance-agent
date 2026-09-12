---
name: risk-analysis
description: 家庭风险分析。基于 Canonical Client State 与已确认需求，判断家庭暴露在哪些风险、后果多大、现有缓冲能吸收多少、剩余风险有多高、哪些应优先处理。当已有 Requirement Analysis 输出、需要进入风险层（Risk）而非需求层（Requirement）或产品层（Product）时使用。
argument-hint: 提供 client-intake 的 CLIENT_PROFILE.md 与 requirement-analysis 的输出 JSON 路径，可选指定 analysis_scope（R1–R5）
---

# Risk Analysis

**核心问题**：这个家庭真正暴露在哪些风险上？风险有多大？哪些值得优先处理？

> 完整契约见 [`CONTRACT.md`](CONTRACT.md)。项目级命名 / 分层 / 上游不可变约定见仓库根 [`AGENTS.md`](../../../AGENTS.md)。

---

## Identity

| 项 | 值 |
|---|---|
| 层 | `risk_analysis` |
| 上游 | `requirement-analysis`（需求）、`client-intake`（事实，经 ClientState 间接消费） |
| 下游 | `coverage-gap-analysis`（消费 `residual_risk`） |
| 产物 | `Risks`（severity / likelihood / residual_risk / priority） |
| 引擎 | 确定性脚本，无 LLM 依赖 |

## Trigger

✅ 已有 `requirement-analysis` 输出，且需要判断**风险**而非需求时。
❌ 不用于：采集事实（`client-intake`）、识别需求（`requirement-analysis`）、推荐产品（下游）。

## Input

```text
Canonical Client State  (事实，源自 client-intake，经本 Skill adapter 规范化)
        +
RequirementAnalysisOutput.requirements  (需求层结论)
        ↓
RiskAnalysisInput   [schemas/risk-analysis-input.schema.json]
```

**不自由双读两份上游 output。** 事实溯源统一指向 `client_state.<profile>.<field>`。

## Workflow

```text
INPUT → Normalize/Provenance → Sufficiency Check (dependency graph)
      → Risk Discovery (R1–R5) → Exposure → Impact
      → Existing Protection → Residual Risk
      → Severity × Likelihood → Priority
      → Evidence/Reasoning/Conclusion
      → Eval(7) ──PASS──→ OUTPUT
                 └─FAIL──→ Repair(≤2) → Re-analysis → Eval
                              └─仍失败──→ NEEDS_REVIEW
```

每一步的深层规则见 `references/`，本文件不展开。

## Output

- 机器可读（**唯一事实源**）：`schemas/risk-analysis-output.schema.json`
- 渲染层：`家庭风险分析报告`（9 节，见 `references/output-schema.md`）

## Safety Boundary

- ❌ 不推荐任何保险产品 / 险种 / 保额建议
- ❌ 不重新产出 `requirement`（那是上游的活）
- ❌ 不修改 `client-intake` / `requirement-analysis` 任何文件；上游缺失只记 `MISSING_FROM_UPSTREAM` 并降级 `UNKNOWN`
- ❌ 不恐吓、不夸大、不为制造需求而抬高等级
- ✅ 允许："建议进一步解决该风险 / 评估收入替代能力 / 量化长期责任"

**最高优先级**：`UNKNOWN > fabricated certainty`。宁可不知道，不得假装知道。

## References

| 文件 | 内容 |
|---|---|
| `references/01-provenance.md` | 证据溯源与 5 态 status 规则 |
| `references/02-sufficiency.md` | 风险依赖图与充分性判定（**已完成**：规则 + 引擎 + 单测） |
| `references/03-risk-taxonomy.md` | R1–R5 风险域定义与发现规则（V1.0，非 overlay）**已完成**：规则 + 引擎 + 11 单测 |
| `references/04-risk-scoring.md` | Severity / Likelihood / Residual / Priority 确定性档位 **已完成**：规则 + 引擎 + 10 单测 |
| `references/05-questioning.md` | Expected Information Value 追问协议 |
| `references/06-output-schema.md` | Markdown 报告结构（9 节） |

## Eval

7 项独立机检：`completeness` / `evidence_grounding` / `reasoning_consistency` / `separation` / `unknown_integrity` / `priority_consistency` / `anti_sales`。

纪律：可机检才判 PASS；`MANUAL` / `NOT_EXECUTED` **不计通过**；FAIL → Repair(≤2) → 复评 → 仍失败 `NEEDS_REVIEW`。

规则与词典外置：`evals/eval-policy.md`（7 项判定细则）、`resources/config/anti-sales.rules.json`（恐吓/夸大/销售动词/产品名词典）。
反例 fixture 在 `evals/fixtures/unit/eval/`，每个精确命中且**只命中**一项检查（反向断言防误伤）。

## Scripts

| 脚本 | 作用 |
|---|---|
| `scripts/build-client-state.ps1` | client-intake 画像 → Canonical Client State（只读上游） |
| `scripts/build-risk-input.ps1` | ClientState + RA output → RiskAnalysisInput |
| `scripts/invoke-risk-analysis-sufficiency.ps1` | 充分性引擎（依赖图 + EIV 追问，规则外置）✅ Phase 3 |
| `scripts/invoke-risk-analysis-discovery.ps1` | 发现引擎（R1–R5 三态判定 + 证据登记，规则外置）✅ Phase 4 |
| `scripts/invoke-risk-analysis-analysis.ps1` | 主分析引擎（确定性量化：gross→protected→severity→likelihood→residual→priority，规则全外置）✅ Phase 5 |
| `scripts/invoke-risk-analysis-eval.ps1` | Eval 引擎（7 项确定性机检；`-DiscoveryJsonPath` 启用"应发现域覆盖"；词典外置）✅ Phase 6 |
| `scripts/check-skill-anatomy.ps1` | 架构守卫（⏳ 待建，骨架约定见上级 `AGENTS.md`） |
| `scripts/verify-contract.py` | 契约校验（schema + 金样本 + 负向 + 阶段产物；§8 校验 EvalResult） |

## Phase 进度

| Phase | 内容 | 状态 |
|---|---|---|
| 1 | Reconnaissance | ✅ |
| 2 | Contract（5 schema + CONTRACT.md + AGENTS.md） | ✅ |
| 3 | Sufficiency（依赖图 + EIV + 引擎 + 8 单测） | ✅ |
| 4 | Discovery（R1–R5 分类 + 三态判定 + 引擎 + 11 单测） | ✅ |
| 5 | Scoring（确定性量化引擎：gross→protected→severity→likelihood→residual→priority，规则外置 `risk-scoring.rules.json`；10 单测 + 契约校验） | ✅ |
| 6 | Eval（7 项机检 + anti-sales 词典外置 + 16 单测 + 契约 §8） | ✅ |
| 7–9 | Repair / Dataset / Review | ⏳ |
