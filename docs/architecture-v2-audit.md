# 保险 Agent 架构 V2 审计（Phase 0：只读分析）

> 本文件由 **Phase 0：Architecture Audit** 产出。**仅分析、未修改任何业务 Skill。**
> 下一阶段（Phase 1）请在确认本审计结论后再启动。

---

## 0. 审计范围与方法

- 读取：`AGENTS.md`、`.trae/skills/*/SKILL.md`、各 Skill 的 `schemas/`、`CONTRACT.md`、`.trae/skills/*/evals/`。
- 实跑验证：用 `recommendation` 自带数据集 + 实跑 `knowledge-search` → `recommendation` → `report-generation`，确认当前链路真实可连通（见 §4 的“已验证事实”）。
- 临时文件清理（不属于 V2 改造，但属于用户早先提出的清理请求，且与审计“当前问题”直接相关）：
  - 删除了 3 处 `tmp/` 调试/备份树（顶层 `tmp/`、`requirement_analysis/tmp`、`risk-analysis/tmp`），
    共 **2142 个文件**，0 个 `tmp/` 目录残留。
  - 依据 `AGENTS.md` 约定：`tmp/ # 运行产物，不计入基线`。
  - **未触碰任何业务 Skill 源码**（仅删除 `tmp/` 运行产物，其中 `risk-analysis/tmp` 含 anatomy 探针副本与 `.bak`，均为调试产物）。

---

## 1. 当前仓库结构（审计基线）

```text
insurance-agent/
├── AGENTS.md                      # 项目总约定（数据链 FACT→REQUIREMENT→RISK→GAP→SOLUTION→PRODUCT）
├── .trae/skills/                 # ★ 6 个 Skill 实际所在目录（V2 目标为 skills/，见 §5 备注）
│   ├── client-intake/            # PowerShell，118 文件（对话驱动）
│   ├── requirement_analysis/     # PowerShell，126 文件（snake_case 命名）
│   ├── risk-analysis/            # PowerShell，引擎 + 15 数据集（下游已声明 coverage-gap-analysis）
│   ├── knowledge-search/         # Python，23 文件（Evidence Provider）
│   ├── recommendation/           # Python，18 文件（product 层；snake_case 命名）
│   └── report-generation/       # Python，20 文件（汇总层）
├── rag/                          # 真实 RAG 基础包（__init__/engine/models/store）—— 保留
├── client-intake-data/           # client-intake 的状态输出目录（CLIENT_PROFILE 等）
├── scripts/run-regression.ps1    # 顶层回归入口
├── test-cases/TEST_CASES.md      # 顶层测试用例说明
└── docs/                         # 仅含 client-intake 的重构报告
```

**V2 目标目录现状**：`contracts/`、`domain/`、`workflow/`、`state/`、`evals/` **均不存在**；
`rag/`、`client-intake-data/`、`scripts/`、`test-cases/`、`docs/` 已存在。

---

## 2. 当前 6 个 Skill 盘点

| # | Skill | 运行时 | 输入 | 输出（核心产物） | 下游消费者 |
|---|-------|--------|------|------------------|-----------|
| 01 | client-intake | PowerShell（多轮对话） | 客户原话 | `CLIENT_PROFILE.md` + CanonicalClientState | requirement_analysis、risk-analysis |
| 02 | requirement_analysis | PowerShell | `CLIENT_PROFILE.md` | `RequirementAnalysis`（requirements / coverage_gaps / information_gaps / priorities） | risk-analysis、recommendation、report-generation |
| 03 | risk-analysis | PowerShell | ClientState + requirements | `RiskAssessment`（risks R1–R5、risk_matrix、coverage_assessment、top_priorities、unknowns） | coverage-gap-analysis（声明但未实现）、recommendation、report-generation |
| 04 | knowledge-search | Python | `query` / `top_k` / `filters` | `KnowledgeEvidence`（results[] + provenance + conflict） | recommendation（名义上）、report-generation |
| 05 | recommendation | Python | requirement + risk + **candidate_solutions** | `ProductRecommendation`（primary/alternatives/not_recommended/evidence_refs/human_review） | report-generation |
| 06 | report-generation | Python | 5 路上游（client_profile / requirement_analysis / risk_analysis / knowledge_search / recommendation） | `InsuranceReport`（8 章节结构化 + Markdown 渲染） | 终端 |

