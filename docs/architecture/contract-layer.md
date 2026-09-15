# 保险 Agent V2 — Phase 1：Canonical Contract Layer

> 本文件记录 **Phase 1（Canonical Contract Layer）** 的产出与验证结论。
> Phase 0 基线见 `docs/dev-notes/architecture-v2-audit.md`（**本文件不修改审计基线**）。
> 本阶段**只新增契约与适配器，不重写任何既有 Skill 业务逻辑**（见文末 git 变更摘要）。

---

## 1. 目标与原则

| 原则 | 说明 |
|---|---|
| Contract First | Skill 之间只通过 Canonical Contract 交换 Artifact；不再依赖文件路径 / Prompt 约定 / 隐含字段直接耦合。 |
| 不重写业务逻辑 | `client-intake`、`requirement_analysis`、`risk-analysis`、`knowledge-search`、`recommendation`、`report-generation` 本阶段**禁止修改逻辑**。 |
| 向后兼容 Adapter | 既有 Skill 的输出经 Adapter 包成 Canonical Artifact，未来重构 Skill 实现时 Adapter 边界独立变化。 |
| 边界即契约 | 本阶段先把“边界”立起来；深度的 Canonical 重塑留待各 Skill 在后续 Phase 重建时进行。 |

---

## 2. 9 份 Canonical Contract

位置：`contracts/*.schema.json`（draft-07）。每份都是统一的 **envelope**：

```jsonc
{
  "artifact_type": "client-profile | requirement-analysis | risk-assessment | coverage-gap-analysis | solution-plan | knowledge-query | knowledge-evidence | product-recommendation | insurance-report",
  "skill": "canonical skill id (kebab-case)",
  "legacy_skill": "legacy physical dir name (may be snake_case)",
  "schema_version": "1.0",
  "generated_at": "ISO-8601",
  "payload": { ... },                       // 实际内容（见下表）
  "provenance": [ { "source_type", "source_id", "field?", "confidence?" } ]
}
```

| # | Contract 文件 | artifact_type | 来源 Skill（legacy） | payload 严格度 | 状态 |
|---|---|---|---|---|---|
| 1 | `client-profile.schema.json` | client-profile | client-intake | 宽松（对象） | 已有 Skill |
| 2 | `requirement-analysis.schema.json` | requirement-analysis | requirement_analysis | 宽松（对象） | 已有 Skill |
| 3 | `risk-assessment.schema.json` | risk-assessment | risk-analysis | 宽松（对象） | 已有 Skill |
| 4 | `coverage-gap-analysis.schema.json` | coverage-gap-analysis | coverage-gap-analysis（Phase 2 新建） | **严格** | 已实现 Skill |
| 5 | `solution-plan.schema.json` | solution-plan | solution（Phase 3 新建） | **严格** | 已实现 Skill |
| 6 | `knowledge-query.schema.json` | knowledge-query | knowledge-search（请求） | **严格** | 前瞻契约 |
| 7 | `knowledge-evidence.schema.json` | knowledge-evidence | knowledge-search（产出） | **严格** | 已有 Skill |
| 8 | `product-recommendation.schema.json` | product-recommendation | recommendation | **严格** | 已有 Skill（重命名） |
| 9 | `insurance-report.schema.json` | insurance-report | report-generation | 宽松（对象） | 已有 Skill |

> **宽松 vs 严格**：6 个已有 Skill 的 payload 在 Phase 1 为 `{"type":"object"}`——它们的内部形态已由各自 output schema + 既有 eval 保障，本阶段只验证“契约边界”（包成带 canonical 标签的 Artifact）。3 个前瞻契约（coverage-gap / solution / knowledge-query）及 knowledge-evidence / product-recommendation 的 payload 按 V2 规范**精确定义**，作为未来 Skill 实现的硬目标。

附带：`contracts/skill-id-map.json` 记录 `canonical → legacy` 映射（Phase 1 不移动 `.trae/skills/`，仅做逻辑名解耦）。

---

## 3. Adapter 映射（Skill → Legacy Output → Adapter → Canonical Artifact → 下游消费者）

