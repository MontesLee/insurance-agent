> 🌐 **Language:** 🇺🇸 [English](architecture.md) · 🇨🇳 中文

# 架构总览（Architecture）

> **⚠ 历史文档（V2 时期）。** 写于多 Agent 各阶段之前。当前架构见
> [overview.zh-CN.md](overview.zh-CN.md) 及其兄弟页面；本文件仅作历史保留。
> 注意：文中的 "Phase 7" 指 V2 旧步骤编号（CaseState/Orchestrator），
> 不是现在的 Phase 7 有界并行调度器。


> 面向读者：面试官 / 新协作者。本文回答三件事：**系统长什么样**、**每一层由谁执行**、**为什么这样分层**。
> 配套：`README.md`（入口）、`docs/adr/`（设计决策）、`docs/architecture/orchestration.md`（编排细节）、
> `docs/architecture/execution-trace.md`（可观测）、`docs/architecture/failure-taxonomy.md`（失败分类）。

---

## 1. 一张图

```text
                              Customer
                                 │  (对话 / 表单，executor: provided)
                                 ▼
                        ┌──────────────────┐
                        │   Orchestrator   │  runtime/orchestrator.py
                        │  (唯一运行时循环) │  + runtime/insurance-analysis.yaml（声明式单一真源）
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │     CaseState    │  runtime/state/case_state.py   ← 跨 Skill 唯一事实源
                        │ artifacts/tasks/ │  runtime/state/transitions.py  ← 单调性 / 前置条件 / 冻结
                        │ registry/evals/  │  runtime/artifact_registry.py ← 血缘 + 指纹
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │   Skill Graph    │  8 个 Specialist Skill（每层一个 artifact）
                        └────────┬─────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
  Business Skills          Evidence / RAG            Product Catalog
  (gap/solution/report)    (knowledge-search)        (demo, 版本化)
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 ▼
                            Artifacts
                                 │
                                 ▼
                           Eval (确定性 6 类检查)
                          ↙                        ↘
                       PASS                        FAIL
                        │                            │
                        │                         Repair (局部化重跑)
                        │                            │
                        │                          Rerun
                        └─────────────┬──────────────┘
                                      ▼
                                 Checkpoint  (落盘 + 校验，拒绝从损坏态续跑)
                                      │
                                      ▼
                                   Report
                                      │
                                      ▼
                          Benchmark / Trace / Demo
```

**执行方式标记**（§27 要求）：

| 标记 | 含义 | 具体落点 |
|---|---|---|
| `Deterministic` | 纯规则引擎，同输入必同输出，可单测 | `coverage-gap-analysis` / `solution` / `product-candidate-provider` / `recommendation` / `report-generation` 的引擎；`eval_engine` / `repair` / `checkpoint` / `transitions` |
| `LLM` | 由对话式 Skill 产出（本仓库不内置模型调用，产物以 artifact 形式注入） | `client-intake` / `requirement_analysis` / `risk-analysis` 三个上游 stage（`executor: provided`） |
| `RAG` | 共享 Evidence Provider（`knowledge/rag/` 存储 + `knowledge/evidence/loop.py` 受控回环） | `knowledge-search`（`services:` 中的非线性 Provider，不是 stage） |
| `External Data` | 外部产品数据源，当前为 demo catalog，可替换 | `catalog/product-catalog.v0.1.json`（`is_demo=true`），通过 Product Provider 抽象隔离 |

---

## 2. Skill Graph（8 个层，单向数据链）

```text
FACT ─► REQUIREMENT ─► RISK ─► GAP ─► SOLUTION ─► PRODUCT ─► REPORT
```

| # | Skill | 回答 | 产物 Artifact | 执行 | 关键约束 |
|---|---|---|---|---|---|
| 01 | client-intake | 客户有哪些**事实**？ | ClientProfile | LLM（provided） | FactValue = value/status/source/confidence；UNKNOWN 绝不写入 answered_fields |
| 02 | requirement-analysis | 想解决什么**问题**？ | RequirementAnalysis | LLM（provided） | coverage_gaps 只是 **hint**，不是最终缺口 |
| 03 | risk-analysis | 暴露什么**风险**？ | RiskAssessment | LLM（provided） | 三态 IDENTIFIED/NOT_IDENTIFIED/UNDETERMINED；UNDETERMINED 不提升为 Risk |
| 04 | coverage-gap-analysis | 现有保障哪里**不足**？ | CoverageGapAnalysis | Deterministic | **独立判断层**：不复制 severity/likelihood，只引 `risk_id`；**不携带任何金额字段** |
| 05 | solution | 应采什么**解决策略**？ | SolutionPlan | Deterministic | 禁止具体产品名 / 公司名（策略 ≠ 产品） |
| — | knowledge-search | 提供什么**证据**？ | KnowledgeEvidence | RAG（共享服务） | 非线性 Provider；回环只读（`source_unchanged`） |
| 06 | product-candidate-provider | 哪些产品**够格**？ | ProductCandidates | Deterministic | 只做候选生成（类型/方向/资格/证据四类判定），**不排序、不选主推** |
| 07 | product-recommendation | 用哪些**产品**实现策略？ | ProductRecommendation | Deterministic | 硬拒任何未通过产品校验的候选，绝不把策略伪装成产品 |
| 08 | report-generation | 汇总 / 归一化 / 渲染 | InsuranceReport | Deterministic | 只汇报，不做自主保险判断；canonical-first |

