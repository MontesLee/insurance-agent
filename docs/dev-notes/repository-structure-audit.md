# Repository Structure Audit & Migration Plan

> **性质：READ-ONLY 审计。本文件是本次任务唯一的产出。**
> 仓库：`https://github.com/MontesLee/insurance-agent`
> 本地路径：`D:\Workspace\insurance-agent`
> 审计时间：2026-09-15
> 审计基线：`git HEAD = 2e88056`（working tree clean，0 untracked）
> 审计范围：Step 1–4 完成后的**目录与文件结构**；不涉及功能新增、不涉及业务代码修改。

**本审计未执行任何迁移。** 未 `git mv` / 未 rename / 未 delete / 未改 import / 未改任何现有文件。
唯一新增文件：本文件。

---

## 0. 审计方法与证据口径

| 项 | 做法 |
|---|---|
| 结构来源 | `git ls-files`（**只统计被 git 跟踪的内容**，避免被 `tmp/` 434 个运行产物干扰） |
| 职责判定 | 逐文件阅读实际职责（入口脚本 / import 关系 / 配置引用），**不看目录名猜** |
| 依赖判定 | grep `import` / `REPO_ROOT` / `Path(__file__)` / 路径字符串字面量 / YAML / JSON 配置 |
| 数字口径 | 全部来自真实命令输出（下节给出可复现命令） |
| 未验证项 | 明确标注为「未验证」或进入 Open Questions，不做推测性断言 |

---

## 1. Executive Summary

### 1.1 一句话结论

> **仓库结构的「骨架」已经是对的（契约 / 适配器 / Skill / 领域 / 目录高度一致），
> 真正的问题只有 3 类：① Agent Runtime 在文件系统上没有形成单一边界；② Knowledge 层被拆成两个互不说明的目录；③ 一批开发过程的运行产物与历史文档被当作基线提交进了仓库。**
>
> 三类问题里，**③ 是零风险且应当立刻做**，**①② 是有明确收益但需要动 import 的迁移**，必须显式决策后再做。

### 1.2 关键数字

| 指标 | 值 | 说明 |
|---|---|---|
| Git 跟踪文件总数 | **580** | working tree clean |
| 根目录文件数 | **4** | `README.md` / `AGENTS.md` / `demo.py` / `.gitignore` |
| 一级目录数（跟踪） | **15** | + `tmp/`（gitignore）/ `.git/` |
| **根目录拥挤度** | **不拥挤** | 4 个文件，均为真正的项目入口/约定；**不构成问题** |
| 9 个 Skill 的文件占比 | **398 / 580 = 68.6%** | `.trae/skills/**` |
| 提交进仓库的运行产物 | **23** | `_*_log.txt` / `_rg_sample.txt` |
| 回归套件 | **29** | 全绿（`tmp/run_regression.py`） |
| 提交历史 | **7** commits | 一次性大提交模式（非逐步演化） |

### 1.3 已经做对的地方（不建议动）

这几点是**结构已经正确**的证据，迁移方案必须保住它们：

1. **契约边界正确**：`contracts/`（10 canonical schema + `skill-id-map.json` + 生成器）与
   `.trae/skills/*/schemas/`（Skill 级 schema）分工清晰，没有互相污染。
2. **适配器边界正确**：`adapters/` 是 10 个纯包络（envelope）适配器，**不含业务决策**，
   与 `docs/contract-layer.md` 的声明一致。
3. **Skill 目录高度同构**：9 个 Skill 中有 7 个具备完整的
   `SKILL.md + CONTRACT.md + references/ + schemas/ + resources/ + evals/ + scripts/` 骨架。
4. **Skill 位置正确**：放在 `.trae/skills/`（AI IDE / WorkBuddy 的发现约定），
   **不是**仓库根的 `skills/`；`AGENTS.md §7` 已明文规定。
5. **运行产物已隔离**：`tmp/` 已被 `.gitignore` 排除，0 个被跟踪。
6. **领域层与运行层已经分离**：`domain/insurance/`（领域知识）与 `workflow/`（运行时）
   不互相污染；`evidence/`、`rag/` 是通用层，不含保险专属判断。

---

## 2. Current Structure（真实仓库）

### 2.1 一级目录一览

```
insurance-agent/
├── .gitignore
├── AGENTS.md                          ← 项目级硬约定（命名/Skill 分层/Eval 纪律）
├── README.md                          ← Portfolio 主入口（17 节）
├── demo.py                            ← CLI Demo 入口（Step 4 P10）
│
├── .trae/
│   ├── skills/                        ← 9 个 Specialist Skill（398 个文件）
│   └── internal/                      ← 2 个调试脚本【已 gitignore，不在仓库】
├── adapters/                          ← 10：legacy → canonical 包络适配器
├── catalog/                           ← 2：Demo Product Catalog + 说明
├── client-intake-data/                ← 1：client-intake 运行时客户数据根
├── contracts/                         ← 12：9 份 canonical schema + 生成器 + skill id map
├── docs/                              ← 24：架构 / 契约 / ADR / Trace / 失败分类 / 交付
│   └── adr/                           ← ADR-001 … ADR-007
│   └── client-intake/                 ← 2：client-intake v1.x 历史文档
├── domain/insurance/                  ← 15：Domain Pack（pack.yaml / playbook / references / kb / scripts）
├── evals/agent-benchmark/             ← 8：Benchmark + Golden + Baseline + 运行器
├── evidence/                          ← 7：共享 Evidence Provider（+ 属性级 grounding）
├── rag/                               ← 4：RAG 基础层（models / store / engine）
├── scripts/                           ← 1：run-regression.ps1（**已失效**）
├── state/                             ← 5：CaseState + transitions + store
├── test-cases/                        ← 25：E2E 场景数据 + 运行器
├── tests/                             ← 51：契约测试 / 工作流单测 / 变异测试
├── workflow/                          ← 13：Orchestrator / eval / repair / checkpoint / trace / observability
└── (tmp/)                             ← 434 运行产物【已 gitignore】
```

### 2.2 每个一级目录的真实职责 / 问题 / 建议

| Directory | Actual Responsibility（实测） | Problems | Recommendation |
|---|---|---|---|
| `.trae/skills/` | 9 个 Specialist Skill 的完整分发单元（SKILL.md + 契约 + 规则 + 引擎 + Eval + 夹具）。398 文件 / 68.6% 体量 | 命名不一致（`requirement_analysis` 下划线）；2 个 Skill 缺 `CONTRACT.md`；1 个 Skill 根多一个 `REFACTOR_REPORT.md` | **KEEP 位置不动**。仅记录一致性缺口；`requirement_analysis` 与 `client-intake` 为 AGENTS §4 冻结 Skill，**禁止改动** |
| `adapters/` | 10 个纯包络适配器：把 Skill 原生输出包成 canonical contract。`insurance-analysis.yaml` 通过 `post_adapter: adapters.report_generation_adapter.to_canonical` 声明引用 | **无实质问题**。文件名与 `skill-id-map.json` 一一对应 | **KEEP AS-IS** |
| `catalog/` | Demo Product Catalog（12 个虚构产品，全部 `is_demo=true`），已在 Step 4 P8 版本化（`catalog_version` / `product_version` / `effective_from`） | 路径 `catalog/product-catalog.v0.1.json` 被 **2 份 rules JSON + 2 处代码默认值** 硬引用 | **KEEP**（含文件名）。移动需同步改 4 处，收益为 0 |
| `client-intake-data/` | `client-intake` 的**运行时**客户数据写入根（真实数据，非夹具）。当前仅 1 个 README 被跟踪 | 被**冻结 Skill 深度引用**（`SKILL.md` / `references/06-*.md` / `interaction-nodes.md` / RA 的 6 份 fixture 都以该路径为准）；自身 README 声明「建议版本库忽略」但 `clients/` 未 gitignore | **KEEP 路径不变**（冻结依赖）。仅建议补 `.gitignore`（只保留 README） |
| `contracts/` | 9 份 Canonical Artifact schema + `skill-id-map.json`（canonical→legacy 名称解耦）+ `build_contracts.py`（生成器）+ `_build_log.txt`（**已提交的运行日志**） | 生成器与生成物同目录（§十一 明确点名要判定的模式）；`_build_log.txt` 是运行产物却被提交 | **KEEP 生成器同居**（记忆记载：重跑生成器会回退手改内容，同居有助于发现漂移）。**删除** `_build_log.txt` |
| `docs/` | 24 份文档：架构(2) / 目标架构与审计(2) / 契约(1) / 领域包(1) / Trace(1) / 失败分类(1) / 编排(1) / 三个 Skill 的 v2 说明(3) / Step2-4 过程与交付(4) / ADR(7) / client-intake 历史(2) | **Portfolio 交付物与开发过程记录混放**；`docs/client-intake/*` 引用的 `01-client-intake/SOP.md`、`EVAL.md` 已不存在（死链）；`test-cases/TEST_CASES.md` 同样指向已删除的旧路径 | 新增 `docs/dev-notes/` 收拢过程记录；`docs/archive/` 收拢失效历史；**`docs/client-intake/` 不能动**（见 §7） |
| `domain/insurance/` | Domain Pack：`pack.yaml`（险种 taxonomy / 证据类型 / 来源等级 / rag 摄取配置）+ `playbook.md` + 6 份权威 references（= RAG 生产语料）+ `kb/insurance_kb.sqlite`（运行产物）+ `overlays/` + 3 个构建/校验脚本 | `kb/insurance_kb.sqlite` 是运行产物，是否应入库需确认（当前被跟踪）；`scripts/` 下 3 个脚本属**构建/维护**类，不属于运行链 | **KEEP 主体**。`kb/*.sqlite` 建议改为「脚本生成 + gitignore」。脚本建议保留（低价值迁移） |
| `evals/` | 仅含 `agent-benchmark/`：33 个 Case manifest + 9 个 Golden + baseline + 2 个运行器 + 报告 | 目录名 `evals/` 与 `.trae/skills/*/evals/`（Skill 级 eval）**同名不同义**，易混淆 | 保留（可读性尚可）。重命名为 `benchmark/` 属可选优化，收益低、需改 README/docs 多处 |
| `evidence/` | 共享 Evidence Provider（V2 Phase 4）：`request`（模板化 KnowledgeQuery）/ `provider` / `loop` / `attribute_grounding`（Step 4 P7 属性级三态 grounding）+ `resources/config/` | 与 `rag/` 两层语义（Provider 层 vs 检索引擎层）对初次读者不直观；`provider.py` 的 `REPO_ROOT = dirname(HERE)` 是**层级敏感**代码 | 与 `rag/` 合并为 `knowledge/`（详见 §4 / §6） |
| `rag/` | RAG 基础层：`models`（Chunk/Query/Candidate/Evidence）/ `store`（SQLite + `chunk_markdown`）/ `engine`（trigram-BM25 + RRF + Reranker） | 同上；无 `REPO_ROOT`，移动相对安全（只受 import 影响） | 同上 |
| `scripts/` | 仅 1 个 `run-regression.ps1`：client-intake v1.x 时代的 8 Case 回归壳 | **已失效且有害**：`$IntakeDir = <repo>/01-client-intake` 目录不存在；脚本会用 `New-Item -Force` **凭空重建**这个历史目录并写入运行产物 → 运行即污染仓库。已被 `tmp/run_regression.py`（29 套件）取代 | **DELETE**（历史由 git 保留）。若要保留运维脚本位置，重命名为 `scripts/ops/` 并只放**有效**脚本 |
| `state/` | CaseState 唯一事实源 + `transitions`（不变量：`NON_MONOTONIC` / `MISSING_INPUT_ARTIFACT` / `ARTIFACT_MUTATION`）+ `store`（持久化）+ `case_state.schema.json` | 与 `workflow/` 同属 Agent Runtime 却分成两个顶层目录；**依赖是单向的**（`workflow → state`，`state` 从不 import `workflow`），属分层而非循环，但读者需自行推断 | 收进 `runtime/state/`（详见 §4 / §6） |
| `test-cases/` | E2E 场景数据：`case-00X.json` + `manifest.json` + `kb-empty/` 夹具，**同时**包含 3 个运行器 `run_*_e2e.py` | **违反「tests/ = 程序，test-cases/ = 数据」原则**：运行器混进数据目录；`TEST_CASES.md` 是 client-intake v1.x 遗留（引用已删除的 `01-client-intake/SOP.md`） | 保留双目录（拆分合理）。**运行器与场景同居是刻意设计**（见 §3.6），建议以**文档化约定**替代强制搬迁 |
| `tests/` | 测试程序：`contracts/`(11) / `e2e/`(2) / `evidence/`(2) / `workflow/`(5) + 各自 fixture | `tests/` 内**也**含夹具（`contracts/fixtures/`、`e2e/fixtures/case-full-chain.json`、`evidence/cases/fixtures/`），与 `test-cases/` 职责重叠 | 保留；把「程序 vs 数据」的边界写进 `AGENTS.md` 或 `tests/README.md` |
| `workflow/` | Agent Runtime 控制层：`orchestrator` / `tasks` / `artifact_registry` / `eval_engine` / `repair` / `checkpoint` / `trace` / `observability` + `insurance-analysis.yaml`（**声明式工作流单一真源**）+ `resources/config/`（外置规则） | 目录名 `workflow` 在通用语境里读起来像"CI 工作流"，对一个 **Agent Runtime** 而言命名不够直白；与 `state/` 同属 Runtime 却分列两个顶层目录 | 重命名为 `runtime/`，并把 `state/` 收为其子层（详见 §4） |

