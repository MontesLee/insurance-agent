> 🌐 **语言 / Language:** 🇺🇸 [English](README.md) · 🇨🇳 中文
>
> 本文档是英文版 README 的中文翻译。章节标题保留英文锚点以便交叉引用，正文已完整中文化。所有被引用的子文档（ADR、`failure-injection`、`stories`、架构总览等）均已提供中文版（`*.zh-CN.md`），可在文末「文档索引」中直达。

# insurance-agent

一个确定性的多阶段保险分析智能体（Agent），用于展示可靠的 Agent Systems 工程能力。

```text
核心能力：

  - 状态驱动编排（State-driven orchestration）
  - 结构化产物（Structured artifacts）
  - 确定性 Fail-Closed 评估（Deterministic fail-closed evaluation）
  - 有界自修复（Bounded self-repair）
  - 证据溯源（Evidence provenance）
  - 检查点 / 恢复（Checkpoint / Resume）
  - 链路追踪与可观测性（Trace & observability）

组合定位：
  聚焦 Agent Systems 的可靠性，而非保险产品的准确性。
```

> **一句话定位**
> 一个确定性的多阶段保险分析智能体，具备状态驱动编排、Fail-Closed 评估、有界自修复、证据溯源、Checkpoint/Resume 与可观测性。
> （A deterministic multi-stage insurance-analysis Agent with state-driven orchestration, fail-closed evaluation, bounded self-repair, evidence provenance, checkpoint/resume, and observability.）

> **核心观点：** *生成很容易，可靠的延续很难。*

---

## 1. 这是什么？

`insurance-agent` 是一个运行时（runtime），它接收一个**结构化客户状态**，并引导其经过一条固定的数据链 —— 需求 → 风险 → 保障缺口 → 解决方案 → 候选产品 → 推荐 → 报告 —— 同时持续**评估、修复、检查点保存与追踪**每一步。

它**不是**一个聊天机器人，也**不是**一次单独的 LLM 调用。它是一次工程示范：当输入缺失、相互矛盾、或缺乏证据支撑时，如何让一个智能体**安全地继续，或诚实地停下**。

```text
结构化客户状态
（在当前组合中由上游提供）
        │
        ▼
   编排器（Orchestrator）── 状态驱动，不含业务判断
        │
        ▼
  技能 → 产物 → 确定性评估 → 修复 → 检查点 → 追踪
        │
        ▼
   推荐方向（演示用目录，is_demo=true）
```

完整图示：[`docs/architecture/portfolio-architecture.svg`](docs/architecture/portfolio-architecture.svg)

## 2. 我为什么做它

大多数的 Agent 演示只展示*成功的生成*。这个项目提出了一个更难的问题：

> **我们如何让一个智能体知道：何时可以安全地继续 —— 何时必须停下？**

LLM 可以生成看似合理的答案。真正未被解决的问题是*可靠性*：当证据稀薄、某个字段是 `UNKNOWN`、某个产品在目录中不存在时，智能体绝不能悄悄编造一个自信满满的结果。

因此，本项目将以下概念作为**一等运行时概念**来对待：

```text
状态(State)   产物(Artifact)   评估(Eval)
修复(Repair)  证据(Evidence)   检查点(Checkpoint)   追踪(Trace)
```

这才是真正的「产品」。保险领域只是用来演示它的*载体*。

## 3. 核心工程问题

一个永远「成功」的智能体并不可靠 —— 它只是幸运。真正的问题是**延续安全性（continuation safety）**：

- 智能体何时应当推进到下一阶段？
- 何时必须阻断并等待人工？
- 何时必须拒绝生成产品，而不是幻觉出一个？
- 何时已经尝试足够、应当升级（escalate）？

下文每一个设计决策，都是为了让这些问题*可被判定、可被审计*，而不是交给模型的「心情」。

## 4. 架构

![组合架构](docs/architecture/portfolio-architecture.svg)