| Skill（legacy） | Legacy Output | Adapter | Canonical Artifact | 下游消费者 |
|---|---|---|---|---|
| client-intake | CanonicalClientState (`client-state.schema.json`) | `client_intake_adapter` | ClientProfile | requirement-analysis, risk-analysis |
| requirement_analysis | RequirementAnalysisOutput (`output.schema.json`) | `requirement_analysis_adapter` | RequirementAnalysis | risk-analysis, coverage-gap-analysis, solution, product-recommendation, report-generation |
| risk-analysis | RiskAnalysisOutput (`risk-analysis-output.schema.json`) | `risk_analysis_adapter` | RiskAssessment | coverage-gap-analysis, solution, product-recommendation, report-generation |
| coverage-gap-analysis | CoverageGapAnalysis（引擎产出，严格结构） | `coverage_gap_analysis_adapter` | CoverageGapAnalysis | solution, product-recommendation, report-generation |
| solution | SolutionPlan（引擎产出，严格结构） | `solution_adapter` | SolutionPlan | product-recommendation, knowledge-search（Evidence 回环）, report-generation |
| knowledge-search | KnowledgeSearchOutput (`knowledge-search-output.schema.json`) | `knowledge_search_adapter` | KnowledgeEvidence | solution, product-recommendation, report-generation（按需，非固定步骤） |
| recommendation | RecommendationOutput (`recommendation-output.schema.json`) | `recommendation_adapter` | ProductRecommendation | report-generation |
| report-generation | ReportGenerationResult (`report-output.schema.json`) | `report_generation_adapter` | InsuranceReport | 终端 |

Adapter 仅做**包络 / 重命名 / 归一化**，不含任何业务判断。

> **Phase 5 输入契约变更**：`recommendation` 的**输入**已升级为 V2
> （`product-recommendation-input.schema.json`），消费
> `RequirementAnalysis + RiskAssessment + CoverageGapAnalysis + SolutionPlan [+ KnowledgeEvidence]`，
> 并以 `not: {required: [candidate_solutions]}` **机器禁止**再把 `candidate_solutions`
> 当独立隐式输入 —— 候选改由 `solution_to_candidates.py` 从 `SolutionPlan.solutions[]` 派生。
> 这根治了 Phase 0 审计的 P1（`candidate_solutions` 无生产者）。
> **输出形态与 `recommendation_adapter` 均未变。** 详见 `docs/architecture/product-recommendation-v2.md`。

---

## 4. 三个边界修正（来自用户 Phase 1 评审，已落地于契约）

1. **Coverage Gap 是独立业务判断层，不是 Risk Analysis 的字段拆解。**
   `coverage-gap-analysis` 契约独立定义 `gaps[]`（含 `current_coverage.status: NONE/PARTIAL/SUFFICIENT/UNKNOWN`、`target_coverage.direction`、`gap_level`、`related_risk_ids`）。**刻意不复制 severity / likelihood**——Risk ≠ Coverage Gap，只引用 `risk_id`。`risk-analysis.coverage_assessment` 在契约中明确为“风险层辅助判断”，最终缺口结论归 `coverage-gap-analysis`。未来保单体检 / 家庭保障盘点 / 旧保单分析均可挂此层。

2. **Solution 是“解决策略”，不是“推荐保险方案”。**
   `solution-plan` 契约只表达 `solution_type / objective / coverage_direction / priority / constraints / trade_offs / rejected_directions`，**禁止出现具体产品名或保险公司名**。链路语义明确为：
   `Risk（可能出什么问题）→ Coverage Gap（现在缺什么）→ Solution（应采用什么解决策略）→ Product（哪些产品实现策略）`。

3. **Knowledge Search 是共享 Evidence Provider，不是 workflow 固定第 6 步。**
   `knowledge-query` 契约定义 `purpose ∈ {SOLUTION_VALIDATION, PRODUCT_VALIDATION, POLICY_FACT, MEDICAL_FACT, REGULATORY_FACT, COMPARISON, OTHER}` 与 `related_artifact_ids`，支持 `Skill → Evidence Request → Knowledge Search → Skill` 的受控回环，而非写死线性步骤。

> 另：用户明确**暂缓 `domain/insurance`**（Domain Pack / Overlay / Playbook）。Phase 1 只建 `contracts/ + adapters/ + tests/`；`domain/insurance/` 留待 8 个 Skill 跑稳后的 V2.1。

---

## 5. 验证结论

### 5.1 Contract Tests（新增）— `tests/contracts/run_contract_tests.py`
9/9 全绿：