---

## 3. Current Problems（对应任务书 §五 的 9 个检查项）

### 3.1 Runtime 是否分散？—— **是，且这是本仓库最主要的结构问题**

Runtime 的 10 个构件分布在 **2 个顶层目录**：

| 构件 | 当前位置 |
|---|---|
| `orchestrator`（唯一运行时循环） | `workflow/orchestrator.py` |
| `tasks`（Task 实体 / 状态机） | `workflow/tasks.py` |
| `artifact_registry`（ART-ID / lineage / evidence_refs） | `workflow/artifact_registry.py` |
| `eval_engine`（6 类确定性检查） | `workflow/eval_engine.py` |
| `repair`（局部重跑 + 预算） | `workflow/repair.py` |
| `checkpoint`（save/load/validate） | `workflow/checkpoint.py` |
| `trace`（13 类事件） | `workflow/trace.py` |
| `observability`（latency / call count） | `workflow/observability.py` |
| `CaseState` / `transitions` / `store` | **`state/`** ← 分列 |
| 外置规则（eval / repair / orchestrator） | `workflow/resources/config/` |

**判定：应当形成一个清晰的 Runtime 边界。** 理由：

- 这 10 个构件**共同构成一句话**：「把 Skill 编排起来、评估、修复、可恢复、可观测」。
  拆在 `workflow/` + `state/` 两个顶层目录，读者必须自己推断二者关系。
- `workflow/` 对 `state/` 的依赖是**单向且全面**的（7 处 `from state import ...`），
  `state/` 从不反向 import `workflow/`。这说明二者是**同一个模块的两层**（state 层 / control 层），
  而不是两个独立模块。**（未发现循环依赖——已实测确认。）**
- 对 Portfolio 读者：`runtime/` 三个字比 `workflow/` 更直接地回答「Agent 运行时在哪」。

### 3.2 Skill 是否清晰？—— **基本清晰，有 4 个一致性缺口**

| 检查项 | 结论 |
|---|---|
| 是否全部集中 | ✅ 全部在 `.trae/skills/`（9 个），无散落 |
| 是否存在重复 Skill | ✅ **无重复**。`recommendation/` 与文件系统名 `product-candidate-provider/` 不冲突；`requirement-analysis`（canonical id）↔ `requirement_analysis`（物理目录）通过 `contracts/skill-id-map.json` 显式解耦 |
| 是否存在 legacy Skill | ⚠️ 有**一处历史兼容**：`requirement_analysis`（下划线）。`workflow/insurance-analysis.yaml` 中 `product-recommendation` stage 带 `legacy_skill: recommendation` 字段，说明保留旧 id 是**有意为之** |
| Skill 内部结构是否一致 | ⚠️ 7/9 完整。**缺口**：`client-intake` 与 `requirement_analysis` 无 `CONTRACT.md`；仅 3 个有 `ACCEPTANCE.md`（knowledge-search / recommendation / report-generation）。`client-intake` 独有 `examples/` |
| 是否存在与 Skill 无关的文件 | ⚠️ **1 处**：`.trae/skills/requirement_analysis/REFACTOR_REPORT.md`（Skill 根的重构报告，属过程记录）。但该文件被 `scripts/check-skill-anatomy.ps1:106` **显式豁免**，且该 Skill 已冻结 → **不建议移动**（详见 §8） |
| `SKILL.md` 行数纪律 | ✅ 全部 ≤100 行（client-intake 恰好 100） |
| 架构守卫覆盖 | ⚠️ `check-skill-anatomy.ps1` 只存在于 **2/9** 个 Skill（`requirement_analysis`、`risk-analysis`） |

**特别说明：`requirement_analysis` 是否重命名？**
→ **不建议重命名。** 证据（三条独立理由）：
1. `AGENTS.md §1` 明文规定「为既有 Skill 且已完成回归基线，**不重命名**」；
2. `AGENTS.md §4` 把 `requirement_analysis` 列为**禁止修改任何文件**的冻结 Skill；
3. 代码层存在**运行时**依赖链：`workflow/insurance-analysis.yaml:37` 的 `skill: requirement_analysis`
   → 该值经 `contracts/skill-id-map.json` 映射 → adapter 物理路径；
   另有 `adapters/requirement_analysis_adapter.py`、`tests/contracts/test_requirement_analysis_contract.py`、
   `docs/` 多处引用。**收益（命名一致）远小于风险。**

### 3.3 Domain 与 Runtime 是否混杂？—— **否，分离良好**

| 层 | 内容 | 位置 |
|---|---|---|
| Insurance-specific | 险种 taxonomy / 证据类型 / 来源等级 / 权威知识正文 / playbook | `domain/insurance/` |
| Insurance-specific（产品） | 12 个 demo 产品 + 版本字段 | `catalog/` |
| Insurance-specific（规则） | 风险分类 R1–R5 / 覆盖映射 / 解决方案映射 / 报告文案 | 各 Skill 的 `resources/config/*.rules.json` |
| Agent Runtime（领域无关） | orchestrator / eval / repair / checkpoint / trace / observability | `workflow/` |
| Agent Runtime（领域无关） | CaseState | `state/` |
| 通用知识层（领域无关） | Evidence Provider / RAG 引擎 | `evidence/` / `rag/` |

**结论：无混杂。** `workflow/`、`state/`、`evidence/`、`rag/` 全都不含保险专属判断；
保险知识一律下沉到 `domain/`、`catalog/` 与 Skill 级 rules。**这是本仓库结构上最扎实的一点，迁移时必须保持。**

### 3.4 Adapter 是否清晰？—— **是，且职责边界守住了**

- 10 个适配器**全部是纯 data transformation**（legacy envelope → canonical envelope），
  无业务决策。核对 `adapters/base.py` + 9 个具体适配器，职责单一。
- 引用方式**声明式**：`workflow/insurance-analysis.yaml:131`
  `post_adapter: adapters.report_generation_adapter.to_canonical`（唯一使用 post_adapter 的 stage）。
- 存在**两处** adapter 概念，需区分（不是问题，但值得记录）：
  1. `adapters/`（仓库根）——**跨层包络**，orchestrator 边界使用；
  2. Skill 内 translator（如 `.trae/skills/recommendation/scripts/product_candidates_to_candidate_solutions.py`、
     `.trae/skills/report-generation/scripts/upstream_results_adapter.py`）——**Skill 内输入归一**。
- **两者不应合并**：前者是「跨契约边界」，后者是「Skill 私有输入整形」。建议在 `docs/contract-layer.md` 补一句区分（文档级建议，非结构性）。

### 3.5 Contracts 是否分散？—— **否，层次清晰，有 1 处需清理**