```text
                    客户输入（Client Input）
                          │
                          ▼
                 ┌───────────────────────────────┐
                 │  结构化客户状态（CaseState）    │
                 │  （在当前组合中由上游提供）       │
                 └───────────┬───────────────────┘
                             │
                             ▼
                   ┌────────────────────┐
                   │   编排器 Orchestrator │  ← 状态驱动，不含业务判断
                   └─────────┬──────────┘
                             │
         ┌───────────────────┼────────────────────┐
         ▼                   ▼                    ▼
   需求 Requirement     风险 Risk             缺口 Gap
         └───────────────────┼────────────────────┘
                             ▼
                         解决方案 Solution
                             │
                             ▼
                  产品候选 Provider（Product Candidate Provider）
                       │           │
                       ▼           ▼
                     RAG       目录 Catalog
                       │           │
                       └─────┬─────┘
                             ▼
                      推荐 Recommendation
                             │
                             ▼
                          报告 Report

   ┌────────────────────────────────────────────────────┐
   │            可靠性层（Reliability Layer）             │
   │  Eval → Repair → Rerun → Review                   │
   │  Provenance / Trace / Checkpoint                   │
   └────────────────────────────────────────────────────┘
```

该架构图**刻意不**把原始自然语言（raw NL）intake 作为一个已执行的阶段展示。在当前组合中，上游三个阶段（`client-intake`、`requirement-analysis`、`risk-analysis`）是 `executor: provided` —— 由精选的 fixtures 播种。运行时从**结构化客户状态**开始证明自身。

## 5. 智能体执行模型

编排器（`runtime/orchestrator.py`）是唯一的运行时循环。它**不持有任何保险业务逻辑**；其行为由声明式的 `runtime/insurance-analysis.yaml` 驱动。

每一轮，它向状态层询问：

```text
next_runnable(state, workflow)  →  下一个可运行的阶段是哪个？
can_run(state, stage)            →  它的前置条件是否满足？
```

如果不存在任何种子（seed），它会**在 `client-intake` 处阻断** —— 绝不凭空捏造一个客户。如果客户信息是 `INSUFFICIENT`/`CONFLICTING`，它会转入 `WAITING_FOR_USER`，而不是猜测。

两种执行器模式：

| 模式 | 阶段 | 含义 |
| --- | --- | --- |
| `provided` | client-intake, requirement-analysis, risk-analysis | 以结构化产物形式到达（在本组合中由 fixtures 播种） |
| `python` | coverage-gap, solution, product-candidate, product-recommendation, report | 确定性、规则驱动、离线、可回归测试 |

这把**安全关键路径完整保留为机器可校验**，并将 LLM 的非确定性从系统中「必须可信」的部分移除。

## 6. 可靠性模型

```text
生成 Generate
   │
   ▼
评估 Evaluate  ──────────────── PASS ──────────▶ 继续 Continue
   │
   └── FAIL
        ▼
     修复 Repair
        ▼
     重新评估 Re-evaluate
        ▼
   PASS / FAIL
        │
   最多 2 次修复尝试
        │
        ▼
   NEEDS_REVIEW（升级给人工）
```

> **不要求智能体永远成功。它只被要求安全地失败。**

修复只改变某个阶段的*输入* —— 绝不改变一个已冻结的产物。修复预算是一个**上限**，而不是配额：在 2 次修复失败后，案例进入 `NEEDS_REVIEW`，由人工决定。这在 [Demo B](docs/demo/demo-b.zh-CN.md) 中有演示。

## 7. 证据与溯源

每一条证据引用都必须携带 `evidence_id` + `document_id` + `chunk_id`。仅由「知识库」支撑的声明是不可采信的。

属性级溯源（attribute-level grounding）将具体产品属性与具体文本块（chunk）进行核对：

```text
产品属性 ─► 证据要求 ─► 证据文本块 ─► SUPPORTED / UNSUPPORTED / CONFLICT / NOT_CHECKABLE
```

- `NOT_CHECKABLE` 是一个**独立的第一等第三态** —— 不确定性永远不会被折叠进 `SUPPORTED`。
- 一个没有支撑证据的产品**不能**成为「有依据的推荐」。