```
[PASS] client-profile            (真实 CanonicalClientState → adapter)
[PASS] requirement-analysis     (真实 RequirementAnalysisOutput → adapter)
[PASS] risk-assessment          (代表性 RiskAnalysisOutput 样本 → adapter)
[PASS] coverage-gap-analysis    (真实引擎产出 → adapter，契约可满足且不带 severity/likelihood)
[PASS] solution-plan            (真实引擎产出 → adapter；每 Gap 一条策略，priority 由 gap_level 推导)
[PASS] knowledge-query          (合成合法 KnowledgeQueryArtifact)
[PASS] knowledge-evidence       (真实 KnowledgeSearchOutput → adapter 转换)
[PASS] product-recommendation   (真实 RecommendationOutput → adapter)
[PASS] insurance-report         (真实 ReportGenerationResult → adapter)
CONTRACT TESTS: 9/9 passed  →  RESULT: ALL GREEN
```

### 5.2 既有 Eval 回归
| 来源 | 结果 | 说明 |
|---|---|---|
| report-generation（legacy） | **ALL GREEN**（8 case + 2 negative） | 经 Python runner 实测 |
| **report-generation V2**（Phase 6） | **ALL GREEN**（6 case + 10 项架构不变量 + 5 项负向探针） | 经 Python runner 实测 |
| recommendation | **ALL GREEN**（11 case） | 经 Python runner 实测 |
| knowledge-search | **ALL GREEN**（dataset） | 经 Python runner 实测 |
| **coverage-gap-analysis**（Phase 2 新建） | **ALL GREEN**（5 case + 契约校验 + 架构不变量单测） | 经 Python runner 实测 |
| **solution**（Phase 3 新建） | **ALL GREEN**（5 case + 契约校验 + 9 项架构不变量 + 负向探针） | 经 Python runner 实测 |
| **evidence**（Phase 4 新建） | **ALL GREEN**（5 case + 7 项架构不变量 + 3 项负向探针） | 经 Python runner 实测（真实 knowledge-search 引擎） |
| requirement_analysis | 环境受限未在本沙箱实跑 | 其源文件 0 修改，回归结构性保持；本地命令见下 |
| risk-analysis | 环境受限未在本沙箱实跑 | 其源文件 0 修改，回归结构性保持；本地命令见下 |

> **沙箱限制说明**：`requirement_analysis` 与 `risk-analysis` 的 eval runner 是 PowerShell（`.ps1`），本环境的安全策略拦截 `Set-ExecutionPolicy`，故无法在此实跑。但 Phase 1 **未触碰这两个 Skill 的任意源文件**（见 §6 git 摘要），回归在结构上被保证。本地复跑命令：
> ```powershell
> pwsh -ExecutionPolicy Bypass -File .trae/skills/requirement_analysis/scripts/run-requirement-analysis-dataset.ps1
> pwsh -ExecutionPolicy Bypass -File .trae/skills/risk-analysis/scripts/run-risk-analysis-dataset.ps1
> ```

### 5.3 业务逻辑零改写确认
git status 仅显示新增未跟踪目录 `adapters/`、`contracts/`、`tests/`、`.trae/skills/coverage-gap-analysis/`、`.trae/skills/solution/`，以及 Phase 0 的 `docs/architecture-v2-audit.md`、Phase 1 的 `docs/architecture-v2.md` / `docs/contract-layer.md`。**`git diff` 为空（无任何已跟踪文件被修改）**；逐 Skill 检查确认 6 个既有 Skill（`client-intake` / `requirement_analysis` / `risk-analysis` / `knowledge-search` / `recommendation` / `report-generation`）**各 0 个文件被修改**。

Phase 2 / Phase 3 / Phase 4 均为纯新增：`coverage-gap-analysis` 与 `solution` 两个新 Skill、共享 `evidence/` 层，以及 `adapters/coverage_gap_analysis_adapter.py`、`adapters/solution_adapter.py`（均为纯包络，无业务逻辑）。**`knowledge-search` 本阶段 0 文件被修改**——Evidence Provider 只是加载并调用其既有入口，未重造检索、未改其判定。