| 契约类型 | 位置 | 数量 |
|---|---|---|
| Canonical Artifact 契约 | `contracts/*.schema.json` | 9 |
| Runtime 状态契约 | `state/case_state.schema.json` | 1 |
| Skill 级 I/O 契约 | `.trae/skills/*/schemas/*.schema.json` | 约 20 |
| 生成器 | `contracts/build_contracts.py` | 1 |
| **运行日志（误入库）** | `contracts/_build_log.txt` | 1 |

- 无重复定义：canonical 与 Skill 级是**两层**（跨 Skill 边界 vs Skill 内部），`docs/contract-layer.md` 已声明。
- 命名一致：`<artifact-type>.schema.json`，kebab-case，与 `AGENTS.md §1` 相符。
- **唯一问题**：生成器与生成物同目录。**判定：KEEP。** 记忆记载「重跑 `build_contracts.py` 会回退手改进生成物的内容」——
  同居反而让「生成源 vs 生成物」的漂移更容易被发现，拆开会让漂移更隐蔽。

### 3.6 Tests 与 Test Cases 是否混淆？—— **部分违反原则，但建议以约定而非搬迁收口**

| 目录 | 应有职责 | 实测 |
|---|---|---|
| `tests/` | 测试**程序** | ✅ 21 个 `test_*` / `run_*` 程序；⚠️ 但同时也含夹具（`contracts/fixtures/`、`e2e/fixtures/case-full-chain.json`、`evidence/cases/fixtures/`） |
| `test-cases/` | 测试**数据 / 场景** | ✅ 3 组 E2E 场景（case JSON + manifest + `kb-empty/` 夹具）；⚠️ **但混进了 3 个运行器**：`run_core_analysis_e2e.py`、`run_full_agent_e2e.py`、`run_product_recommendation_e2e.py` |

**关键判断：不要强制搬迁这 3 个运行器。** 理由：

1. 运行器与它的 `manifest.json` / `case-*.json` / `kb-empty/` **强同位耦合**：
   运行器通过 `REPO_ROOT` + manifest 里的相对路径读取同目录场景。
2. 迁移收益仅是「形式整齐」，代价是 `REPO_ROOT` 深度重算 + manifest 路径更新 + 回归重跑。
3. 更干净的收口方式是**把边界写成约定**（例如 `test-cases/README.md`：
   "本目录 = 场景数据 + 其专属运行器；共享夹具一律放 `tests/**/fixtures/`"），
   同时明确 `tests/e2e/fixtures/case-full-chain.json` 是**跨模块共享种子**（被 2 份 manifest + 2 个测试引用）。

### 3.7 Scripts 是否混乱？—— **不混乱，但唯一的一个脚本是失效的**

- `scripts/` 只有 **1 个**文件 → **不存在"混乱"**，也**不应为了形式建 4 个空目录**。
- 但该脚本 `run-regression.ps1`（737 行）**已失效且具破坏性**：
  - 第 21 行 `$IntakeDir = <repo>/01-client-intake` —— 该目录**在仓库中不存在**；
  - 第 26–28 行：若不存在则 `New-Item -ItemType Directory -Force` **自动重建**它；
  - 第 24 行 `$RunsDir = <repo>/01-client-intake/runs` —— 运行产物写进这个幽灵目录。
  - → **执行它会凭空复活一个历史遗留目录并写入产物**，污染仓库。
- 其测试用例读取路径（`.trae/skills/client-intake/evals/cases`）确实是有效的，
  说明它是「半迁移」状态：**脚本迁移到一半，目录却被删了**。
- **已有替代**：`tmp/run_regression.py`（29 套件统一回归，Step 3/4 权威口径）。

### 3.8 Docs 是否混乱？—— **有 3 类混杂，需一次归档**

| 类别 | 文件 | 判定 |
|---|---|---|
| **Portfolio 最终交付** | `architecture.md`、`architecture-v2.md`、`orchestration.md`、`contract-layer.md`、`evidence-provider.md`、`domain-pack.md`、`product-recommendation-v2.md`、`report-generation-v2.md`、`execution-trace.md`、`failure-taxonomy.md`、`step4-delivery.md`、`adr/*`(7) | **保留在 `docs/` 顶层**（面试官直接看得到） |
| **开发过程记录** | `step4-audit.md`、`step2-evidence-recommendation.md`、`step3-assembly.md` | 建议 → `docs/dev-notes/` |
| **只读历史基线** | `architecture-v2-audit.md`（记忆记载：Phase 0 只读基线，**永不修改**） | **原地保留**（移动即改变其基线路径，与"只读"原则冲突） |
| **失效 / 死链** | `client-intake/USAGE_GUIDE.md`（引 `01-client-intake/SOP.md`、`EVAL.md`）、`client-intake/REFACTOR_REPORT.md` | **不能移动**（被冻结 Skill 引用，见 §7）；建议只在文首加"历史文档"标注 —— **但那需要改文件，本次不动** |
| **索引失效** | `test-cases/TEST_CASES.md`（引 `01-client-intake/SOP.md`） | 可归档或重写（LOW 风险） |

### 3.9 Root Directory 是否过于拥挤？—— **不拥挤，无需处理**

- 根目录只有 **4 个文件**：`README.md`、`AGENTS.md`、`demo.py`、`.gitignore`。全部是**真正的项目入口/约定**。
- 没有 `setup.py` / 临时脚本 / 笔记文件散落。
- **`demo.py` 建议留在根**：它是唯一的 CLI 入口，`README.md §13` 与 `docs/step4-delivery.md` 都以
  `python demo.py demo-a` 为教学路径；根目录位置对「30 秒读懂」是**加分**而非减分。
  （`demo.py:24` 用 `REPO = HERE` 假定自己在仓库根，迁移到子目录需改此 1 行 + 改文档，收益为负。）

### 3.10 额外发现（不在任务书 9 项内，但属结构问题）

**P-A｜23 个运行产物被提交进仓库（最应立刻修）**

`AGENTS.md §7` 明文规定 `tmp/ 运行产物，不计入基线`，但以下 **23 个文件已被 git 跟踪**：

```
.trae/skills/coverage-gap-analysis/evals/cases/_unit_log.txt
.trae/skills/product-candidate-provider/evals/cases/_candidate_unit_log.txt
.trae/skills/recommendation/evals/cases/_pr_v2_unit_log.txt
.trae/skills/report-generation/evals/cases/_report_v2_unit_log.txt
.trae/skills/solution/evals/cases/_solution_unit_log.txt
contracts/_build_log.txt
test-cases/e2e/core-analysis/_e2e_core_log.txt
test-cases/e2e/full-agent/_full_agent_log.txt
test-cases/e2e/product-recommendation/_e2e_step2_log.txt
tests/contracts/_contract_test_log.txt
tests/contracts/_coverage_gap_dataset_log.txt
tests/contracts/_product_rec_dataset_log.txt
tests/contracts/_py_eval_log.txt
tests/contracts/_rg_sample.txt
tests/contracts/_solution_dataset_log.txt
tests/contracts/fixtures/_gen_log.txt
tests/e2e/_e2e_log.txt
tests/e2e/_orchestration_invariants_log.txt
tests/e2e/fixtures/_gen_log.txt
tests/evidence/_evidence_dataset_log.txt
tests/evidence/_evidence_invariants_log.txt
tests/workflow/_step3_mutation_log.txt
tests/workflow/_step3_orchestrator_self_eval_log.txt
```

**根因**（精确）：`.gitignore` 的规则是 `*.log`，而这些文件扩展名是 **`.txt`** —— 规则**漏掉了它们**。
→ 修法：或删文件 + 补 `.gitignore`（`_*_log.txt`、`_*_sample.txt`），或统一改名为 `.log`。

**P-B｜仓库无 Python 打包与无 CI**

- 无 `pyproject.toml` / `requirements.txt` / `setup.py` → 环境依赖只能靠 README 口述。
- 无 `.github/workflows/` → **有 29 个回归套件却没有 CI 门禁**。
- 对「可验证系统」的叙事而言，这是**叙事与结构之间的落差**（读者会问：那你怎么保证每次改动不掉绿？）。

**P-C｜`domain/insurance/kb/insurance_kb.sqlite` 是运行产物却被跟踪**

- `pack.yaml` 的 `rag_seed.output_db: kb/insurance_kb.sqlite` 明确说明它由 `seed_rag.py` 产出。
- 该目录内有 `.gitignore`，但 sqlite 仍被跟踪 → 需确认意图（可能是为了让读者免构建即可跑 demo）。

---

## 4. Proposed Structure（目标结构）

### 4.1 设计取舍说明（先讲"为什么"，再给树）

| 原则 | 在本方案中的落地 |
|---|---|
| **P1 Architecture-first** | 顶层目录 = 架构概念（Runtime / Knowledge / Domain / Contract / Adapter / Skill / Evaluation），而不是技术类型（`src` / `lib` / `utils`） |
| **P2 Low nesting** | 全部路径 ≤ 4 层（`runtime/state/case_state.py` = 3 层；`.trae/skills/<id>/scripts/x.py` = 4 层） |
| **P3 High cohesion** | Runtime 10 构件进一个 `runtime/`；Knowledge 两层进一个 `knowledge/` |
| **P4 Low coupling** | **只做 2 处需要动 import 的迁移**，其余全部是零代码影响的移动/删除；不做"重排式"迁移 |
| **P5 No junk drawer** | **不创建** `src/` `lib/` `core/` `common/` `utils/` `helpers/` `misc/`。无一例外 |
| **P6 Portfolio readability** | 30 秒可读出：Runtime / Skills / Knowledge / Domain / Contract / Evaluation / Docs 七块 |

**明确否掉的两个候选**（说明为什么不做）：

- ❌ **不把 `demo.py` 移进 `demos/`**：只有一个入口脚本，建目录属形式主义；且根位置更利于首屏阅读。
- ❌ **不把 `test-cases/` 的运行器搬进 `tests/`**：同位耦合强（manifest / 场景 / kb 夹具），收益低于风险（见 §3.6）。

### 4.2 目标结构