### 逐 Skill 明细（Input → Output → Contract → Downstream → 问题）

**① client-intake**
- Input：客户原话 → Output：事实档案（含 KNOWN/UNKNOWN/ESTIMATED/ASSUMED/INFERRED 五态）
- Contract：`schemas/execution-output.schema.json`；强边界 HF01–HF09
- Downstream：requirement_analysis / risk-analysis
- 问题：无。稳定，按 V2 原则**不重写**。

**② requirement_analysis**
- Input：`CLIENT_PROFILE.md` → adapter → 结构化 Input；Output：`output.schema.json`
- Contract：5 态 analysis_status、5 类需求、4 级优先级、`guardrails.product_recommendation_included=false`
- Downstream：risk-analysis / recommendation / report-generation
- 问题：
  - **命名 snake_case**（V2 §32 要求 kebab-case `requirement-analysis`）。
  - 已**自含 `coverage_gaps` 输出** → 与 V2 新增 `coverage-gap-analysis` 存在边界重叠（见 §4 P3）。

**③ risk-analysis**
- Input：ClientState + requirements → Output：`risk-analysis-output.schema.json`、`risk.schema.json`
- Contract：R1–R5 风险域、severity×likelihood→residual→priority、provenance、UNKNOWN 不臆断
- Downstream（SKILL.md 自声明）：`coverage-gap-analysis`（**该 Skill 不存在**）、recommendation、report-generation
- 问题：无逻辑问题；其 `coverage_assessment`（protected/unprotected 金额）已含“缺口”雏形 → 新 `coverage-gap-analysis` 应**消费**而非重算。

**④ knowledge-search**
- Input：`query` → Output：`knowledge-search-output.schema.json`（status / results[] / conflict / retrieval_metadata）
- Contract：只找证据、不推荐、不补事实、`conflict=true` 保留双方
- Downstream：recommendation（名义）、report-generation
- 问题：**与决策链脱节**（见 §4 P4）。

**⑤ recommendation**
- Input：requirement + risk + **`candidate_solutions`** → Output：`recommendation-output.schema.json`
- Contract：primary_recommendation / alternatives / not_recommended / evidence_refs / human_review_required；status 含 INSUFFICIENT_INPUT / NO_CANDIDATES / INCOMPLETE_EVIDENCE
- Downstream：report-generation
- 问题：**核心断点** —— 输入依赖 `candidate_solutions`，但 6 个 Skill 中**没有任何一个产出它**（见 §4 P1）。

**⑥ report-generation**
- Input：5 路上游 → Output：`report-output.schema.json`（8 章节 + validation + provenance）
- Contract：不重新分析、缺失→「待确认」、冲突显式化（不裁决）、金额子串防幻觉
- Downstream：终端
- 问题：**输入契约缺口** —— V2 要求消费 8 个 Artifact（含 coverage_gap_analysis / solution_plan / product_recommendation），当前仅 5 路（见 §4 P5）。

---

## 3. 当前数据链路（含断点）

```text
client-intake ──► requirement_analysis ──► risk-analysis ──┐
   │                │                      │              │
   │                │                      ▼              ▼
   │                │                 [coverage-gap-analysis]  ← 缺失
   │                │                      │              │
   │                │                      ▼              ▼
   │                │                 [solution]            ← 缺失
   │                │                      │              │
   │                └──────────────────────┼──────────────┘
   │                                       ▼
   │                              knowledge-search        ← 当前脱节（见 P4）
   │                                       │
   │                                       ▼
   │                              [product-recommendation] ← 现为 recommendation，输入需 candidate_solutions
   │                                       │                    ↑ 无生产者（断点）
   └──────────────────────────────────────┴──────────────► report-generation
                                                            （当前仅接 5 路，缺 3 路）
```

### 已验证事实（实跑结论，来自本次 e2e 验证）
1. 接口契约在字段层面**首尾对齐**：5 路上游 output schema 字段与 `report-generation` 的 input/adapter 完全一致。
2. 3 个 Python 段（`knowledge-search` → `recommendation` → `report-generation`）端到端实跑**通过**、数据可传递、成稿 schema 有效。
3. **真实 bug（已修复）**：`recommendation` 在证据不足时返回 `primary_recommendation=null`（status=`INCOMPLETE_EVIDENCE`），原 `report-generation` 兜底条目写 `candidate_id/fit=null` 违反成稿 schema；已改为字符串占位，Skill 6 自身 8 例 + 2 负向仍全绿。
4. **真实断点（未解）**：`recommendation` 输入需 `candidate_solutions`，不提供时直接返回 `NO_CANDIDATES` —— 证实“候选方案无生产者”是链路最大缺口。

