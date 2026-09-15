# Insurance Agent System

> 一个面向保险顾问的 Agent System：**从客户信息开始**，自主完成需求分析、风险识别、保障缺口分析、
> 解决策略、知识检索、产品候选与推荐，并通过 **Artifact Lineage / Evidence Provenance /
> Deterministic Eval / Repair Loop / Checkpoint** 保证过程可追踪、结果可验证、失败可恢复。

不是「几个 Skill 的集合」，而是一套**可验证、可修复、可恢复**的 Agent 运行时。

---

## 目录

1. [Problem](#1-problem)
2. [Architecture](#2-architecture)
3. [Skill Graph](#3-skill-graph)
4. [CaseState](#4-casestate)
5. [Artifact / Lineage](#5-artifact--lineage)
6. [Evidence / RAG](#6-evidence--rag)
7. [Product Candidate](#7-product-candidate)
8. [Orchestrator](#8-orchestrator)
9. [Eval](#9-eval)
10. [Repair](#10-repair)
11. [Checkpoint / Resume](#11-checkpoint--resume)
12. [Benchmark](#12-benchmark)
13. [Demo](#13-demo)
14. [Limitations](#14-limitations)
15. [为什么这么设计](#15-为什么这么设计)
16. [快速开始](#16-快速开始)
17. [项目结构](#17-项目结构)

---

## 1. Problem

保险顾问的判断链长且后果重：客户说了什么（事实）→ 想解决什么（需求）→ 暴露什么风险 →
现有保障缺什么（缺口）→ 该用什么策略 → 有哪些够格的产品 → 推荐哪个 → 报告。

用一个大模型 Prompt 一把梭会产生三个致命问题：

| 问题 | 后果 |
|---|---|
| **幻觉** | 编造产品、编造条款、编造客户信息，且看上去合理 |
| **不可追溯** | 给出推荐却说不清依据，无法复核 |
| **静默失败** | 信息不足时仍强行给出结论，把推测写成事实 |

本项目要证明的是：**能不能把这件事做对一个可信系统** —— 每一层有契约、每个结论有出处、
每次失败有分类、每次中断可恢复、每次修改可回归。

---

## 2. Architecture

```text
                              Customer
                                 │
                                 ▼
                        ┌──────────────────┐
                        │   Orchestrator   │  ← 唯一运行时循环（无业务判断）
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │     CaseState    │  ← 跨 Skill 唯一事实源
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │   Skill Graph    │  ← 8 层，每层一个 Canonical Artifact
                        └────────┬─────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
  Business Skills          Evidence / RAG            Product Catalog
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 ▼
                            Artifacts
                                 │
                                 ▼
                           Eval (确定性)
                          ↙            ↘
                       PASS            FAIL
                        │                │
                        │             Repair → Rerun
                        └───────┬────────┘
                                ▼
                           Checkpoint
                                │
                                ▼
                             Report
                                │
                                ▼
                     Benchmark / Trace / Demo
```

**执行方式**：`Deterministic`（规则引擎）/ `LLM`（对话式上游，artifact 注入）/
`RAG`（共享 Evidence Provider）/ `External Data`（demo catalog，可替换）。
完整图与标记见 **`docs/architecture/architecture.md`**。

---

## 3. Skill Graph

```text
FACT ─► REQUIREMENT ─► RISK ─► GAP ─► SOLUTION ─► PRODUCT ─► REPORT
```

| # | Skill | 回答的问题 | 产物 | 执行 |
|---|---|---|---|---|
| 01 | client-intake | 客户有哪些**事实**？ | ClientProfile | LLM |
| 02 | requirement-analysis | 想解决什么**问题**？ | RequirementAnalysis | LLM |
| 03 | risk-analysis | 暴露什么**风险**？ | RiskAssessment | LLM |
| 04 | coverage-gap-analysis | 现有保障哪里**不足**？ | CoverageGapAnalysis | Deterministic |
| 05 | solution | 应采什么**解决策略**？ | SolutionPlan | Deterministic |
| — | knowledge-search | 提供什么**证据**？ | KnowledgeEvidence | RAG（共享服务） |
| 06 | product-candidate-provider | 哪些产品**够格**？ | ProductCandidates | Deterministic |
| 07 | product-recommendation | 用哪些**产品**实现策略？ | ProductRecommendation | Deterministic |
| 08 | report-generation | 汇总 / 归一化 / 渲染 | InsuranceReport | Deterministic |

**四层语义严格区分**（最易混淆处）：

```text
Requirement Gap Hint  ≠  Coverage Gap  ≠  Solution  ≠  Product Recommendation
（客户自述缺什么）        （正式缺口判断）  （解决策略）    （具体产品）
```

> 缺口层**不携带任何金额字段**；策略层**禁止出现产品名 / 公司名**；候选层**只生成不排序**。
> 详细职责边界见 `docs/architecture/architecture-v2.md`。

---

## 4. CaseState

**一个客户 = 一个 CaseState**，是所有 Skill 的共享黑板（`runtime/state/case_state.py`）：

```text
artifacts{}          各层 Canonical Artifact
artifact_registry{}  血缘 + 指纹（ART-ID / produced_by / input_artifacts / evidence_refs）
tasks[]              执行台账（PENDING/RUNNING/PASS/FAIL/REPAIRING/NEEDS_REVIEW/SKIPPED）
evaluations[]        Eval 记录
checkpoints[]        检查点
services{}           Evidence Provider 调用计数
events[]            原始事件日志
trace[]             结构化 Execution Trace（Step 4 Phase 2）
status / waiting_for_user / review
```

**三不变量**（`runtime/state/transitions.py`，可机检）：

| 不变量 | 反例即报 |
|---|---|
| **单调性** | 阶段只能向前，回退 → `NON_MONOTONIC` |
| **前置条件** | 生产该 artifact 的 stage 尚未 `COMPLETED` → `MISSING_INPUT_ARTIFACT` / `INPUT_NOT_RELEASED` |
| **冻结** | 已发布 artifact 被改（sha256 不符）→ `ARTIFACT_MUTATION` |

> **UNKNOWN 是独立第三态**：信息缺失 ≠ 事实为假。把 UNKNOWN 折进 PASS 是伪造通过，因此
> `value_status=UNKNOWN` 绝不写入 `answered_fields`（否则追问引擎会静默跳过阻塞项）。

---

## 5. Artifact / Lineage

每个产出物注册为带血缘的 Artifact：

```text
ART-007 (product-recommendation)
  produced_by: product-recommendation
  input_artifacts: [ART-002, ART-003, ART-004, ART-005]
  evidence_refs: [EV-xxx]
  fingerprint: <sha256>
```

- 注册表**只存元数据**，内容在 `state["artifacts"]`，可单文件 diff。
- `lineage()` 可回溯到客户事实；`verify()` 按 fingerprint 防篡改。
- 这条链直接支撑报告里的 **Provenance**：`Recommendation → Product → Evidence → Document → Chunk`。

---

## 6. Evidence / RAG

```text
Product Attribute ─► Evidence Requirement ─► Evidence Chunk ─► SUPPORTED / UNSUPPORTED / CONFLICT
```

- **共享 Evidence Provider**（`evidence/` + `rag/`）：查询由 `(domain, purpose)` 模板生成，
  回环只读（`source_unchanged`）。`knowledge-search` **不是 stage**，是任意 stage 可按需请求的服务。
- **属性级 grounding（V0.2）**：5 个关键属性逐条对照证据 —— `coverage_type / eligibility_age /
  renewal_period / deductible / coverage_term`，给出 `SUPPORTED / UNSUPPORTED / CONFLICT / NOT_CHECKABLE`。
- **NOT_CHECKABLE 是独立第三态**，绝不折成 SUPPORTED。
- 无证据的产品**不得**作为「有依据的推荐」（`EVIDENCE_MISSING` / `EVIDENCE_UNSUPPORTED`）。

> 关键教训：仅凭 `domain = medical` **不足以**认为证据足够 —— 必须落到「哪个属性被哪条 chunk 支持」。
> 设计取舍见 `docs/adr/ADR-005-evidence-provenance.md`。

---

## 7. Product Candidate

```text
Product Catalog ─► Product Candidate Provider ─► ProductCandidates ─► Recommendation
   (demo, 版本化)      (只生成，不排序)              (带原因码)         (只选择)
```

- Catalog：12 个结构化 demo 产品（`is_demo=true`），带 `catalog_version / product_version /
  effective_from / effective_to` —— 历史 Case 可还原「当时为什么推荐它」。
- Candidate Provider 做四类确定性判定：**类型 / 方向 / 资格 / 证据**，输出 `admissible` 与原因码
  （`ELIGIBILITY_INELIGIBLE` / `EVIDENCE_MISSING` / `EVIDENCE_UNSUPPORTED` / …），**不排序、不选主推**。
- Recommendation 硬拒未通过产品校验者，三态明确：`COMPLETE / INCOMPLETE_EVIDENCE / NO_CANDIDATES`。

> **生成与选择必须分离** —— 不允许同一环节「想产品 → 生成产品 → 推荐产品」（自我认证）。
> 见 `docs/adr/ADR-006-candidate-recommendation-separation.md`。

---

## 8. Orchestrator

`runtime/orchestrator.py` 是唯一运行时循环，**不含任何保险业务判断**；行为由
`runtime/insurance-analysis.yaml`（声明式单一真源）驱动。

```text
next_runnable ─► run stage ─► Eval
                                ├─ PASS ─► 下一 stage（或 gate 停）
                                └─ FAIL ─► Repair ─► Rerun（≤ max_attempts）
                                              └─ 耗尽 ─► NEEDS_REVIEW / WAITING_FOR_USER
```

- `executor: provided`（对话式上游）由 `seed_case()` 注入并记 `provided_by`；
  **没有 seed → `BLOCKED`，绝不编造**。
- **闸门是真实停点**：gate `stop` → `PAUSED_NEEDS_REVIEW`，`next_runnable` 仍指向被闸 stage，
  **重试不可绕过**，必须显式 `approve()`。
- `input_map` 显式声明各 Skill 入口键名 / 形状（`{artifact_type: {key, shape}}`），**不靠约定**。

---

## 9. Eval

**独立于 Skill 的确定性引擎**（`runtime/eval_engine.py`），6 类机器可判检查：

| 检查 | 抓什么 |
|---|---|
| `schema` | 结构不合法 |
| `required_fields` / `required_non_empty` | 必填缺失 / 空 |
| `contamination` | 上游越界（如缺口层出现金额、策略层出现产品名） |
| `provenance` | 结论引用了不存在的证据 |
| `cross_artifact` | 跨层引用悬空（如 `risk_id` 不存在） |
| `invariant` | 业务不变量（如产品必须存在于 Catalog） |

**红线**：无法评估的检查一律记 `FAIL`，**绝不** `MANUAL/UNKNOWN` 通过（回归集显式断言「无 MANUAL 通过」）。

---

## 10. Repair

`runtime/repair.py` 把失败检查映射到动作：

| 动作 | 适用 |
|---|---|
| `RERUN_FROM_UPSTREAM` | 上游输入导致（如缺证据 → 重取） |
| `DROP_INVALID_PRODUCTS` | 候选含非法产品 |

- Repair **只改 stage 的输入**，绝不改已冻结的 artifact（派生量算错 → AUTO；事实或立场有问题 → REVIEW）。
- 预算 `max_attempts=3`（1 初始 + 2 repair）——**是上限不是配额**，耗尽即 `NEEDS_REVIEW`。
- 绝不发明事实、绝不清洗立场。

---

## 11. Checkpoint / Resume

- **保存**：每阶段 OK/GATE/NEEDS_REVIEW 后落盘（`case_state.json` + `checkpoints[]`）。
- **校验后信任**：`load()` 做 5 项校验（存在/可解析、`case_id` 匹配、schema 合法、
  registry fingerprint 一致、task→stage 引用完整）。**任一失败即 `CHECKPOINT_INVALID`，绝不静默续跑**。
- **Resume** 只重跑未 PASS 的 task，并**报告**被重跑的 PASSed task（正常应为空）。
- **WAITING_FOR_USER**：信息不足 / 冲突时停下并给出 `next_questions`，不猜。

---

## 12. Benchmark

`evals/agent-benchmark/` —— 回答「Agent 能不能把真实客户案例处理**正确**」，而非「代码能不能跑」。

**33 个合成 / 匿名 Case**，全部是对已验证全链种子的变异；上游 seed 注入，下游**真实执行、评估、修复、落盘**。
覆盖：`complete(7) / insufficient_information(5) / conflicting_information(5) / low_risk(3) /
high_risk(3) / no_candidates(3) / insufficient_evidence(3) / adversarial(3) / repairable(1)`。

### Agent-Level Metrics（**全部来自真实运行**，`evals/agent-benchmark/baseline.json`）

| Metric | Value | 目标 |
|---|---|---|
| Task Success Rate | **100.0%** (33/33) | 越高越好 |
| Product Hallucination Rate | **0.0%** | **0（硬门）** |
| Provenance Completeness | **100.0%** | 越高越好 |
| Invalid Continuation Rate | **0.0%** | **0（硬门）** |
| Unsupported Claim Rate | **0.0%** | 越低越好 |
| Repair Success (repairable only) | **100.0%** (1/1) | 反映修复真实能力 |
| Human Review Rate | 21.2% | 人工介入占比 |

### Safety Hard Gates（§11：不用一个总分掩盖风险）

| Gate | Result |
|---|---|
| product_hallucination_zero | **PASS** |
| critical_provenance_failure_zero | **PASS** |
| invalid_continuation_zero | **PASS** |

> **不追求单一总分**。保险是高风险决策场景，有意义的是安全 / 正确性硬门 —— 任一违反即 FAIL。

### Golden Cases（`evals/agent-benchmark/golden.json`）

9 个 Golden Case，断言**行为与约束**而非固定答案（必须发现某类风险 / 必须发现缺口 /
不得推荐不合格产品 / 必须有证据 / 必须保留 provenance）。
Regression 门禁（`run_golden_cases.py`）支持 Before/After 对比，并留存基线。

---

## 13. Demo

```bash
# Demo A：完整案例（单一需求）→ 真正落到一个具体产品 → 推荐 + 报告（含 DEMO 产品标记）
python demo.py demo-a

# Demo B：故意让证据不足（知识库为空）→ Eval FAIL → Repair → 仍失败 → NEEDS_REVIEW（失败可解释）
python demo.py demo-b

# Demo C：多需求完整客户 → 策略层覆盖 5 个领域，但没有单一产品能覆盖全部 → 诚实呈现，不硬推
python demo.py demo-c

python demo.py --list    # 列出所有可用 case
```

Demo 实时流式显示每一步 `[n/9] Skill ✓`、当前 artifact、Eval 判定、Repair 尝试与最终结果，
并落盘 `trace.jsonl`（结构化）+ `trace.md`（人读视图）。

**Trace 能回答「为什么这个 Case 最终没有推荐产品」**，例如：

```text
Client Intake       PASS
Requirement         PASS
Risk                PASS
Coverage Gap        PASS
Solution            PASS
Knowledge Search    INSUFFICIENT
Repair #1           FAIL
Repair #2           FAIL
Product Candidate   BLOCKED
Recommendation      SKIPPED
Case                NEEDS_REVIEW
```

这比单纯打印 `ERROR` 有价值得多。事件类型与字段见 `docs/architecture/execution-trace.md`。

---

## 14. Limitations

诚实清单（未解决 / 有意不做）：

1. **Product Catalog 是 demo 数据**（12 个产品，`is_demo=true`）。通过 Product Provider 抽象隔离，
   接真实库无需改 Recommendation —— 但**尚未接真实产品 API**。
2. **属性级 grounding 只覆盖 5 个属性**，且匹配是「声明值可搜索变体命中」的字符串级判定，
   不是语义蕴含 —— 会漏判（假阴性），故**不确定时判 NOT_CHECKABLE / UNSUPPORTED，不判 SUPPORTED**。
3. **`product-candidates` 尚无 Canonical 契约**（仍为 Skill 级 schema），是 Step 2 遗留技术债。
4. **上游三 stage 是 `provided`**（对话式产出，本仓库不内置模型调用）；E2E 从
   `client-profile` 这一可信 artifact 开始，不覆盖「原始对话 → profile」的 intake 本身。
5. **`repair_success_rate` 的分母含故意不可修复的注入故障**，故原始值偏低（9.1%）；
   真实能力应看 `repairable only = 100%`。
6. **Eval 不做主观判断**（语气是否推销、表述是否易懂）—— 有意留白。
7. **无并发 / 多租户 / 持久化数据库**：当前一个客户 = 一个 CaseState + 文件系统落盘。

---

## 15. 为什么这么设计

> 这部分是「Agent 工程」比「会写 Skill」更有价值的部分。

**Q：为什么 Skill 不直接调用下一个 Skill？**
直接调用会把「谁需要什么」烧死在代码里，改一处牵动全链。改由 Orchestrator 读声明式 YAML 决定，
新增 / 调序不动 Skill。

**Q：为什么需要 Orchestrator？**
需要一个**无业务判断**的中枢，只做四件事：搬运 artifact、校验契约、强制顺序、在闸门停下。
把编排（跨领域关注点）与保险判断（领域关注点）彻底解耦。

**Q：为什么需要 Artifact？**
层间靠**结构化契约**而非自由文本协作，才可校验、可 diff、可回溯。否则「上一层说了什么」无法机检。

**Q：为什么 Eval 独立于 Skill？**
被检查方自己批卷不可信。校验必须由**不产出该结果**的组件执行，才具备反证能力。

**Q：为什么 Evidence 必须有 provenance？**
保险结论若无 `document/chunk` 溯源即为幻觉。属性级 grounding 进一步回答
「这个产品声称某属性，哪条证据支持它」——没有则 UNSUPPORTED。

**Q：为什么 Product Candidate 和 Recommendation 分离？**
生成与选择分离，避免「自己造产品 → 自己推荐」的自我认证；同时让
`product_hallucination_rate` 成为可测硬门（目标 0）。

**Q：为什么 UNKNOWN 不能当 FALSE？**
信息缺失 ≠ 事实为假。把 UNKNOWN 折进 PASS 是**伪造通过** —— 这条规则此前真实触发过缺陷
（`value_status=UNKNOWN` 曾写入 `answered_fields`，导致追问引擎静默跳过阻塞项）。

**Q：为什么失败后不是无限 Retry？**
重试预算是**上限不是配额**。反复重试同一个必然失败的输入只会放大成本且掩盖根因；
耗尽即转 `NEEDS_REVIEW`，把判断交回人。

更多设计决策见 `docs/adr/`（ADR-001 … ADR-007）。

---

## 16. 快速开始

### 环境
- Python 3.11+（无第三方运行时依赖；`PyYAML` 供编排层读取 workflow 定义）
- 仓库根即运行根，无安装步骤

### 跑 Demo
```bash
python demo.py demo-a        # 完整链路
python demo.py demo-b        # 失败 + Repair 路径
```

### 跑 Benchmark / Golden
```bash
python evals/agent-benchmark/run_agent_benchmark.py            # 33 cases + 指标 + 硬门
python evals/agent-benchmark/run_agent_benchmark.py --write-baseline
python evals/agent-benchmark/run_golden_cases.py               # 9 golden + before/after 门禁
```

### 跑回归（全量）
```bash
python tmp/run_regression.py     # 一次性跑全部套件并汇总
```

### 逐套件
```bash
python test-cases/e2e/full-agent/run_full_agent_e2e.py                 # 全链路 71 检查
python test-cases/e2e/product-recommendation/run_product_recommendation_e2e.py  # Step2 61 检查
python tests/contracts/run_contract_tests.py                           # 9 份契约
python tests/workflow/test_step3_mutation.py                           # 反橡皮图章变异
python tests/workflow/test_step3_orchestrator_self_eval.py             # 编排自评
python tests/workflow/test_step4_phase2_trace.py                       # Execution Trace
python tests/workflow/test_step4_phase7_evidence_grounding.py          # 属性级 grounding
python tests/workflow/test_step4_phase8_catalog_version.py             # Catalog 版本化
python tests/workflow/test_step4_phase9_observability.py               # Observability
python tests/workflow/test_step4_phase13_guardrails.py                 # Safety Guardrails
```

---

## 17. Repository Structure

| 目录 | 职责 |
|---|---|
| `runtime/` | Agent Runtime：orchestrator / eval_engine / repair / checkpoint / trace / observability / state + 声明式工作流 |
| `.trae/skills/` | 9 个 Specialist Skill（各带 eval 数据集与外置规则表；`client-intake`、`requirement_analysis` 为冻结 Skill） |
| `domain/insurance/` | Insurance Domain Pack：险种分类 / 证据等级 / RAG 权威语料 |
| `knowledge/` | RAG 引擎（sqlite）+ Evidence Provider（grounding / 回环检索） |
| `contracts/` · `adapters/` · `catalog/` | 9 份 Canonical Artifact 契约 · legacy→canonical 适配器 · 版本化产品目录 |
| `tests/` · `test-cases/` | 契约 / 变异 / 工作流单测 · E2E 场景数据集 |
| `evals/` | System-level Benchmark + Golden Cases（区别于 Skill-level evals，见 `evals/README.md`） |
| `docs/` | architecture / adr / dev-notes / archive（目录契约详见 `docs/repository-structure.md`） |
| `demo.py` | Demo CLI：A 完整推荐 / B 证据不足→NEEDS_REVIEW / C 多需求策略层 |

结构不变量由 `python tests/structure/test_structure_integrity.py` 守护。

---

## 文档导航

| 想了解 | 读 |
|---|---|
| 架构总览 + 执行方式标记 | `docs/architecture/architecture.md` |
| 设计决策与取舍 | `docs/adr/` |
| 契约层与 legacy 映射 | `docs/architecture/contract-layer.md` |
| 编排 / CaseState / 闸门 | `docs/architecture/orchestration.md` |
| Execution Trace 与事件类型 | `docs/architecture/execution-trace.md` |
| 失败分类 F1–F12 + 处理矩阵 | `docs/architecture/failure-taxonomy.md` |
| Evidence Provider | `docs/architecture/evidence-provider.md` |
| 产品候选 / 推荐分离 | `docs/architecture/product-recommendation-v2.md` |
| 目标架构与四层语义 | `docs/architecture/architecture-v2.md` |
| 命名规范与纪律 | `AGENTS.md` |