```
insurance-agent/
├── README.md                          ← Portfolio 主入口
├── AGENTS.md                          ← 项目级硬约定（改 Skill 前必读）
├── .gitignore                         ← 补充 _*_log.txt / _*_sample.txt / kb 产物
├── demo.py                            ← CLI Demo 入口（保留在根）
│
├── .trae/
│   └── skills/                        ← 【KEEP AS-IS】9 个 Specialist Skill
│       ├── client-intake/             ← 【冻结，禁止改动】
│       ├── requirement_analysis/      ← 【冻结 · 下划线遗留命名，不重命名】
│       ├── risk-analysis/
│       ├── coverage-gap-analysis/
│       ├── solution/
│       ├── product-candidate-provider/
│       ├── recommendation/
│       ├── report-generation/
│       └── knowledge-search/
│
├── runtime/                           ← 【NEW】Agent Runtime（= 原 workflow/ + state/ 的 state 层）
│   ├── __init__.py
│   ├── orchestrator.py                ← 唯一运行时循环
│   ├── tasks.py                       ← Task 实体 / 状态机 / max_attempts
│   ├── artifact_registry.py           ← ART-ID / lineage / evidence_refs / 冻结
│   ├── eval_engine.py                 ← 6 类确定性检查
│   ├── repair.py                      ← 局部重跑 + 预算（AUTO/REVIEW 分流）
│   ├── checkpoint.py                  ← save / load / validate
│   ├── trace.py                       ← 13 类 Execution Trace 事件 + JSONL
│   ├── observability.py               ← latency / skill call count / repair 统计
│   ├── insurance-analysis.yaml        ← 声明式工作流【单一真源】
│   ├── resources/
│   │   └── config/                    ← 外置规则：eval / repair / orchestrator
│   └── state/                         ← 【MOVED from state/】状态层
│       ├── __init__.py
│       ├── case_state.py              ← CaseState 唯一事实源
│       ├── transitions.py             ← 三条不变量
│       ├── store.py                   ← 持久化
│       └── case_state.schema.json     ← Runtime 状态契约
│
├── knowledge/                         ← 【NEW】Knowledge 层（= 原 evidence/ + rag/）
│   ├── __init__.py
│   ├── evidence/                      ← 【MOVED from evidence/】共享 Evidence Provider
│   │   ├── __init__.py
│   │   ├── request.py                 ← 模板化 KnowledgeQuery（禁自由文本）
│   │   ├── provider.py                ← KnowledgeQuery → KnowledgeEvidence
│   │   ├── loop.py                    ← 受控回环（保证调用方 artifact 不变）
│   │   ├── attribute_grounding.py     ← 属性级三态 grounding（V0.2）
│   │   └── resources/config/          ← evidence-request / attribute-grounding 规则
│   └── rag/                           ← 【MOVED from rag/】检索基础层
│       ├── __init__.py
│       ├── models.py
│       ├── store.py
│       └── engine.py
│
├── domain/
│   └── insurance/                     ← 【KEEP】Domain Pack
│       ├── pack.yaml
│       ├── playbook.md
│       ├── references/                ← 权威知识正文（= RAG 生产语料）
│       ├── overlays/
│       ├── scripts/                   ← 构建/校验/种子脚本
│       └── kb/                        ← 产出 sqlite（建议 gitignore）
│
├── catalog/                           ← 【KEEP】Demo Product Catalog（含版本字段）
├── contracts/                         ← 【KEEP】9 份 Canonical 契约 + 生成器 + skill-id-map
├── adapters/                          ← 【KEEP】10 个 pure data-transformation 适配器
│
├── evals/
│   └── agent-benchmark/               ← 【KEEP】33 Case + 9 Golden + baseline + 运行器
├── tests/                             ← 【KEEP】测试程序（+ 共享 fixture）
├── test-cases/                        ← 【KEEP】E2E 场景数据（+ 其专属运行器）
├── scripts/                           ← 【CLEANED】仅保留有效运维脚本；删除失效 run-regression.ps1
│
└── docs/
    ├── architecture.md                ← 架构总览（含 Deterministic/LLM/RAG/External 标记）
    ├── architecture-v2.md
    ├── orchestration.md
    ├── contract-layer.md
    ├── evidence-provider.md
    ├── domain-pack.md
    ├── execution-trace.md
    ├── failure-taxonomy.md
    ├── product-recommendation-v2.md
    ├── report-generation-v2.md
    ├── step4-delivery.md
    ├── repository-structure-audit.md  ← 本文件
    ├── adr/                           ← ADR-001 … ADR-007
    ├── dev-notes/                     ← 【NEW】过程记录：step4-audit / step2-* / step3-assembly
    ├── archive/                       ← 【NEW】失效历史（含 TEST_CASES.md 等）
    └── client-intake/                 ← 【KEEP · 不可移动】被冻结 Skill 引用
        ├── USAGE_GUIDE.md
        └── REFACTOR_REPORT.md
```

### 4.3 变化幅度

| 类型 | 数量 | 说明 |
|---|---|---|
| 顶层目录 新增 | 2 | `runtime/`、`knowledge/` |
| 顶层目录 消失 | 2 | `workflow/`、`state/`（并入 `runtime/`）；`evidence/`、`rag/`（并入 `knowledge/`） |
| 顶层目录 减少净额 | 2 | 15 → 15（`-4` 并入 `+2`） |
| 顶层目录 KEEP | 11 | `.trae` `domain` `catalog` `contracts` `adapters` `evals` `tests` `test-cases` `scripts` `docs` |
| 文件级移动 | 约 26 个文件（4 个目录整搬） | 详见 §6 |
| 需改 import 的文件 | **约 12 个** | 详见 §7 |
| 需改路径字面量 | **7 处** | 详见 §7 |
| 删除文件 | **24** | 23 运行日志 + 1 失效脚本 |
| 移动中涉及的"业务判断代码" | **0 行** | 全部是 import / 路径 / 文档引用 |

---

## 5. Architecture → Directory Mapping

| Architecture Concept | Proposed Directory | 现状 | 变动 |
|---|---|---|---|
| **Agent Runtime** | `runtime/` | `workflow/` + `state/` | **MOVE（合并）** |
| Orchestrator | `runtime/orchestrator.py` | `workflow/orchestrator.py` | MOVE |
| CaseState | `runtime/state/case_state.py` | `state/case_state.py` | MOVE |
| Artifact / Lineage | `runtime/artifact_registry.py` | `workflow/artifact_registry.py` | MOVE |
| Skill | `.trae/skills/<skill-id>/` | 同 | **KEEP** |
| Eval | `runtime/eval_engine.py` + `runtime/resources/config/eval.rules.json` | 同（在 `workflow/`） | MOVE |
| Repair | `runtime/repair.py` + `runtime/resources/config/repair.rules.json` | 同（在 `workflow/`） | MOVE |
| Checkpoint | `runtime/checkpoint.py` | `workflow/checkpoint.py` | MOVE |
| Trace | `runtime/trace.py` | `workflow/trace.py` | MOVE |
| Observability | `runtime/observability.py` | `workflow/observability.py` | MOVE |
| Workflow Definition | `runtime/insurance-analysis.yaml` | `workflow/insurance-analysis.yaml` | MOVE |
| **Insurance Domain** | `domain/insurance/` | 同 | **KEEP** |
| **Evidence** | `knowledge/evidence/` | `evidence/` | **MOVE** |
| **Knowledge / RAG** | `knowledge/rag/` | `rag/` | **MOVE** |
| **Product Catalog** | `catalog/` | 同 | **KEEP** |
| **Contract** | `contracts/` | 同 | **KEEP** |
| **Adapter** | `adapters/` | 同 | **KEEP** |
| **Tests（程序）** | `tests/` | 同 | **KEEP** |
| **Test Cases（数据）** | `test-cases/` | 同 | **KEEP**（+ 约定文档化） |
| **Benchmark** | `evals/agent-benchmark/` | 同 | **KEEP** |
| **Demo** | `demo.py`（根） | 同 | **KEEP** |
| **Documentation** | `docs/` + `docs/adr/` + `docs/dev-notes/` | `docs/` + `docs/adr/` | PARTIAL |
| **Ops Scripts** | `scripts/` | 同（但内容失效） | CLEAN |

---

## 6. OLD → NEW Migration Map

> 约定：RISK 分级 = `LOW`（无代码影响）/ `MEDIUM`（需改 import 或路径，但机械可验证）/ `HIGH` / `DO NOT MOVE`

### 6.1 M-1｜Agent Runtime 合并（`workflow/` + `state/` → `runtime/`）

| 字段 | 内容 |
|---|---|
| **OLD** | `workflow/`（13 文件）<br>`state/`（5 文件） |
| **NEW** | `runtime/`（control 层 8 模块 + `insurance-analysis.yaml` + `resources/config/`）<br>`runtime/state/`（`case_state.py` / `transitions.py` / `store.py` / `case_state.schema.json`） |
| **WHY** | ① 让"Agent Runtime 在哪"一眼可见（`runtime` 比 `workflow` 直白）；② 消除 Runtime 构件跨两个顶层目录的分散；③ `workflow → state` 是单向依赖，合并后可用相对 import（`from .state import ...`）降低耦合度 |
| **RISK** | **MEDIUM** |
| **DEPENDENCIES** | 见 §7.1（import 20 处 + 路径字面量 3 处 + YAML 1 处） |
| **收益** | 高（架构边界显式化）｜**成本**：12 文件 import 编辑 + 回归重跑 |

### 6.2 M-2｜Knowledge 层合并（`evidence/` + `rag/` → `knowledge/`）

| 字段 | 内容 |
|---|---|
| **OLD** | `evidence/`（7 文件）<br>`rag/`（4 文件） |
| **NEW** | `knowledge/evidence/`（`request` / `provider` / `loop` / `attribute_grounding` + `resources/config/`）<br>`knowledge/rag/`（`models` / `store` / `engine`） |
| **WHY** | ① `evidence` 与 `rag` 是同一层的两极（Provider 语义 vs 检索引擎），分列两个顶层目录对首读者不透明；② 汇成 `knowledge/` 后，README 的 `Evidence / RAG` 章节有了唯一对应的目录 |
| **RISK** | **MEDIUM** |
| **DEPENDENCIES** | 见 §7.2（import 16 处 + `REPO_ROOT` 1 处） |
| **收益** | 中高｜**成本**：14 文件 import 编辑 + 1 处 `REPO_ROOT` 层级修正 |

