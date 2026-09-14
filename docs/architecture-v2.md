# 保险 Agent V2 — 目标架构（演进基线）

> 本文件是 V2 的**目标架构**设计文档，随 Phase 推进持续更新。
> Phase 0 审计基线：`docs/architecture-v2-audit.md`（只读，不修改）。
> Phase 1 契约层落地：`docs/contract-layer.md`。
>
> 本架构已吸收用户在 Phase 1 评审中的 **3 个边界修正** + **暂缓 domain/insurance** 决策。

---

## 1. 设计哲学：Contract-first Agent Architecture

```
                 ┌───────────────────────────────┐
                 │          Orchestrator         │
                 └───────────────┬───────────────┘
                                 │  (workflow/insurance-analysis.yaml + state/CaseState)
                                 ▼
   Client Intake ──► Requirement ──► Risk ──► Coverage Gap ──► Solution ──► Product ──► Report
                                 ▲                                      │
                                 └────────── Knowledge Search ◄──────────┘
                                           (共享 Evidence Provider，按需回环)

   横向贯穿： Contract · Provenance · Evidence · Eval · State · Human Review
```

核心主张：**多个 Specialist Skill 通过结构化 Artifact（Canonical Contract）协作**，并用 Provenance / Evidence / Eval / State / Orchestration 控制整条决策链——而非“写几个 Skill”。

---

## 2. 8 个 Skill 与职责边界

| # | Canonical Skill | Legacy 目录 | 核心回答 | 产物 Artifact | 状态 |
|---|---|---|---|---|---|
| 01 | client-intake | client-intake | 客户有哪些**事实**？ | ClientProfile | 稳定，不重写 |
| 02 | requirement-analysis | requirement_analysis | 客户想解决什么**问题**？ | RequirementAnalysis | 稳定，不重写（仅 adapter） |
| 03 | risk-analysis | risk-analysis | 客户暴露什么**风险**？ | RiskAssessment | 稳定，不重写 |
| 04 | coverage-gap-analysis | coverage-gap-analysis | 现有保障哪里**不足**？ | CoverageGapAnalysis | **Phase 2 已完成**（独立判断层，Risk≠Gap） |
| 05 | solution | solution | 应采什么**解决策略**？ | SolutionPlan | **Phase 3 已完成**（策略层，Solution≠Product） |
| 06 | knowledge-search | knowledge-search | 提供**证据** | KnowledgeEvidence / KnowledgeQuery | 稳定，重定位为共享 Provider |
| 07 | product-recommendation | recommendation | 哪些**产品**实现策略？ | ProductRecommendation | **Phase 5 完成**：输入改为消费 SolutionPlan，根治 P1 |
| 08 | report-generation | report-generation | 汇总 / 归一化 / 渲染 | InsuranceReport | **Phase 6 已完成**（7 路 Canonical 输入 + legacy 别名；04 canonical-first；策略块 + 证据附录） |

数据链（单向，不可倒流）：`FACT → REQUIREMENT → RISK → GAP → SOLUTION → PRODUCT`

---

## 3. 三个关键边界（用户评审修正）

### 3.1 Coverage Gap = 独立业务判断层（不是 Risk 的字段拆解）
- `risk-analysis` 回答“这个家庭有哪些风险？”（severity/likelihood/residual/priority）。
- `coverage-gap-analysis` 回答“针对这些风险，保障覆盖到什么程度？”（current_coverage / gap_level / target_coverage）。
- **Risk ≠ Coverage Gap**：契约中不复制 severity/likelihood，只引用 `risk_id`。
- `risk-analysis.coverage_assessment` 降级为“风险层辅助判断”，最终缺口结论由 `coverage-gap-analysis` 负责。
- 未来保单体检 / 家庭保障盘点 / 旧保单分析 / 保障额度计算均可挂此层。

### 3.2 Solution = 解决策略（不是产品推荐）
- `SolutionPlan` 只表达 objective / coverage_direction / priority / constraints / trade_offs / rejected_directions，**禁止具体产品名 / 保险公司名**。
- 每层回答清晰：Risk（什么问题）→ Gap（缺什么）→ Solution（什么策略）→ Product（什么产品）。

### 3.3 Knowledge Search = 共享 Evidence Provider（非固定步骤）
- 不写死在 `solution` 之后、product 之前。
- 支持 `Skill → Evidence Request → Knowledge Search → Skill` 受控回环；也可在 Product 阶段“缺某责任证据→回查→继续”。
- 契约：`knowledge-query`（请求，含 purpose / related_artifact_ids）与 `knowledge-evidence`（结果，含 evidence_id / content / source / relevance / confidence / conflict）。
- **Phase 4 已落地**为共享层 `evidence/`（`request.py` / `provider.py` / `loop.py`）；查询由 `(domain, purpose)` 模板生成，回环只读（`source_unchanged`），`knowledge-search` Skill 本身 0 改动。详见 `docs/evidence-provider.md`。

### 3.4 四层语义必须区分（Step 1 验收要求）

```text
Requirement Gap Hint  ≠  Coverage Gap  ≠  Solution  ≠  Product Recommendation
```

| 层 | 载体 | 回答的问题 | 关键约束 |
|---|---|---|---|
| Requirement Gap Hint | `RequirementAnalysis.coverage_gaps` | 客户**自述需求**层面缺什么 | 只是 hint，**不是**最终缺口结论；保留不删除 |
| Coverage Gap | `CoverageGapAnalysis.gaps[]` | 综合 Risk + Requirement + Existing Protection 后的**正式缺口判断** | 独立判断层；**不得**复制 severity/likelihood；**不得**编造金额 |
| Solution | `SolutionPlan.solutions[]` | 应采用什么**解决策略** | 禁止具体产品名 / 保险公司名 |
| Product Recommendation | `ProductRecommendation` | 用哪些**具体产品**实现策略 | Step 2 范围；Step 1 不实现 |