> 设计取舍（记录在 `knowledge/evidence/resources/config/attribute-grounding.rules.json`）：当前只有 `coverage_type` 是**阻断性（blocking）**的溯源属性；`eligibility_age`、`renewal_period`、`deductible`、`coverage_term` 会被溯源并**上报**，但非阻断（演示语料库是有意不完整的 —— 若对每个属性都阻断，会拒绝一切，什么也讲不清）。非阻断**不等于**「已证实」。

## 8. 失败 → 评估 → 修复 → 复核

运行时使用**刻意对抗性**的输入（F1–F6）进行测试，而非仅走 happy path：

| 失败类型 | 注入方式 | 期望行为 |
| --- | --- | --- |
| Schema 违规 | 畸形的产物 | 评估 FAIL / 阻断 |
| 证据缺失 | 空知识库 | 修复 ×2 → NEEDS_REVIEW |
| 不合格产品 | 不可能的资格 | `NO_CANDIDATES` / 不推荐 |
| 幻觉产品 | 未知产品 ID | 被阻断（primary=0, unverified=[]） |
| 溯源缺失 | 无效的 chunk 引用 | 被拒绝 |
| 非法延续 | 被篡改的产物 / 检查点 | `CHECKPOINT_INVALID` / 自愈 |

完整说明：[`docs/eval/failure-injection.zh-CN.md`](docs/eval/failure-injection.zh-CN.md)。

## 9. 检查点与恢复

- **保存：** 每个完成的阶段之后（`case_state.json` + `checkpoints[]`）。
- **信任前先校验：** `load()` 执行 5 项校验（存在性、解析、`case_id` 匹配、schema、注册表指纹、任务→阶段完整性）。任一失败 → `CHECKPOINT_INVALID`；运行绝不会在损坏状态上默默继续。
- **恢复：** 只有非 `PASS` 的任务会重新运行；任何*将会*重新运行的 `PASS` 任务会被**上报**（通常为 0）。

## 10. 评估结果

评估是**确定性的、且与生产者（producer）无关**的（见 §11）。本仓库当前的真实数据：

| 测试套件 | 结果 |
| --- | --- |
| 完整回归（harness） | **30 / 30 GREEN** |
| 全链路 E2E（`run_full_agent_e2e.py`） | **71 / 71 检查项** |
| 智能体基准测试 | **33 / 33 用例** 全部 GREEN |
| 黄金用例 | **9 / 9** |
| 变异测试 | 全部 GREEN |
| 安全护栏 | 全部 GREEN |
| 证据溯源 | 全部 GREEN |
| 推荐目录守卫 | 全部 PASS |
| **发现假通过** | **0** |
| **最大修复次数** | **2**（之后 `NEEDS_REVIEW`） |