### 6.3 M-3｜删除 23 个被提交的运行产物

| 字段 | 内容 |
|---|---|
| **OLD** | 23 个 `_*_log.txt` / `_rg_sample.txt`（散落在 `.trae/skills/*/evals/cases/`、`contracts/`、`test-cases/e2e/*/`、`tests/**/`） |
| **NEW** | 不存在（并补 `.gitignore`） |
| **WHY** | 违反 `AGENTS.md §7`「tmp/ 运行产物，不计入基线」；它们是噪声，且会误导读者以为"这是基线的一部分" |
| **RISK** | **LOW**（无任何代码/配置引用它们——已 grep 确认） |
| **DEPENDENCIES** | 无。`rm` + `.gitignore` 补 `_*_log.txt` / `_*_sample.txt` |
| **收益** | 中（仓库信噪比）｜**成本**：0 |

### 6.4 M-4｜删除失效的 `scripts/run-regression.ps1`

| 字段 | 内容 |
|---|---|
| **OLD** | `scripts/run-regression.ps1`（737 行，client-intake v1.x 回归壳） |
| **NEW** | 删除（`scripts/` 暂时为空；后续只放**有效**运维脚本） |
| **WHY** | ① 引用的 `01-client-intake/` 已不存在，且脚本会 `New-Item -Force` **重建该幽灵目录**并写入产物 → **运行即污染仓库**；② 已被 `tmp/run_regression.py`（29 套件）取代 |
| **RISK** | **LOW–MEDIUM**（删除代码文件，但有 4 处文档引用它 → 需同步处理，见 §12 Phase 3） |
| **DEPENDENCIES** | `docs/client-intake/USAGE_GUIDE.md`(4 处) · `docs/client-intake/REFACTOR_REPORT.md`(2 处) · `docs/architecture-v2-audit.md`(1 处, **只读基线不改**) · `docs/step4-audit.md`(1 处) |
| **收益** | 中高（消除一个会破坏仓库的脚本）｜**成本**：低 |

### 6.5 M-5｜文档分层（`docs/` → `docs/dev-notes/` + `docs/archive/`）

| 字段 | 内容 |
|---|---|
| **OLD** | `docs/step4-audit.md`、`docs/step2-evidence-recommendation.md`、`docs/step3-assembly.md`<br>`test-cases/TEST_CASES.md`（内容已失效） |
| **NEW** | `docs/dev-notes/step4-audit.md` 等 3 个<br>`docs/archive/TEST_CASES.md` |
| **WHY** | 把 Portfolio 交付物与开发过程记录分开，让面试官在 `docs/` 顶层只看到结论性文档 |
| **RISK** | **LOW**（纯文档，无代码引用） |
| **DEPENDENCIES** | `README.md` 的「文档导航」表需同步（若表中引用了这 3 个文件则更新路径） |
| **收益** | 中｜**成本**：低 |

### 6.6 M-6｜补 `.gitignore`：运行时客户数据与知识库产物

| 字段 | 内容 |
|---|---|
| **OLD** | `client-intake-data/clients/` 未被忽略；`domain/insurance/kb/*.sqlite` 已被跟踪 |
| **NEW** | `.gitignore` 增加：`client-intake-data/clients/*`（保留 `README.md`）、`domain/insurance/kb/*.sqlite` |
| **WHY** | 二者都是**运行产物**（真实客户数据 / 脚本构建产物），`client-intake-data/README.md` 自己就写明"建议版本库忽略" |
| **RISK** | **LOW–MEDIUM**（`kb/insurance_kb.sqlite` 若被忽略，读者需先跑 `seed_rag.py` 才能用生产 KB —— 需确认是否可接受） |
| **DEPENDENCIES** | `domain/insurance/pack.yaml:148`（`output_db` 声明）|
| **收益** | 中｜**成本**：0 |

### 6.7 NOT MOVED（明确不迁移）

| OLD | 判定 | 原因 |
|---|---|---|
| `.trae/skills/requirement_analysis/` | **DO NOT MOVE / DO NOT RENAME** | `AGENTS.md §1 + §4` 冻结；`skill-id-map.json` 运行时映射；adapter / 测试 / 文档多处硬引用 |
| `.trae/skills/requirement_analysis/REFACTOR_REPORT.md` | **DO NOT MOVE** | 被 `check-skill-anatomy.ps1:106` **显式豁免**；移出需改冻结 Skill 的守卫脚本 |
| `.trae/skills/client-intake/**` | **DO NOT MOVE** | AGENTS §4 冻结；`client-intake-data/` 路径被其 4 份文档硬编码 |
| `docs/client-intake/*.md` | **DO NOT MOVE** | 被冻结的 `client-intake/resources/interaction-nodes.md:50` 引用；移动即产生死链且无法修 |
| `docs/architecture-v2-audit.md` | **DO NOT MOVE** | Phase 0 **只读基线**，移动即改变其作为基线的路径语义 |
| `catalog/product-catalog.v0.1.json` | **DO NOT MOVE / DO NOT RENAME** | 2 份 rules JSON + 2 处代码默认值硬引用；收益 0 |
| `contracts/build_contracts.py` | **DO NOT MOVE** | 与生成物同居是**有意设计**（记忆：拆分会让"生成源 vs 生成物"漂移更隐蔽） |
| `contracts/*.schema.json`（9 个文件名） | **DO NOT RENAME** | `insurance-analysis.yaml` 逐 stage 声明路径；`tests/contracts/*` 5 处引用 |
| `adapters/*.py`（10 个文件名） | **DO NOT RENAME** | `insurance-analysis.yaml:131` 的 `post_adapter:` 路径引用 |
| `tests/e2e/fixtures/case-full-chain.json` | **DO NOT MOVE** | 跨模块共享种子：2 份 manifest (`seeds_file`) + 2 个测试硬编码 |
| `test-cases/e2e/full-agent/kb-empty/` | **DO NOT MOVE** | 2 份 manifest (`empty_kb`) + `run_full_agent_e2e.py:264` 兜底 + `test_step3_orchestrator_self_eval.py:34` |
| `demo.py`（根） | **KEEP** | 唯一 CLI 入口；`REPO = HERE` 假定在根（`demo.py:24`）；根位置利于首屏阅读 |
| `test-cases/**/run_*.py`（3 个运行器） | **KEEP** | 与同目录 manifest / 场景 / kb 夹具强同位耦合（见 §3.6） |
| `tmp/` | **KEEP（gitignored）** | 运行产物区，已是正确状态 |
| `.trae/internal/` | **KEEP（gitignored）** | 调试脚本，已不在仓库中 |

---

## 7. Dependency / Path Risk（任务书 §八）

> 这是迁移风险的全部依据。**每一项均已实测**，非推测。

### 7.1 M-1（Runtime）依赖清单

**A. Python import（20 处 / 12 文件）**

| 现 import | 需改为 | 所在文件 |
|---|---|---|
| `from state import case_state as cs` | `from .state import case_state as cs`（包内）<br>`from runtime.state import case_state as cs`（包外） | `workflow/artifact_registry.py:15`<br>`workflow/checkpoint.py:20`<br>`workflow/eval_engine.py:27`<br>`workflow/orchestrator.py:40`<br>`workflow/tasks.py:17` |
| `from state import transitions` | 同上 | `workflow/artifact_registry.py:16`、`workflow/orchestrator.py:41` |
| `from state import store` | 同上 | `workflow/checkpoint.py:21` |
| `from workflow import ...` | `from runtime import ...` | `demo.py:28,29,30`<br>`evals/agent-benchmark/run_agent_benchmark.py`<br>`evals/agent-benchmark/run_golden_cases.py`<br>`test-cases/e2e/full-agent/run_full_agent_e2e.py`<br>`tests/e2e/run_e2e.py`<br>`tests/e2e/test_orchestration_invariants.py`<br>`tests/workflow/test_step3_mutation.py`<br>`tests/workflow/test_step3_orchestrator_self_eval.py`<br>`tests/workflow/test_step4_phase2_trace.py`<br>`tests/workflow/test_step4_phase7_evidence_grounding.py`<br>`tests/workflow/test_step4_phase9_observability.py`<br>`tests/workflow/test_step4_phase13_guardrails.py` |
| 包内相对 import（**不变**） | — | `workflow/checkpoint.py:22-24`、`workflow/orchestrator.py:42-46`、`workflow/repair.py:19`、`workflow/tasks.py:18` |

**B. 路径字面量 / 配置（4 处）**

| 位置 | 现值 | 需改为 |
|---|---|---|
| `workflow/insurance-analysis.yaml:24` | `state_schema: state/case_state.schema.json` | `runtime/state/case_state.schema.json` |
| `workflow/insurance-analysis.yaml:59,71,85,109,124` | `entrypoint: .trae/skills/...` | **不变**（Skill 未移动） |
| `workflow/orchestrator.py:36-37` | `REPO_ROOT = dirname(HERE)`，`HERE = workflow/` | **不变**（`runtime/` 与 `workflow/` **同深度**，1 级即可） |
| `evals/agent-benchmark/manifest.json:4,6` | `seeds_file` / `empty_kb` 指向 `tests/`·`test-cases/` | **不变** |

**C. 目录深度校验（关键）**

| 迁移 | 深度变化 | `REPO_ROOT` 是否受影响 |
|---|---|---|
| `workflow/` → `runtime/` | 不变（1 级） | ✅ 不受影响 |
| `state/` → `runtime/state/` | +1（0 → 1 级） | ⚠️ `state/` 内**无** `REPO_ROOT` / `__file__` 依赖 → **不受影响**（已实测：`state/*.py` 只 import 标准库 + 同包相对模块） |

### 7.2 M-2（Knowledge）依赖清单

**A. Python import（16 处 / 14 文件）**