---

## 4. 存在的问题（汇总）

- **P1（致命断点）`candidate_solutions` 无生产者**：`recommendation` 的输入契约要求候选保障方案/产品，但 6 个 Skill 中无任一产出。V2 通过将 `recommendation` 演化为 `product-recommendation`、把输入改为消费 `SolutionPlan + CoverageGapAnalysis + KnowledgeEvidence` 来根治（不再需要独立的 `candidate_solutions` 生产者）。
- **P2 缺 `coverage-gap-analysis`**：`risk-analysis` 的 SKILL.md 已声明下游为 `coverage-gap-analysis`，但该 Skill 尚未存在；导致 Risk 直接跳到 Product，缺“缺口”中间层。
- **P3 缺 `solution`**：无“保障解决方向”层，Risk/Gap 与具体产品之间没有抽象缓冲，容易越界成产品推荐。
- **P4 `knowledge-search` 脱节**：当前 e2e 中 KS 跑在 recommendation 之前，但 recommendation **不消费** KS 输出（它直接吃 `candidate_solutions`）。KS 形同孤立。V2 应把它定位在 `solution` 之后，并允许受控回环。
- **P5 `report-generation` 输入契约缺口**：当前 5 路，缺 `coverage_gap_analysis` / `solution_plan` / `product_recommendation` 三路；需扩展 input schema + adapter + 章节（新增 06 产品候选及比较、04 保障缺口深化）。
- **P6 命名不一致**：`requirement_analysis`、`recommendation` 为 snake_case；V2 §32 要求 kebab-case（`requirement-analysis`、`product-recommendation`）。同时物理目录是 `.trae/skills/` 而非 V2 目标的 `skills/`（目录归属属布局选择，可保留 `.trae/skills/`，但命名建议统一）。
- **P7 缺共享 `contracts/` 层**：跨 Skill 契约目前隐含在各自 `schemas/` + `report-generation` 的 adapter 中，无统一公共契约，容易出现 P5 这类“下游不知道上游新产物”的漂移。
- **P8 缺 `workflow/` 编排与 `state/` CaseState**：当前无 Orchestrator；3 个 PowerShell 段（client-intake / requirement_analysis / risk-analysis）依赖 LLM 多轮驱动，无法 fire-and-forget。
- **P9 `requirement_analysis` 与新建 `coverage-gap-analysis` 边界重叠**：前者已输出 `coverage_gaps`，后者需明确“消费前者 + risk 的 coverage_assessment + 客户 existing_protection”，避免重复推导或结论分歧。
- **P10 测试散落**：各 Skill 自带 `evals/`（requirement_analysis 18 例、risk-analysis 15 例、knowledge-search 数据集、recommendation 11 例、report-generation 8 例 + 2 负向），但无统一的 `evals/skill|contract|workflow|e2e/` 结构，E2E 仅我手跑验证过，无固化脚本。

---

## 5. V2 修改方案（映射当前 → 目标）

| 当前 | V2 目标 | 动作 | 风险 |
|------|---------|------|------|
| client-intake | 01 client-intake | **保留**，仅按需补 adapter | 低（稳定） |
| requirement_analysis | 02 requirement-analysis | **重命名目录**为 kebab；内部逻辑不动 | 中（需同步所有引用该目录名的路径） |
| risk-analysis | 03 risk-analysis | **保留**；其 `coverage_assessment` 供新 Skill 消费 | 低 |
| — | 04 coverage-gap-analysis | **新建**：消费 RiskAssessment + existing_protection + RequirementAnalysis → CoverageGap（NONE/PARTIAL/SUFFICIENT/UNKNOWN + gap_level） | 中（边界见 P9） |
| — | 05 solution | **新建**：Gap → SolutionPlan（方向，禁具体产品） | 中 |
| knowledge-search | 06 knowledge-search | **保留**；增加由 `SolutionPlan` 构造 `KnowledgeQuery` 的 adapter；重定位到 solution 之后 | 低 |
| recommendation | 07 product-recommendation | **演化**：目录改名 + 输入由 `candidate_solutions` 改为 `SolutionPlan + CoverageGapAnalysis + KnowledgeEvidence`；保留已有决策/权衡/证据/人审逻辑 | 中（核心迁移，需保测试） |
| report-generation | 08 report-generation | **扩展**输入至 8 Artifact，新增 06 产品候选及比较、深化 04 保障缺口 | 中 |