> **Candidate Generation 与 Recommendation 必须分离** —— 不允许同一环节「想产品 → 生成产品 → 推荐产品」。

---

## 3. 控制面（Agent Runtime）

| 组件 | 文件 | 职责 |
|---|---|---|
| Orchestrator | `runtime/orchestrator.py` | `next_runnable → run → eval → PASS/FAIL → repair → checkpoint` 主循环；闸门策略 `stop` |
| Workflow 声明 | `runtime/insurance-analysis.yaml` | stage 顺序 / artifact 生产消费 / executor / gate 的**单一真源** |
| CaseState | `runtime/state/case_state.py` | `artifacts / artifact_registry / tasks / evaluations / checkpoints / services / events / trace` |
| Transitions | `runtime/state/transitions.py` | 三不变量：**单调性**（NON_MONOTONIC）/ **前置条件**（MISSING_INPUT_ARTIFACT + INPUT_NOT_RELEASED）/ **冻结**（ARTIFACT_MUTATION，sha256） |
| Artifact Registry | `runtime/artifact_registry.py` | ART-ID / lineage / fingerprint / evidence_refs；只存元数据，不复制内容 |
| Eval Engine | `runtime/eval_engine.py` | 6 类确定性检查：schema / required_fields / contamination / provenance / cross_artifact / invariant（+ required_non_empty） |
| Repair | `runtime/repair.py` | 失败检查 → 动作映射（RERUN_FROM_UPSTREAM / DROP_INVALID_PRODUCTS）；只改**输入**，不改已冻结 artifact |
| Checkpoint | `runtime/checkpoint.py` | save / load / validate（5 项）→ 损坏即 `CHECKPOINT_INVALID`，绝不静默续跑 |
| Trace | `runtime/trace.py` | 结构化 Execution Trace（13 事件类型 + `duration_ms`），外置 `<case_dir>/trace.jsonl` |
| Observability | `runtime/observability.py` | per-skill latency / 调用计数 / repair 次数 / knowledge-search 次数，回答「一个 Case 跑完多少次 Skill 调用」 |

---

## 4. 上下游边界（数据面）

```text
ClientProfile ─► RequirementAnalysis ─► RiskAssessment ─► CoverageGapAnalysis
      ─► SolutionPlan ─► (KnowledgeEvidence) ─► ProductCandidates
      ─► ProductRecommendation ─► InsuranceReport
```

- **单向**：任一层不得越界（`risk-analysis` 不推荐产品、不重产 requirement）。
- **边界显式化**：各 Skill 入口键名 / 形状并不一致，统一写在 YAML 的 `input_map`（`{artifact_type: {key, shape}}`），**不靠约定**。
- **适配器边界**：`report-generation` 的引擎返回 **Skill 原生结果**（非 Canonical 信封），由 `post_adapter: adapters.report_generation_adapter.to_canonical` 包裹。其余 stage 的 invoke 脚本内部已 `make_envelope`。

---

## 5. 为什么这样分层（对应 README §「为什么这么设计」）

| 设计 | 一句话理由 |
|---|---|
| Skill 不直接调用下一个 Skill | 直接调用会把「谁需要什么」烧死在代码里；由 Orchestrator 读声明式 YAML 决定，新增/调序不改 Skill |
| 必须有 Orchestrator | 需要一个**无业务判断**的中枢：只搬运 artifact、校验契约、强制顺序、在闸门停下 |
| 必须有 Artifact | 层间靠**结构化契约**而非自由文本对话，才可校验、可 diff、可回溯 |
| Eval 独立于 Skill | Skill 自己说「我通过」没有意义；校验必须由不产出该结果的组件执行 |
| Evidence 必须有 provenance | 保险结论若无 `document/chunk` 溯源即为幻觉；属性级 grounding 进一步要求「产品声明的某个属性被哪条证据支持」 |
| Candidate 与 Recommendation 分离 | 生成与选择分离，避免「自己造产品再自己推荐」的自我认证 |
| UNKNOWN 不能当 FALSE | 信息缺失 ≠ 事实为假；把 UNKNOWN 折进 PASS 是**伪造通过**，故设为独立第三态 |
| 失败后不是无限 Retry | 预算是上限不是配额（`max_attempts=3`）；耗尽即 `NEEDS_REVIEW`，由人接手 |

---

## 6. 运行产物落盘

```text
<root>/<case_id>/
  case_state.json          # 唯一事实源快照（含 trace[] / evaluations[] / checkpoints[]）
  artifacts/<type>.json    # 每个 artifact 单文件，可 diff
  trace.jsonl              # 结构化 trace（跨 run 可聚合）
```

> 运行产物落在 `tmp/`（回归运行目录）时**不计入基线**；仓库基线只含代码、契约、数据集与文档。