| 现 import | 需改为 | 引用者 |
|---|---|---|
| `from rag import ...` | `from knowledge.rag import ...` | `.trae/skills/knowledge-search/scripts/invoke-knowledge-search.py`<br>`.trae/skills/knowledge-search/scripts/run_knowledge_search_dataset.py`<br>`domain/insurance/scripts/build_domain_engine.py`<br>`domain/insurance/scripts/seed_rag.py`<br>`domain/insurance/scripts/validate_pack.py`<br>`tests/contracts/_gen_fixtures.py`<br>`tests/contracts/test_knowledge_evidence_traceability.py` |
| `from evidence import ...` | `from knowledge.evidence import ...` | `.trae/skills/product-candidate-provider/scripts/product_candidate_engine.py`<br>`test-cases/e2e/product-recommendation/run_product_recommendation_e2e.py`<br>`tests/contracts/test_knowledge_evidence_contract.py`<br>`tests/contracts/test_knowledge_query_contract.py`<br>`tests/evidence/run_evidence_dataset.py`<br>`tests/evidence/test_evidence_invariants.py`<br>`tests/workflow/test_step4_phase7_evidence_grounding.py`<br>`tests/workflow/test_step4_phase8_catalog_version.py`<br>`workflow/orchestrator.py` |

**B. 路径 / 层级（关键：1 处必须修正）**

| 位置 | 现值 | 问题 | 需改为 |
|---|---|---|---|
| `evidence/provider.py:25-26` | `HERE = dirname(__file__)`<br>`REPO_ROOT = dirname(HERE)` | 现在 `evidence/` 距根 1 级 → 正确。<br>迁到 `knowledge/evidence/` 后距根 **2 级** → `REPO_ROOT` 会指向 `knowledge/` ❌ | `REPO_ROOT = os.path.dirname(os.path.dirname(HERE))` |
| `evidence/provider.py:31,33,34` | `.trae/skills/knowledge-search/scripts/...`<br>`contracts/knowledge-evidence.schema.json`<br>`contracts/knowledge-query.schema.json` | 依赖 `REPO_ROOT` → 随上一行修正而自动恢复 | 不变（只要 REPO_ROOT 对） |
| `evidence/request.py:20-21` | `RULES_PATH = HERE/resources/config/...` | **HERE 相对** → 整目录搬迁安全 | 不变 |
| `evidence/attribute_grounding.py:32-33` | `DEFAULT_RULES = HERE/resources/config/...` | **HERE 相对** → 安全 | 不变 |
| `rag/**` | 无 `__file__` / `REPO_ROOT` 依赖（仅 `rag/store.py:103` 的 `os.path.join` 用于 ingest 入参） | 整目录搬迁安全 | 不变 |

> ⚠️ **风险提示（本审计最有价值的一条）**：`REPO_ROOT` 的 `dirname` 层数是**层级敏感**的，
> 历史上已因此发生过 `report_generation_engine.REPO_ROOT` 多算一级的潜伏 bug（Step 4 P13 才暴露）。
> `evidence/` 的层级一旦加深，**必须同步修正**，否则 `provider` 会静默找不到 knowledge-search 入口与 2 份契约。

### 7.3 文件系统 / 其它依赖（两项共同）

| 类型 | 检查结果 |
|---|---|
| **相对 import** | `workflow/*` 内部用 `from . import X`（相对）→ 整目录改名安全；`state/` 内用 `from . import X` → 进 `runtime/state/` 后仍成立 |
| **`pathlib` / `parents[n]`** | 仅 `test-cases/e2e/core-analysis/run_core_analysis_e2e.py:21-27` 用 `Path(__file__).resolve().parents[3]` —— 该文件**不在迁移范围**，不受影响 |
| **`subprocess` 调用** | 无跨目录 subprocess 调用（引擎按 `importlib.util.spec_from_file_location` 加载，路径由 YAML / REPO_ROOT 派生） |
| **CLI 入口** | `demo.py`（保留在根，`REPO = HERE` 仍正确） |
| **PowerShell 脚本** | Skill 内 `.ps1` **全部使用 `$PSScriptRoot` 相对推导**，与本次迁移的目录无关（Skill 未移动）；唯一受影响的是被删除的 `scripts/run-regression.ps1` |
| **文档引用** | `README.md §17「项目结构」` 必须重写（逐行描述旧结构）；`docs/step4-delivery.md`、`docs/step4-audit.md`、`docs/architecture.md` 中若有旧目录树也需同步 |
| **GitHub 链接** | 文档内存在 `file:///D:/Workspace/insurance-agent/01-client-intake/...` 这类**绝对路径死链**（client-intake 历史文档）→ 记录为历史文档即可，不在本次修 |
| **生成文件** | `contracts/*.schema.json` 由 `build_contracts.py` 生成；本次**不移动也不重生成**，避免回退手改内容（记忆硬规则） |

### 7.4 迁移风险总表（任务书 §九）

| File / Directory | Move | Risk | Reason |
|---|---|---|---|
| `workflow/` → `runtime/` | **YES** | **MEDIUM** | 20 处 import（跨 12 文件）+ YAML 1 处；同深度，`REPO_ROOT` 不受影响；29 套件可全量验证 |
| `state/` → `runtime/state/` | **YES** | **MEDIUM** | 与上项同批；`state/` 无 `REPO_ROOT` 依赖（实测），仅 import 改名 |
| `evidence/` → `knowledge/evidence/` | **YES** | **MEDIUM** | 9 处 import + **`provider.py` `REPO_ROOT` 层级必须修正**（否则静默失效） |
| `rag/` → `knowledge/rag/` | **YES** | **MEDIUM** | 7 处 import；无 `__file__` 依赖，整目录搬迁安全 |
| 23 个 `_*_log.txt` | **DELETE** | **LOW** | 无任何引用（已 grep 确认）；补 `.gitignore` |
| `scripts/run-regression.ps1` | **DELETE** | **LOW–MEDIUM** | 会重建幽灵目录；4 处文档引用需同步 |
| `docs/step4-audit.md` 等 3 个 → `docs/dev-notes/` | **YES** | **LOW** | 纯文档；可能需同步 README 导航表 |
| `test-cases/TEST_CASES.md` → `docs/archive/` | **YES** | **LOW** | 内容已失效（引用不存在的 `01-client-intake/SOP.md`） |
| `.gitignore` 补 2 条规则 | — | **LOW** | 需确认 `kb/*.sqlite` 忽略是否影响读者上手 |
| `catalog/product-catalog.v0.1.json` | **NO** | **HIGH** | 2 份 rules JSON + 2 处代码默认值硬引用；收益 0 |
| `contracts/*.schema.json`（改名） | **NO** | **HIGH** | YAML 逐 stage 声明 + 5 处测试引用 |
| `adapters/*.py`（改名） | **NO** | **HIGH** | `insurance-analysis.yaml:131` 的 `post_adapter` 路径 |
| `tests/e2e/fixtures/case-full-chain.json` | **NO** | **HIGH** | 2 份 manifest `seeds_file` + 2 个测试硬编码 |
| `test-cases/e2e/full-agent/kb-empty/` | **NO** | **HIGH** | 2 份 manifest `empty_kb` + 1 处代码兜底 + 1 个测试常量 |
| `.trae/skills/**`（整体或改名） | **NO** | **DO NOT MOVE** | AI IDE 发现约定 + AGENTS §7；`client-intake`/`requirement_analysis` 冻结 |
| `.trae/skills/requirement_analysis/REFACTOR_REPORT.md` | **NO** | **DO NOT MOVE** | 被 `check-skill-anatomy.ps1:106` 显式豁免；改动即触碰冻结 Skill |
| `docs/client-intake/*` | **NO** | **DO NOT MOVE** | 被冻结 Skill 的 `interaction-nodes.md:50` 引用 |
| `docs/architecture-v2-audit.md` | **NO** | **DO NOT MOVE** | Phase 0 只读基线 |
| `contracts/build_contracts.py` | **NO** | **DO NOT MOVE** | 与生成物同居是防漂移的设计 |
| `client-intake-data/` | **NO** | **DO NOT MOVE** | 被冻结 Skill（client-intake + RA 夹具）硬编码 |
| `demo.py` | **NO** | **KEEP** | 唯一 CLI 入口；`REPO = HERE` 假定在根 |
| `test-cases/**/run_*.py` | **NO** | **KEEP** | 与同目录场景/manifest/kb 夹具强同位耦合 |
| `tmp/`、`.trae/internal/` | **NO** | **KEEP** | 已 gitignore，状态正确 |

---

## 8. Legacy Compatibility（任务书 §十）

### 8.1 Legacy Paths 清单

| Legacy 对象 | 性质 | 证据 | 处置 |
|---|---|---|---|
| `.trae/skills/requirement_analysis/` | **历史命名**（下划线 vs kebab-case） | `AGENTS.md §1` 明文豁免 | **保留**。`contracts/skill-id-map.json` 已把 canonical id `requirement-analysis` 与物理目录解耦，**不需要**改目录 |
| `workflow/insurance-analysis.yaml:103` `legacy_skill: recommendation` | **运行时 legacy 映射** | YAML 内显式声明 | **保留**（迁移后随 YAML 一起进 `runtime/`） |
| `adapters/requirement_analysis_adapter.py` | 命名沿用 legacy 名 | 与上一条同源 | **保留**（文件名即映射关系） |
| `scripts/run-regression.ps1` | **半迁移遗留** | 引用已删除的 `01-client-intake/` | **删除**（见 §6.4） |
| `test-cases/TEST_CASES.md` | **失效遗留** | 引用已删除的 `01-client-intake/SOP.md` / `EVAL.md` | 归档到 `docs/archive/` |
| `docs/client-intake/{USAGE_GUIDE,REFACTOR_REPORT}.md` | **失效历史文档** | 多处 `file:///D:/.../01-client-intake/SOP.md` 绝对路径死链 | **不能移动**（被冻结 Skill 引用）→ 仅在文首标注"历史文档"（**本次不动**） |
| `state/case_state.schema.json` 中 `workflow_stages` 等字段 | 命名沿用 `workflow` 词 | Schema 字段名 | **不改**（改字段是契约变更，超出结构审计范围） |
| `client-intake-data/`（v1.2 多客户结构） | 运行时目录约定 | `client-intake/references/06-state-file-rules.md:41` 明确 v1.0/v1.1 顶层三文件已删除 | **保留**（当前即为 v1.2 正确形态） |