**Phase 5 / Phase 6 是首次修改既有 Skill**（均由用户 spec 明确授权）：Phase 5 改 `recommendation` 3 个文件（输入契约 + 三态约束护栏），Phase 6 改 `report-generation` 输入契约、适配器、引擎与规则（新增 canonical 章节 + 渲染修复）。两者均**未改写既有评估语义**——各自 legacy 数据集全部保持通过。详见 `docs/architecture/product-recommendation-v2.md` / `docs/architecture/report-generation-v2.md`。

### 5.4 Evidence Provider（Phase 4）

Knowledge Search 已固化为**共享 Evidence Provider**，原子操作是 `Skill → Evidence Request → Knowledge Search → Skill`，而非 workflow 里写死的一步。详见 `docs/architecture/evidence-provider.md`。

- `knowledge/evidence/request.py`：请求侧，把任意 Skill 的需要转成规范 `KnowledgeQuery`。**查询由 `(domain, purpose)` 模板生成，不接受调用方自由文本**（防注入 + 防幻觉 + 可测）。
- `knowledge/evidence/provider.py`：供给侧，`KnowledgeQuery → knowledge-search 引擎 → 规范 KnowledgeEvidence`，双向契约校验。
- `knowledge/evidence/loop.py`：受控回环，返回 `source_unchanged` 证明**只读消费**。
- 硬边界：Evidence≠Recommendation、诚实弃权、冲突透传、只读回环、不重造检索。

### 5.5 契约演进记录（Phase 3）
`solution-plan.schema.json` 在实现 `solution` Skill 时做了一次**纯增量**修订（既有 required 字段与类型全部保持不变，旧消费者不受影响）：

- 新增 `payload.solutions[]`：每个 Gap 一条策略（`solution_id` / `solution_type` / `objective` / `coverage_direction` / `priority` / `constraints` / `trade_offs` / `rejected_directions` / `related_gap_ids` / `related_risk_ids` / `confidence` / `evidence_refs`），`additionalProperties: false`。
- 新增 `payload.information_gaps[]`：覆盖未知、策略暂不能定稿的 Gap。
- 顶层 `objective` / `coverage_direction` / `priority` / `solution_type` 明确为**由 `solutions[0]` 派生**（契约描述中写死，避免双写漂移）。

原因：实现时发现单一策略无法表达"N 个 Gap → N 条策略"这一真实语义（`related_gap_ids` 原本是数组已隐含此意）。契约先于实现、并随实现补齐声明，符合 Contract First——但**不允许隐式字段**，故同步写入契约而非只写代码。

---

## 6. 如何运行

```bash
# 生成真实 legacy 样本（从既有数据集/引擎抽取）
python tests/contracts/_gen_fixtures.py

# 运行 9 份契约测试
python tests/contracts/run_contract_tests.py

# 运行 3 个 Python 既有 eval 回归
python tests/contracts/_run_py_evals.py

# Phase 2：coverage-gap-analysis
python .trae/skills/coverage-gap-analysis/scripts/run_coverage_gap_dataset.py
python .trae/skills/coverage-gap-analysis/scripts/test_coverage_gap.py

# Phase 3：solution（策略层）
python .trae/skills/solution/scripts/run_solution_dataset.py
python .trae/skills/solution/scripts/test_solution.py
python .trae/skills/solution/scripts/invoke-solution.py --input <composite.json>

# Phase 4：共享 Evidence Provider
python tests/evidence/run_evidence_dataset.py
python tests/evidence/test_evidence_invariants.py

# Phase 5：product-recommendation V2（根治 P1）
python .trae/skills/recommendation/scripts/run_product_recommendation_dataset.py
python .trae/skills/recommendation/scripts/test_product_recommendation_v2.py

# Phase 6：report-generation V2（8 Artifact 输入）
python .trae/skills/report-generation/scripts/run_report_v2_dataset.py
python .trae/skills/report-generation/scripts/test_report_v2.py

# Phase 7：CaseState + Orchestrator + E2E
python tests/e2e/_gen_e2e_fixture.py
python tests/e2e/run_e2e.py
python tests/e2e/test_orchestration_invariants.py
```

---

## 7. Phase 3 完成结论

Phase 3 已按用户评审的三条边界修正中的**修改 2**落地：`solution` 新建 Skill 完成。