这些数字是通过运行测试套件重新核验的，而非从本文档抄录。参见[独立验收](#independent-acceptance)。

## 11. 评估 —— 不是 LLM 自评

```text
产物 Artifact
   │
   ▼
确定性规则 Deterministic Rules
   │
   ▼
PASS / FAIL
```

评估引擎（`runtime/eval_engine.py`）运行六个机器可校验的族：`schema`、`required_fields`、`contamination`（上游边界穿越）、`provenance`、`cross_artifact`、`invariant`。

硬性规则：

- **不可判定 → FAIL。** 不存在 `MANUAL` / `UNKNOWN` 的通过路径。
- **变异测试：** 一个好的产物必须通过；一个*被刻意破坏*的产物必须失败。如果被破坏的产物也通过了，说明评估是空洞的、测试本身有问题。
- **显式不变量：** 例如，被推荐的产品 ID 必须存在于目录中（`catalog_has_primary_product`）；候选 ID 必须是已知的（`candidate_known`）。

示例：

```text
好的产物
  candidate_id = C001
  product_id   = P001
  → PASS

变异
  candidate_id = C999_BOGUS
  → FAIL

变异
  evidence_refs = []
  → FAIL
```

> 一个好产物还不够。评估器还必须*拒绝一个被刻意破坏的产物*。

## 12. 演示

```bash
python demo.py demo-a     # 成功路径 → 有依据的推荐，is_demo=true
python demo.py demo-b     # 安全失败路径 → 空知识库 → NEEDS_REVIEW
python demo.py --list     # 列出可用用例
```

| 演示 | 用例 | 展示内容 |
| --- | --- | --- |
| [Demo A](docs/demo/demo-a.zh-CN.md) | `bm-complete-006-single-medical` | 完整链路 PASS → `CASE_COMPLETED`，P001（演示） |
| [Demo B](docs/demo/demo-b.zh-CN.md) | `bm-noev-001` | 空知识库 → 2 次修复 → `NEEDS_REVIEW` |
| [5 分钟脚本](docs/demo/5-minute-demo-script.zh-CN.md) | — | 面试走查 |

两个演示都会持久化一份结构化的 `trace.jsonl`（机器可读的执行轨迹）；人类可读的走查是每个演示文档中的带注释叙述。

**P001 是一个虚构的演示用目录产品**（`is_demo = true`），仅用于运行时校验。它**不是**真实的保险产品、保费或保险公司 offerings。

## 13. 诚实的局限

开宗明义地说明，因为它们界定了本组合的范围：

1. **部分端到端（PARTIAL E2E）。** 原始自然语言 → 客户状态 intake **不是**当前已执行边界的一部分。运行时从**结构化客户状态**开始证明。我**不**把它呈现为一个完整的对话式智能体。
2. **演示目录。** 所有产品都是 `is_demo = true`（12 个虚构产品）。它们不代表真实的保险产品、价格或保险公司。
3. **证据溯源。** 只有 `coverage_type` 是*阻断性*的溯源属性。`eligibility_age`、`renewal_period`、`deductible`、`coverage_term` 会被溯源并上报，但当前非阻断（设计取舍，见 §7）。
4. **无生产基础设施。** 没有 Redis、Kafka、Kubernetes、多租户、生产数据库或真实的保险公司 API。这些被**有意排除**在组合范围之外。

其他已知的缺口（保持诚实，不隐藏）：

- `product-candidates` 目前还没有独立的 canonical 契约（仍是 skill 级 schema）—— 这是一项被追踪的技术债，而非运行时正确性问题。
- 评估不评判主观质量（语气、可读性）。这是有意省略。

## 14. 关键设计决策（ADR）

每个 ADR 都以**问题 / 决策 / 理由 / 取舍**的简短结构写成 —— 面试友好（每份默认为英文版，同目录下有 `*.zh-CN.md` 中文版）。

| # | 主题 | 文件 |
| --- | --- | --- |
| ADR-001 | 基于技能的架构 | `docs/adr/ADR-001-skill-based-architecture.zh-CN.md` |
| ADR-002 | 编排器优于流水线 | `docs/adr/ADR-002-orchestrator-over-pipeline.zh-CN.md` |
| ADR-003 | 产物血缘 | `docs/adr/ADR-003-artifact-lineage.zh-CN.md` |
| ADR-004 | 确定性评估 | `docs/adr/ADR-004-deterministic-eval.zh-CN.md` |
| ADR-005 | 证据溯源 | `docs/adr/ADR-005-evidence-provenance.zh-CN.md` |
| ADR-006 | 候选 / 推荐分离 | `docs/adr/ADR-006-candidate-recommendation-separation.zh-CN.md` |
| ADR-007 | 检查点 / 恢复 | `docs/adr/ADR-007-checkpoint-resume.zh-CN.md` |

## 15. 仓库结构

仅列核心目录（仓库还有更多文件；以下是对「故事」最重要的那些）：

| 目录 | 职责 |
| --- | --- |
| `runtime/` | 智能体运行时：`orchestrator.py`、`eval_engine.py`、`repair.py`、`checkpoint.py`、`trace.py`、`observability.py`、`state/`（CaseState + transitions）、`insurance-analysis.yaml` |
| `.trae/skills/` | 9 个专家技能；`client-intake`、`requirement_analysis`、`risk-analysis` 已冻结（上游） |
| `domain/insurance/` | 保险领域包：产品分类法、证据层级、RAG 权威语料 |
| `knowledge/` | `rag/`（检索）+ `evidence/`（属性级溯源 provider） |
| `catalog/` | 带版本的演示产品目录（`product-catalog.v0.1.json`，`is_demo=true`） |
| `contracts/` · `adapters/` | canonical 产物契约 · legacy→canonical 适配器 |
| `evals/` | 系统级基准测试 + 黄金用例 |
| `test-cases/` · `tests/` | E2E 场景数据集 · 契约 / 变异 / 工作流单元测试 |
| `docs/` | `architecture/`、`adr/`、`eval/`、`demo/`、`interview/`、`dev-notes/` |
| `demo.py` | 演示 CLI（A 成功 / B 安全失败） |

## 16. 如何运行

**环境：** Python 3.11+（核心循环无需第三方运行时依赖；编排层使用 `PyYAML` 读取工作流定义）。仓库根目录即为运行根目录；无需安装步骤。

**运行演示**

```bash
python demo.py demo-a     # 完整链路 → 有依据的推荐
python demo.py demo-b     # 空知识库 → NEEDS_REVIEW
```

**运行基准测试 / 黄金用例**

```bash
python evals/agent-benchmark/run_agent_benchmark.py     # 33 用例 + 安全硬门
python evals/agent-benchmark/run_golden_cases.py        # 9 黄金 + 前后门
```

**运行完整回归**

```bash
python tmp/run_regression.py        # 运行所有套件，报告 PASS/FAIL/INFRA_ERROR
```

**运行单个套件**

```bash
python test-cases/e2e/full-agent/run_full_agent_e2e.py            # 71 检查项
python tests/eval/test_recommendation_catalog_guard.py            # 目录守卫（正/负）
python tests/workflow/test_step3_mutation.py                     # 反「橡皮图章」变异
python tests/workflow/test_step4_phase7_evidence_grounding.py     # 属性级溯源
python tests/workflow/test_step4_phase13_guardrails.py            # 安全护栏
```

<a id="independent-acceptance"></a>
## 独立验收（Independent Acceptance）

本项目经过了**独立的红队（red-team）审查**，而非仅依赖开发者自己写的测试。审查者检查了代码、注入了失败（F1–F6）、变异了产物、阅读了轨迹、把溯源追到 `chunk_id`、并追猎假通过。

结果（见 [`docs/eval/independent-acceptance-report.zh-CN.md`](docs/eval/independent-acceptance-report.zh-CN.md)）：

```text
P0 = 0   P1 = 0   P2 = 0   P3 = 0
假通过 = 0
回归 = 30 / 30
```

> 独立审查确认了 `PARTIAL E2E` 是一个诚实的边界（原始 NL intake 不在已执行范围内），并要求它被披露 —— 这一点已在 §13 中做到。

---

### 文档索引

| 想了解 | 阅读 |
| --- | --- |
| 架构总览 | [`docs/architecture/architecture.zh-CN.md`](docs/architecture/architecture.zh-CN.md) |
| 设计决策（ADR） | `docs/adr/`（每份均有 `*.zh-CN.md` 中文版） |
| 失败注入（F1–F6） | [`docs/eval/failure-injection.zh-CN.md`](docs/eval/failure-injection.zh-CN.md) |
| 独立验收 | [`docs/eval/independent-acceptance-report.zh-CN.md`](docs/eval/independent-acceptance-report.zh-CN.md) |
| Demo A / B / 5 分钟脚本 | [`docs/demo/`](docs/demo/)（每份均有中文版） |
| 面试问答 | [`docs/interview/interview-guide.zh-CN.md`](docs/interview/interview-guide.zh-CN.md) |
| 面试故事 | [`docs/interview/stories.zh-CN.md`](docs/interview/stories.zh-CN.md) |
| 命名与规范 | `AGENTS.md`（英文） |