### 8.2 Legacy 处置原则（本次采用）

> **无法证明安全 → 不移动。**

本次审计的每一条 `DO NOT MOVE` 都基于**可验证证据**（grep 到的实际引用行号），
而不是「感觉可能有问题」。共 13 项 `DO NOT MOVE`，全部在 §6.7 / §7.4 给出引用证据。

---

## 9. Files to Keep（KEEP AS-IS）

| # | 对象 | 原因 |
|---|---|---|
| 1 | `README.md` | Portfolio 主入口。内容需**更新**（§17 项目结构），但文件本身保留 |
| 2 | `AGENTS.md` | 项目级硬约定，被本审计反复引用为判据 |
| 3 | `.gitignore` | 保留；仅**追加**规则（M-3 / M-6） |
| 4 | `.trae/skills/`（整目录及全部 9 个 Skill） | AI IDE 发现约定（`AGENTS.md §7`"不是仓库根的 skills/"）+ WorkBuddy 目录联接 |
| 5 | `.trae/skills/client-intake/` | `AGENTS.md §4` 冻结 |
| 6 | `.trae/skills/requirement_analysis/` | `AGENTS.md §1 + §4` 冻结 + `skill-id-map.json` 运行时映射 |
| 7 | `.trae/skills/requirement_analysis/REFACTOR_REPORT.md` | 被 `check-skill-anatomy.ps1:106` 显式豁免 |
| 8 | `docs/client-intake/*.md` | 被冻结 Skill 的 `interaction-nodes.md:50` 引用 |
| 9 | `docs/architecture-v2-audit.md` | Phase 0 只读基线 |
| 10 | `contracts/`（含 `build_contracts.py` 与 9 份 schema 文件名） | YAML / 测试 / 生成器同居设计 |
| 11 | `adapters/`（10 文件 + 文件名） | `post_adapter` 路径引用 |
| 12 | `catalog/product-catalog.v0.1.json` | 4 处硬引用 |
| 13 | `domain/insurance/`（含 `references/`、`pack.yaml`） | Domain Pack 单一事实源；`rag_seed.references_dir` 引用 |
| 14 | `client-intake-data/`（路径） | 冻结 Skill 硬编码 |
| 15 | `tests/` + `test-cases/`（结构） | 拆分合理；仅需文档化边界 |
| 16 | `test-cases/**/run_*.py` | 与场景强同位耦合 |
| 17 | `evals/agent-benchmark/` | Benchmark + Golden + baseline 的完整单元 |
| 18 | `demo.py`（根位置） | 唯一 CLI 入口 |
| 19 | `tmp/`（gitignored） | 运行产物区，状态正确 |
| 20 | `.trae/internal/`（gitignored） | 调试脚本，已在仓库之外 |

---

## 10. Files to Move

| # | OLD | NEW | 文件数 | Risk |
|---|---|---|---|---|
| 1 | `workflow/*.py` + `insurance-analysis.yaml` + `resources/` | `runtime/`（同结构） | 13 | MEDIUM |
| 2 | `state/*` | `runtime/state/` | 5 | MEDIUM |
| 3 | `evidence/*` | `knowledge/evidence/` | 7 | MEDIUM |
| 4 | `rag/*` | `knowledge/rag/` | 4 | MEDIUM |
| 5 | `docs/step4-audit.md` | `docs/dev-notes/step4-audit.md` | 1 | LOW |
| 6 | `docs/step2-evidence-recommendation.md` | `docs/dev-notes/step2-evidence-recommendation.md` | 1 | LOW |
| 7 | `docs/step3-assembly.md` | `docs/dev-notes/step3-assembly.md` | 1 | LOW |
| 8 | `test-cases/TEST_CASES.md` | `docs/archive/TEST_CASES.md` | 1 | LOW |
| **合计** | | | **33 个文件（4 个目录整搬 + 4 个单文件）** | |

---

## 11. Files to Delete

| # | 文件 | 数量 | 理由 | Risk |
|---|---|---|---|---|
| 1 | `_*_log.txt` / `_*_sample.txt`（运行日志） | 23 | 违反 `AGENTS.md §7`；`.gitignore` 的 `*.log` 规则**漏掉了 `.txt`**；无任何引用 | LOW |
| 2 | `scripts/run-regression.ps1` | 1 | 引用已删除的 `01-client-intake/`，执行会**重建幽灵目录**并污染仓库；已被 `tmp/run_regression.py` 取代 | LOW–MEDIUM |
| **合计** | | **24** | | |

**不删除但需决策**（列入 Open Questions）：
- `domain/insurance/kb/insurance_kb.sqlite`（运行产物，但可能是有意提供"开箱即跑"）
- `docs/client-intake/*`（失效但被冻结 Skill 引用）
- `test-cases/TEST_CASES.md`（建议归档而非删除）

---

## 12. Migration Plan（**不执行，仅供下一步决策**）

### Phase 0 — 前置校验（幂等、零改动）
1. `git status` 必须 clean；记录 `git rev-parse HEAD` 作为回滚点。
2. 跑一次基线：`python tmp/run_regression.py` → 确认 **29/29 ALL GREEN**，记录各套件通过数。
3. 记录 `git ls-files | wc -l` = **580**（迁移后应对齐预期）。

### Phase 1 — Safe Moves（零业务代码影响）
1. **删除 23 个运行日志**（M-3）+ `.gitignore` 补 `_*_log.txt`、`_*_sample.txt`。
2. **删除 `scripts/run-regression.ps1`**（M-4）。
   - ⚠️ 先确认 4 处文档引用中，除 `docs/architecture-v2-audit.md`（只读基线，不动）外，
     其余是否改为"已废弃"注记或随文档一起归档。
3. **新建 `docs/dev-notes/`**，移入 3 个过程文档（M-5）。
4. **新建 `docs/archive/`**，移入 `test-cases/TEST_CASES.md`。
5. **`.gitignore` 补运行时数据规则**（M-6）——**需先确认** `kb/*.sqlite` 是否要忽略。
6. 校验点：`git status` 只显示预期的 delete/rename；**不跑回归（无代码变化）**。

### Phase 2 — Path / Import Updates（需改代码，唯一有风险的一步）
> 建议 **M-1 与 M-2 分开两次提交**，便于二分定位回归失败。

**2A — M-1 Runtime 合并**
1. `git mv workflow runtime`
2. `git mv state runtime/state`
3. 改包外 import：12 个文件（§7.1.A）
4. 改包内 import：`runtime/*.py` 的 `from state import` → `from .state import`；`runtime/state/*.py` 保持 `from . import`
5. 改 YAML：`state_schema: state/case_state.schema.json` → `runtime/state/case_state.schema.json`
6. 改文档：`README.md §17`、`docs/architecture.md`、`docs/orchestration.md`、`docs/execution-trace.md`、`docs/step4-delivery.md` 中出现的旧路径
7. 校验点：跑 `tests/contracts` + `tests/e2e` + `tests/workflow`（**先跑这 3 组**，它们是 import 变更的直接受害者）

**2B — M-2 Knowledge 合并**
1. `git mv evidence knowledge/evidence`
2. `git mv rag knowledge/rag`
3. 新增 `knowledge/__init__.py`
4. 改 16 处 import（§7.2.A）
5. **修正 `knowledge/evidence/provider.py:26` 的 `REPO_ROOT` 为 2 级 `dirname`**（§7.2.B）
6. 校验点：跑 `tests/evidence` + `tests/contracts` + `tests/workflow/test_step4_phase7*` + `tests/workflow/test_step4_phase8*`

**2C — 全量回归**
- `python tmp/run_regression.py` → 必须回到 **29/29 ALL GREEN**
- 额外人工校验 3 个数：
  - `python evals/agent-benchmark/run_agent_benchmark.py` → **33/33**，硬门违反 **0**
  - `python evals/agent-benchmark/run_golden_cases.py` → **9/9**
  - `python test-cases/e2e/full-agent/run_full_agent_e2e.py` → **71/71**
- 冒烟：`python demo.py demo-a`、`python demo.py demo-b` 均 exit 0

### Phase 3 — Tests / Scripts / Docs updates
1. 更新 `README.md §17「项目结构」`为新的目标树（**这是唯一对外可见的结构声明**）。
2. 更新 README「文档导航」表中受 M-5 影响的路径。
3. 新增 `tests/README.md`（或 `AGENTS.md` 增补）写明 **`tests/` = 程序，`test-cases/` = 数据（+ 专属运行器）** 的边界约定。
4. 校验：`grep -rn "workflow/" --include=*.md docs README.md` 应无残留旧路径（除历史文档）。

### Phase 4 — Delete Obsolete
- Phase 1 已完成的删除在此确认（`git rm` 已生效、`.gitignore` 生效、`git status` clean）。
- 确认 `git ls-files | wc -l` 落在预期值（580 − 24 + 0 = **556**，另 `+1` 本审计文档 = **557**）。

### Phase 5 — Regression & Freeze
1. 全量回归 **29/29**；3 个重点套件（benchmark / golden / full-agent）数字不变。
2. `python -c "import runtime, knowledge"` 级别的 import 冒烟（包可导入）。
3. `docs/repository-structure-audit.md` 追加"迁移执行记录"小节（实际移动清单 + 回归证据）。
4. 提交策略建议：`Phase 1` / `Phase 2A` / `Phase 2B` / `Phase 3` **4 个独立提交**，任一失败可精确回滚。

---

## 13. Regression Plan