- **定位**：CoverageGapAnalysis（权威驱动）+ RequirementAnalysis（约束）+ RiskAssessment（仅引用）→ SolutionPlan。
- **语义落点**：`Risk（可能出什么问题）→ Coverage Gap（现在缺什么）→ Solution（应采用什么解决策略）→ Product（哪些产品实现策略）`。
- **禁项已强制**：输出不含具体产品名 / 保险公司名。结构性防线是**全部文本来自规则模板**（引擎无自由文本入口），第二道防线是 `forbidden_terms` 扫描；负向探针已验证两道防线均会真实触发（注入品牌词 / 注入自定义 direction 均被检出，基线 0 命中）。
- **层间不泄漏**：不重算 `severity` / `likelihood` / `residual_risk`；`priority` 由 **gap_level** 推导而非继承 risk priority；`coverage_direction` 逐条比对规则模板，杜绝编造。
- **验证**：9/9 契约测试、5 case 数据集、9 项架构不变量单测全绿；3 个既有 Python eval 无回归；`git diff` 为空。

---

## 8. Phase 4 完成结论

Phase 4 已按用户评审的**修改 3**落地：Knowledge Search 固化为共享 Evidence Provider。

- **形态**：`Skill → Evidence Request → Knowledge Search → Skill` 受控回环，而非写死的 Step 6。已从 `solution` 与 `coverage-gap-analysis` 两侧各发起过真实回环。
- **查询模板化**：`query` 是 `(domain, purpose)` 的纯函数，不接受调用方自由文本；具体性来自 domain+purpose，可追溯性来自 `related_artifact_ids`，二者分离。
- **只读**：回环返回 `source_unchanged`，证明请求方 Artifact 未被修改（只读消费）。
- **不重造检索**：`knowledge/evidence/provider.py` 加载并调用 knowledge-search 的既有入口；`knowledge-search` 0 文件被修改。
- **验证**：契约测试 9/9（knowledge-query / knowledge-evidence 已改为跑真实 provider）；evidence 数据集 5/5；7 项架构不变量全绿；3 项负向探针 **GUARDS LIVE**；6 个数据集回归全绿；`git diff` 为空。

---

## 9. Phase 5 完成结论

Phase 5 根治了 Phase 0 审计的 **P1（致命）**：`candidate_solutions` 无生产者。

- **根治方式**：不新增 `candidate-solutions` Skill，而是让 `SolutionPlan` 成为
  candidate solution 的 Canonical 来源；`solution_to_candidates.py` 在显式适配器边界上派生候选。
- **护栏可机检**：V2 输入契约用 `not: {required: [candidate_solutions]}` 禁止该字段作为输入。
- **诚实边界**：`premium` / `term` / `insurer` / `product_name` 刻意缺省，绝不从策略推导；
  `liquidity_impact` 一律 `unknown`。
- **顺带修掉一个真实缺陷**：原实现在候选缺 `premium` 时会把 budget 记成「通过」并输出
  `within_budget`。现改为三态 **violation / pass / unverifiable**；不可验证既不阻断入选，
  也不降级为 `INCOMPLETE_EVIDENCE`，而是转为 `constraint_unverifiable` 并强制人工复核。
- **验证**：12/12 套件全绿（含 LEGACY 11 case 回归 + V2 5 case + 10 项不变量 + 9/9 契约测试）；
  负向探针 3/3 GUARDS LIVE。
- **改动范围**：仅 `recommendation` 的 3 个文件（+52 / -8），评估逻辑未重写。
  详见 `docs/architecture/product-recommendation-v2.md`。

---

## 10. Phase 6 完成结论

`report-generation` 的输入从 5 路 legacy 输出扩展为 **7 路 Canonical Artifact + legacy 别名**，
并保持「不拥有业务判断权」的硬边界（只 collect / normalize / render / validate）。

- **04 章节 canonical-first**：提供 `CoverageGapAnalysis` 时它是 04 的**唯一**来源并逐条照搬，
  风险推导条目被抑制，`derivation="canonical"`；缺失时回退推导并打
  `GAP_SOURCE_DERIVED_NOT_CANONICAL` 警告，`derivation="derived"`。两条路径永不可混淆。
- **06A 解决策略**：逐条照搬 `SolutionPlan`（含 constraints / trade_offs / rejected_directions），
  报告不转述策略——转述会让一条策略悄悄变成另一条策略。