> **禁止把 `RequirementAnalysis.coverage_gaps` 直接复制成最终 Gap。** 需求侧 hint 只是输入之一。

**Coverage Gap 不允许编造金额**：缺口层**不携带任何金额字段**（无 `gap_amount` / `required_coverage` / `protected_amount`）。
无法判断时输出 `current_coverage.status = UNKNOWN` + `payload.status = NEED_MORE_INFORMATION`，
并登记 `information_gaps[]`。宁可 UNKNOWN，不得按年龄/收入/职业/家庭结构猜测客户未提供的金额。

**验证**：`test-cases/e2e/core-analysis/`（3 例：完整客户 / 信息不足 / 信息冲突），
运行 `python test-cases/e2e/core-analysis/run_core_analysis_e2e.py`（41/41）。

---

## 4. 关键断点根治（P1）
`recommendation` 原依赖 `candidate_solutions`，但无生产者。V2 方案：
- `product-recommendation` 直接消费 `SolutionPlan + CoverageGapAnalysis + KnowledgeEvidence`（不再需要独立 `candidate_solutions` 生产者）。
- 该演化在 **Phase 5** 进行，Phase 1 不改 `recommendation` 逻辑，仅在契约层定义未来 `SolutionPlan` 为其 Canonical 候选来源。

### 4.1 Step 2 修正：策略 ≠ 候选（Candidate Provider 的引入）

Phase 5 用 `SolutionPlan → candidate_solutions` 闭合了"无生产者"，但那仍是**策略级占位**：
策略没有产品、保费、期限、投保资格，也没有证据，`recommendation` 实际在对不可能存在于任何
产品库的对象排序。

Step 2 引入独立一层闭合它：

```text
Product Catalog ──► Product Candidate Provider ──► ProductCandidates ──► Recommendation
```

- `catalog/product-catalog.v0.1.json`：12 个**结构化** demo 产品（`is_demo=true`）
- `.trae/skills/product-candidate-provider/`：只做**候选生成**，做类型 / 方向 / 资格 / 证据四类
  确定性判定并打标；**不排序、不选主推**
- `recommendation`：消费真实 Catalog 候选，硬拒任何未通过产品校验者

> 关键纪律：**Candidate Generation 与 Recommendation 必须分离**。
> 不允许同一环节"想产品 → 生成产品 → 推荐产品"。

详见 `docs/step2-evidence-recommendation.md`。

---

## 5. 基础设施演进路线

| 阶段 | 内容 | 状态 |
|---|---|---|
| V2.0 | `skills/`(逻辑名) · `contracts/` · `adapters/` · `evidence/` · `workflow/` · `state/` · `tests/` · `rag/` | **已闭环**（Phase 1–7） |
| V2.1 | `domain/insurance/`（pack / playbook / references / overlays） | **已完成**（Phase 8，详见 docs/domain-pack.md） |
| V2.2 | `catalog/`（Demo Product Catalog）+ `product-candidate-provider` Skill | **已完成**（Step 2，详见 docs/step2-evidence-recommendation.md） |

> 暂缓理由：同时引入 Domain Pack + Overlay + Playbook + References + RAG 会显著抬高工程复杂度；先跑通 Agent 骨架，再抽 Domain Pack。

---

## 6. Phase 进度

| Phase | 范围 | 状态 |
|---|---|---|
| 0 | Architecture Audit（只读） | 完成（docs/architecture-v2-audit.md） |
| 1 | Canonical Contract Layer（9 契约 + 6 adapter + 9 契约测试） | 完成（docs/contract-layer.md）；已 STOP |
| 2 | coverage-gap-analysis 新建 Skill | 完成（9/9 契约测试 + 5 case 数据集 + 架构不变量单测全绿）；已 STOP |
| 3 | solution 新建 Skill | 完成（9/9 契约测试 + 5 case 数据集 + 9 项架构不变量 + 负向探针全绿）；已 STOP |
| 4 | knowledge-search adapter 化（Evidence Provider 接口） | 完成（共享 `evidence/` 层：request/provider/loop；5 例数据集 + 7 项不变量 + 3 项负向探针全绿；knowledge-search 0 改动）；已 STOP |
| 5 | product-recommendation 演化输入契约（根治 P1） | **完成**（docs/product-recommendation-v2.md）；已 STOP |
| 6 | report-generation 输入扩展至 8 Artifact | **完成**（docs/report-generation-v2.md）；已 STOP |
| 7 | case-state（`state/`）+ orchestrator（`workflow/`）+ E2E | **完成**（docs/orchestration.md）；已 STOP |
| 8 | `domain/insurance` Domain Pack（pack / playbook / references / overlays） | **完成**（docs/domain-pack.md）；已 STOP |

> **V2.0 骨架闭环（Phase 7 完成后）**：
> `contracts/ · adapters/ · skills/ · evidence/ · state/ · workflow/ · tests/` 全部就位，
> 8 个 Skill 可由 `workflow/insurance-analysis.yaml` 串成一条带状态与人工闸门的完整链路
> （E2E 36/36、编排不变量+负向探针 21/21、全工程 17/17 套件 GREEN）。
>
> **V2.1 领域包落地（Phase 8 完成后）**：
> `domain/insurance/`（pack / playbook / references / overlays）作为横切共享领域知识层就位，
> 中心化险种分类（`critical_illness ↔ critical` 别名统一）、证据类型与来源等级，
> 并成为 `rag` 的权威生产语料（validate_pack 59/59 GREEN、seed_rag 49 chunks）。
> 详见 `docs/domain-pack.md`。