| 层级 | 动作 | 判据 |
|---|---|---|
| **L0 结构自检** | `git ls-files` 计数 + `git status` clean | 文件数 = 预期；无意外 untracked |
| **L1 Import 冒烟** | `python -c "import runtime.orchestrator, runtime.state.case_state, knowledge.rag, knowledge.evidence"` | 无 ImportError |
| **L2 单元/契约** | `tests/contracts`（11）+ `tests/evidence`（2）+ `tests/workflow`（5） | 全绿 |
| **L3 不变量/E2E** | `tests/e2e`（2）+ `test-cases/e2e/*`（3 运行器） | 全绿 |
| **L4 权威回归** | `python tmp/run_regression.py` | **29/29 ALL GREEN** |
| **L5 关键数字不回退** | Agent Benchmark / Golden / Full-Agent E2E | **33/33** / **9/9** / **71/71**；硬门违反 **0** |
| **L6 Demo 冒烟** | `python demo.py demo-a` / `demo-b` | exit 0；demo-b 仍为 `NEEDS_REVIEW` |
| **L7 路径残留扫描** | `grep -rn "from workflow\|from state\|from evidence import\|from rag import"` | 0 命中（历史文档除外） |
| **L8 配置路径扫描** | `grep -rn "state/case_state.schema.json\|"catalog_path"" .` | 全部指向新路径且可解析 |

**回归基线（迁移前必须先记录）**：

```
tmp/run_regression.py ........... 29/29 ALL GREEN
full-agent E2E .................. 71/71
product-recommendation E2E ...... 61/61
Agent Benchmark ................. 33/33（hard gates 违反 0）
Golden Cases .................... 9/9
git tracked files ............... 580
```

> ⚠️ 若任一数字下降：**先分类 implementation bug / test bug / contract conflict，修正确的那一层，
> 绝不修改 baseline 使其变绿**（沿用 `AGENTS.md §6` 与 Step 3/4 的既有纪律）。

---

## 14. Open Questions（需你决策）

| # | 问题 | 选项 | 我的建议 |
|---|---|---|---|
| Q1 | **是否执行 M-1/M-2（Runtime + Knowledge 合并）？** 这是唯一需要改 import 的迁移 | (a) 执行；(b) 仅做 Phase 1（零风险项）；(c) 全部不做，仅文档化边界 | **(a)** —— 结构收益最大，且 29 套件能给出确定性验证；但若你更看重"不再动代码"，(b) 也是完全站得住的工程选择 |
| Q2 | `evals/` 是否重命名为 `benchmark/`（消除与 `.trae/skills/*/evals/` 的同名歧义）？ | (a) 保留；(b) 改名 | **(a) 保留**。`evals/agent-benchmark/` 已自描述；改名收益低、要动 README/docs/`demo.py:32` |
| Q3 | `domain/insurance/kb/insurance_kb.sqlite`（运行产物）是否 gitignore？ | (a) 忽略（读者需跑 `seed_rag.py`）；(b) 保留（开箱可跑） | **(b) 保留**，但在 `catalog/README.md`、`domain/insurance/pack.yaml` 附近标注"构建产物，可由脚本重建"。理由：Portfolio 场景下"clone 即可跑"价值更高 |
| Q4 | 是否补 CI（`.github/workflows/regression.yml` 跑 `tmp/run_regression.py`）？ | (a) 补；(b) 不补 | **(a) 补**。29 套件无门禁是"可验证系统"叙事最明显的结构缺口。注意：`tmp/` 被 gitignore → 需把回归 harness 从 `tmp/` 提到 `scripts/`（这是**新增**，不属本次只读范围） |
| Q5 | 是否补 Python 打包（`pyproject.toml`，把各包声明为 namespace package）？ | (a) 补；(b) 不补 | 倾向 **(b) 不补**：当前全靠 `sys.path.insert(0, REPO_ROOT)` + `importlib` 加载，改为正式包会牵动所有 Skill 引擎的加载方式，风险远大于收益。可在 README「Limitations」说明 |
| Q6 | `test-cases/**/run_*.py` 是否搬进 `tests/` 以严格满足"tests=程序 / test-cases=数据"？ | (a) 搬；(b) 保留 + 文档化约定 | **(b) 保留**（同位耦合强、收益低） |
| Q7 | `docs/client-intake/` 两份失效文档如何处理？（被冻结 Skill 引用，不能移动） | (a) 原样保留；(b) 修 `interaction-nodes.md` 的引用（**需要改冻结 Skill，被禁止**）；(c) 在文档内加"历史"标注 | **(a) 原样保留**，本期不动；把它记入「Remaining Technical Debt」 |
| Q8 | 是否需要在 `runtime/` 内保留 `state/` 子目录，还是把 4 个 state 文件**平铺**进 `runtime/`？ | (a) `runtime/state/`；（b) 平铺 `runtime/` | **(a)** —— 保留 state 层边界（`state/` 是纯状态模型，`runtime/` 根是控制循环），且平铺会让 `runtime/` 根出现 12 个文件，可读性下降 |

---

## 15. 附：审计可复现命令

```bash
# 仓库规模（只统计被跟踪内容）
git ls-files | wc -l                                   # 580
git ls-files | awk -F/ '{print $1}' | sort | uniq -c   # 各目录文件数
git status --short                                     # clean

# 根目录文件
git ls-files | grep -v /

# Skill 骨架一致性
for d in .trae/skills/*/; do ls "$d"; done

# Runtime 依赖（单向：workflow -> state）
grep -n "^from state" workflow/*.py
grep -rn "workflow" state/            # 仅有变量名，无 import

# 路径字面量（迁移风险面）
grep -rn --include=*.py -E '"(evals|test-cases|tests|workflow|state|evidence|rag|domain|catalog|contracts)(\\|/)' . | grep -v /tmp/
grep -rn --include=*.json --include=*.yaml -E '"(catalog_path|state_schema|seeds_file|empty_kb|entrypoint)"' . | grep -v /tmp/

# 误入库的运行产物
git ls-files | grep -E '(^|/)_[^/]*\.(txt|json)$'

# 失效脚本的幽灵路径
grep -n "01-client-intake" scripts/run-regression.ps1
```

---

**审计结束。未执行任何迁移，仓库结构与业务代码保持原状（`git status` clean）。**
**等待下一步指令。**

---

## 16. 迁移执行记录（Migration Execution Log）

> 执行日期：2026-09-15；回滚点：`2e880560df4c7be1c460e46baf0302071a91af30`（审计基线 HEAD）。
> 原则：**Move, don't rewrite** —— 全程未修改业务逻辑、Skill 行为、Eval 语义、Schema 语义、Benchmark/Golden expectation。

### 16.1 各 Phase 执行摘要

| Phase | 内容 | 结果 |
|---|---|---|
| 0 | 基线校验：HEAD 记录 + 基线回归 29/29 + `git ls-files` = 580 | PASS |
| 1 Safe Moves | 删 23 个 `_*_log.txt/_*_sample.txt` 运行产物 + 删 `scripts/run-regression.ps1`（先全仓查引用并修复 4 处活文档引用）+ `.gitignore` 追加规则（`_*_log.txt`、`_*_sample.txt`、`client-intake-data/clients/**`、`domain/insurance/kb/*.sqlite`）+ `docs/dev-notes/`、`docs/archive/` 归档移动 | 完成 |
| 2A M-1 | `workflow/` → `runtime/`、`state/` → `runtime/state/`（git mv）+ 20 处 import + YAML `state_schema` + 包内 `from state import` → `from .state import` | 完成 |
| 2B M-2 | `evidence/` → `knowledge/evidence/`、`rag/` → `knowledge/rag/` + 新增 `knowledge/__init__.py` + 16 处 import + **`provider.py` `REPO_ROOT` 改 2 级 dirname（§7.2.B 风险点已按新层级重验）** | 完成 |
| 2C | `docs/architecture/` 归组（9 份架构文档迁入）+ 全仓活文档路径引用修复约 60 处 | 完成 |
| 3 | 新增 `tests/structure/test_structure_integrity.py`（21 项 invariant）+ `docs/repository-structure.md`（含 Architecture→Directory Mapping）+ `evals/README.md` + `test-cases/README.md` + README「Repository Structure」节 | 完成 |
| 4 | 全量回归矩阵 **30/30 ALL GREEN**（29 原套件 + structure-integrity） | PASS |
| 5 | git diff 审查 + 本执行记录 + demo 冒烟（demo-a/demo-b exit 0） | 完成 |

### 16.2 实际迁移统计（git diff 口径）

| 类型 | 数量 | 说明 |
|---|---|---|
| **Renamed** | 45 | 13 个为 rename+修改（import/path 修复）：`RM docs/architecture/*` 8、`RM dev-notes/*` 3、`RM runtime/*` 若干、`RM knowledge/evidence/provider.py` |
| **Added** | 6 | `tests/structure/test_structure_integrity.py`、`docs/repository-structure.md`、`docs/dev-notes/repository-structure-audit.md`、`evals/README.md`、`test-cases/README.md`、`knowledge/__init__.py` |
| **Deleted** | 24 | 23 个运行产物日志（无引用，已 grep 确认）+ `scripts/run-regression.ps1`（引用先行修复） |
| **Modified** | 54 | unstaged 201+/202−（高度对称 = 行内路径替换特征）；最大单文件为 README 31/41（§17 结构节重写）；代码侧均为 import/路径/docstring 级修改 |

跟踪文件数：580 − 24 + 6（新增待 add）= **562**。

### 16.3 回归证据（迁移后）

```
tmp/run_regression.py ........... 30/30 ALL GREEN（含新增 structure-integrity 21/21）
Agent Benchmark ................. 33/33（hard gates 违反 0；results.json 仅 generated_at 刷新）
Golden Cases .................... 9/9
Full-Agent E2E .................. 71 checks PASS
Product-Recommendation E2E ...... PASS（primary P007 / admissible C001 与基线一致）
Core-Analysis E2E ............... 41/41
Contracts ....................... 10/10
demo-a / demo-b ................. exit 0
git tracked files ............... 556（+6 新增待 add = 562）
```

### 16.4 偏差说明（相对审计计划）

- 审计计划为 29 套件，实际执行 **30**（新增 structure-integrity 属本次任务书要求的新增测试）。
- 审计 §12 Phase 2C 期望「29/29」按 30/30 等效达成；关键数字（benchmark 33、golden 9、full-agent 71）与基线完全一致，无任何 expectation 变更。
- `evals/agent-benchmark/results.json` 仅 `generated_at` 时间戳因重跑刷新，metrics 数值不变。