- **附录 A 证据来源**：逐条列示 `KnowledgeEvidence`，含 conflict 标记；报告**不称量**证据。
- **跨 Artifact 冲突**：缺口判定与风险记载不一致时**呈现而非裁决**（`v2_gap_vs_risk_conflict`）。
- **顺带修掉一个渲染缺陷**：策略块曾把 `constraints / trade_offs / rejected_directions`
  渲染成 Python dict 字面量。已改为按契约字段做字段感知渲染，并修正 `匹配度` 一栏
  （`fit` 取 fit-label 而非状态枚举）。新增外置 `fit_names`。
- **验证**：legacy 8 例 + V2 6 例 + 10 项架构不变量全绿；契约测试 9/9；
  负向探针 **5/5 LIVE**。
- **改动范围**：`report-generation` 的 input/output schema、适配器、引擎、规则、SKILL.md/CONTRACT.md，
  以及新增的 V2 数据集与不变量单测。既有评估语义未改写（legacy 8 例保持通过）。
  详见 `docs/architecture/report-generation-v2.md`。

---

## 11. Phase 7 完成结论

Phase 7 把 8 个 Specialist Skill 串成**可一键运行、带状态与人工复核闸门**的完整链路。

- **State（`runtime/state/`）**：`CaseState` 是一个客户的**唯一事实源**；三不变量可机检——
  **单调性**（`NON_MONOTONIC`）· **前置条件**（`MISSING_INPUT_ARTIFACT` / `INPUT_NOT_RELEASED`）·
  **冻结**（sha256 指纹，`ARTIFACT_MUTATION`）。持久化为 `<case>/case_state.json` + 逐份 Artifact。
- **Workflow（`runtime/insurance-analysis.yaml`）**：**声明式、单一真源**。7 个线性 stage
  （`client-intake → requirement-analysis → risk-analysis → coverage-gap-analysis → solution →
  product-recommendation → report-generation`）+ 1 个非线性 `knowledge-search` **service**。
  输入键/形状（`input_map`）与适配器边界（`post_adapter`）**显式声明**，杜绝隐式字段耦合。
- **Orchestrator**：`provided` stage 由 seed 注入并记 `provided_by`（**不假装跑过、无 seed 即
  `BLOCKED`**）；`python` stage 导入 Skill 自己声明的入口调用；代 stage 发起 Evidence 回环；
  产物逐一校验 Canonical Contract；在人工闸门处 `PAUSED_NEEDS_REVIEW`，批准后续跑。
- **Knowledge Search 保持共享 Provider 语义**（非 Step 6）：探针 P5 通过「把它加成 stage 使形状检查
  失败」反向证明该约束真实生效。
- **验证**：E2E **36/36**（闸门暂停→批准→续跑、8 个 Artifact 契约校验、只读回环、冻结拒写、
  持久化逐字节相等）；编排不变量 + 负向探针 **21/21**；**全工程 17/17 套件 GREEN**；
  **Phase 7 对既有 Skill 0 修改**。
  详见 `docs/architecture/orchestration.md`。

**V2.0 骨架至此闭环**：`contracts/ · adapters/ · skills/ · evidence/ · state/ · workflow/ · tests/`。

---

## 12. 下一步（Phase 8 / V2.1，已完成）

1. **`domain/insurance` Domain Pack**（pack / playbook / references / overlays）—— 按 Phase 1 评审
   **暂缓**至 8 Skill 跑稳之后；现条件已满足，于 **Phase 8** 落地（详见 `docs/architecture/domain-pack.md`）。
   - `pack.yaml` 中心化险种分类（含 `critical_illness ↔ critical` 别名映射）、evidence_types、source_levels、overlay 策略、rag_seed 配置。
   - `references/` 7 份带版本化标记的权威语料，可被 `rag.store` 摄取为生产知识库（`seed_rag.py` → 49 chunks）。
   - `validate_pack.py` 59/59 GREEN（taxonomy 与 `rag.PRODUCT_BY_PREFIX` / `evidence-request` 对齐、overlay 不泄漏、检索冒烟）。
   - `overlays/` 默认空（符合 AGENTS.md §8）。
2. 可选加固：把各 Skill 的 `evals/cases/_*_log.txt` 运行产物统一移出 `evals/cases/`（现与历史
   Phase 一致，仅提示）。
3. 可选：为 `requirements.txt` / `pyproject.toml` 固化 Python 依赖（本阶段新增 `PyYAML`）。

**Phase 8 已 STOP，未自动进入后续阶段。**