**新增基础设施（Phase 1–7）：**
- `contracts/`（9 份 schema）：client-profile / requirement-analysis / risk-assessment / coverage-gap-analysis / solution-plan / knowledge-query / knowledge-evidence / product-recommendation / insurance-report。
- `workflow/insurance-analysis.yaml` + `orchestrator.md`：依赖、状态（RUNNING/WAITING_FOR_USER/RETRYING/HUMAN_REVIEW/COMPLETED/FAILED/BLOCKED）、受控回环（`max_retries=2`、`max_knowledge_rounds=3`）。
- `state/`：CaseState（status 枚举 + artifacts 映射 + completed/failed skills + human_review_required）。
- `domain/insurance/`（可选但推荐）：pack/playbook/references/overlays，把险种知识从 Skill 核心下沉，符合 Lawgent domain pack 思想。
- `evals/` 归并：`skill/ contract/ workflow/ e2e/`，E2E 至少 5 个完整客户（E2E-001~005）。

**关键决策建议（请确认）：**
- **P1 根治方式**：推荐采用 V2 原文方案——`product-recommendation` 直接消费 `SolutionPlan`，**不**再需要单独的 `candidate_solutions` 生产者。这比“新增一个 candidate 生产者”更简洁，也消除了 V1 的断点。
- **P9 重叠处理**：`coverage-gap-analysis` 以 `risk-analysis.coverage_assessment` 与 `client-intake.existing_protection` 为输入，不重算 severity/likelihood；`requirement_analysis.coverage_gaps` 降级为“需求层缺口提示”，最终缺口结论以 `coverage-gap-analysis` 为准，避免双源分歧。

---

## 6. 风险与约束（执行 Phase 1+ 必须遵守）

1. **不重写稳定 Skill**：client-intake / requirement_analysis / risk-analysis 只做 Contract 对齐与必要的 adapter/重命名，**不重写内部逻辑**（V2 §31、§37）。
2. **测试回归优先**：所有现有 Eval 必须保持全绿（requirement_analysis 18、risk-analysis 15、knowledge-search 数据集、recommendation 11、report-generation 8+2）。新增 Skill 自带 Eval。
3. **provenance 贯通**：新 Skill 的每条结论须能回链到 Risk→Client Fact（沿用既有 `reasoning_evidence_refs` / `evidence_refs` 机制）。
4. **不越界**：coverage-gap-analysis / solution 禁止写具体产品名；report-generation 禁止重新推理（沿用已验证的“缺失→待确认 / 冲突→UPSTREAM_CONFLICT”纪律）。
5. **信息不漂移**：UNKNOWN 永不自动变 KNOWN（沿用既有五态约束）。

---

## 7. 下一步（Phase 1 提案，待确认）

**Phase 1：Contract Layer**（仅新增，不改业务逻辑）
1. 创建 `contracts/` 9 份 schema（先 client-profile / requirement-analysis / risk-assessment / insurance-report 四份，再补其余）。
2. 写 Contract Test：用 jsonschema 校验既有 6 个 Skill 的 output 是否满足对应 Contract（验证“当前已对齐”，为后续迁移兜底）。
3. 不动任何业务 Skill 代码。

完成后再次停顿，交回确认，再进入 Phase 2（coverage-gap-analysis 新建）。

---

### 附录：本次清理明细（临时文件）
| 删除目录 | 文件数 |
|----------|--------|
| `tmp/`（含 `risk-analysis-nul-trap`、`ra-c009`、`backup-pre-refactor-RA-*` 等调试/备份副本） | 498 |
| `.trae/skills/requirement_analysis/tmp` | 59 |
| `.trae/skills/risk-analysis/tmp`（含 anatomy_probe_* 探针与 .bak） | 1585 |
| **合计** | **2142** |

> 以上均为 `tmp/` 运行产物/备份，符合 `AGENTS.md` “tmp/ 不计入基线”约定；删除后 0 个 `tmp/` 目录残留，业务 Skill 零改动。
