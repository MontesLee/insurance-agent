# 保险 Agent V2 — Phase 7：CaseState + Orchestrator + E2E

> 本文件记录 **Phase 7** 的产出与验证结论。
> 前置：Phase 0 审计 `docs/dev-notes/architecture-v2-audit.md`（只读基线，未修改）· Phase 1 契约层 `docs/architecture/contract-layer.md`。
> 本阶段**只新增** `state/`、`workflow/`、`tests/e2e/`；**未修改任何 Skill**（见 §7 git 摘要）。

---

## 1. 目标与硬边界

Phase 7 把 8 个 Specialist Skill 串成**可一键运行、带状态、带人工复核闸门**的完整链路。

| 层级 | 回答什么 | 本阶段做什么 |
|---|---|---|
| Contract | Skill 之间交换什么 | 沿用 Phase 1 的 9 份 Canonical Contract（不改） |
| **State** | **这一单客户走到哪了、手里有什么** | **新增 `state/`：CaseState（唯一事实源 + 三不变量）** |
| **Workflow** | **按什么顺序、谁执行、在哪停** | **新增 `workflow/`：声明式 stage 图 + 执行器** |
| Eval | 怎么证明它真的通了 | 新增 `tests/e2e/`：真实全链路 + 不变量 + 负向探针 |

**编排层无任何保险判断**：它只搬运 Artifact、校验契约、强制顺序、在闸门处停下。它不重算等级、不选择策略、不生成推荐、不渲染报告内容。

---

## 2. CaseState（`state/`）

一个客户 = 一个 CaseState。它是**唯一事实源**：每个 stage 从 `artifacts` 读输入，只写回**自己声明的那一个** Artifact。

```
CaseState
  ├── case_id / workflow / workflow_version
  ├── stage_order      线性 stage 顺序（由 workflow 定义派生，不可手改）
  ├── current_stage
  ├── stages           per-stage: index/skill/produces/consumes/gate/executor/status/
  │                              provided_by/attempts/artifact_fingerprint/notes
  ├── artifacts        artifact_type -> Canonical Artifact（管道里的数据）
  ├── services         非线性共享服务（knowledge-search）的调用记账
  └── events           只追加的事件流
```

状态机：`PENDING → RUNNING → COMPLETED | NEEDS_REVIEW | FAILED`（`SKIPPED` 保留）。

### 2.1 三不变量（`runtime/state/transitions.py`）

| 不变量 | 规则 | 违反时 |
|---|---|---|
| **单调性** | 后继 stage 未完成前，前序 stage 不得重入；不得倒流 | `NON_MONOTONIC` |
| **前置条件** | 只有当 `consumes` 的全部 Artifact **存在且其生产者已 `COMPLETED`** 才可运行 | `MISSING_INPUT_ARTIFACT` / `INPUT_NOT_RELEASED` |
| **不可变** | 一旦 `COMPLETED`，该 stage 的 Artifact 被冻结（sha256 指纹比对） | `ARTIFACT_MUTATION` |

> 「生产者必须 `COMPLETED`」而不是「文件存在」是让**人工闸门真实有效**的关键：停在 `NEEDS_REVIEW` 的 stage 会挡住它的下游。

### 2.2 持久化（`runtime/state/store.py`）

```
<root>/<case_id>/
    case_state.json          CaseState
    artifacts/<type>.json    每个 Canonical Artifact 单独落盘（便于人审逐份查阅）
```

---

## 3. Workflow（`runtime/insurance-analysis.yaml`）

**声明式、单一真源**：stage 顺序 = YAML 里列表的顺序（`index` 由编排器按位置赋值，避免两处漂移）。

### 3.1 线性 stage（7 个）

| # | stage | 生产者 | Artifact | 执行器 | 闸门 |
|---|---|---|---|---|---|
| 0 | client-intake | — | ClientProfile | `provided` | **human_review** |
| 1 | requirement-analysis | client-profile | RequirementAnalysis | `provided` | auto |
| 2 | risk-analysis | client-profile, requirement-analysis | RiskAssessment | `provided` | auto |
| 3 | coverage-gap-analysis | client-profile, requirement-analysis, risk-assessment | CoverageGapAnalysis | `python` | auto |
| 4 | solution | coverage-gap-analysis, requirement-analysis, risk-assessment | SolutionPlan | `python` | auto |
| 5 | product-recommendation | requirement-analysis, risk-assessment, coverage-gap-analysis, solution-plan | ProductRecommendation | `python` | **human_review** |
| 6 | report-generation | client-profile, requirement-analysis, risk-assessment (+4 可选) | InsuranceReport | `python` | auto |

**执行器语义**
- `provided`：Artifact 由**编排器之外**产生（对话式 PowerShell Skill，或已跑过的运行时），由 `seed_case()` 注入并记为 `provided_by=upstream-dialogue`。**编排器不假装跑过它**；没有 seed 就 `BLOCKED`，绝不编造。
- `python`：导入 Skill **自己声明的入口**并调用其声明函数（连字符文件名用 `importlib`）。

### 3.2 非线性服务（1 个）

`knowledge-search` **不是 stage**，而是 `services:` 里声明的**共享 Evidence Provider**（用户 Phase 1 评审修改 ③）。任何 stage 都可以通过 `services:` 请求一次证据回环：

```yaml
- id: product-recommendation
  services:
    - id: knowledge-search
      source: solution-plan          # 以哪个 Artifact 为请求依据
      source_kind: solution
      purpose: SOLUTION_VALIDATION
      store_as: knowledge-evidence
```

编排器代该 stage 调用 `evidence.loop.request_evidence()`，把 `KnowledgeEvidence` 存为独立 Artifact，并记录 `source_unchanged`。

### 3.3 显式输入边界（`input_map` / `post_adapter`）

不同 Skill 的入口键名并不一致（这是真实存在的耦合点），因此**在 YAML 里显式声明**，而不是靠约定：

- 默认：`key = artifact_type`（连字符→下划线），`shape = artifact`（Canonical 信封）。
- `report-generation` 读的是**裸 payload** 且风险键叫 `risk_analysis` → 用 `input_map` 声明：

```yaml
input_map:
  client-profile:       { key: client_profile,       shape: payload }
  requirement-analysis: { key: requirement_analysis, shape: payload }
  risk-assessment:      { key: risk_analysis,        shape: payload }
```

- `report-generation` 的引擎返回 Skill 原生结果 → 用 `post_adapter` 声明契约边界：

```yaml
post_adapter: adapters.report_generation_adapter.to_canonical
```

> 这两条把「隐式字段 / 路径约定」变成了**可读、可测、可替换的显式契约**。Phase 1 说的「Skill 之间不允许通过隐含字段耦合」，在这里落到具体机制。

---

## 4. 一次真实运行

同一份 seed，先 `gate_policy=stop` 起跑，在人工闸门处停下；批准后续跑完成：

```
== RUN 1 (gate_policy=stop) ==
status=PAUSED_NEEDS_REVIEW   stopped_at=product-recommendation
client-intake        COMPLETED
requirement-analysis COMPLETED
risk-analysis        COMPLETED
coverage-gap-analysis COMPLETED
solution             COMPLETED
product-recommendation NEEDS_REVIEW     <-- 闸门
report-generation    PENDING            <-- 未越闸

== APPROVE -> ==

== RUN 2 ==
status=COMPLETED
... 7/7 COMPLETED
artifacts = [client-profile, requirement-analysis, risk-assessment,
             coverage-gap-analysis, solution-plan, knowledge-evidence,
             product-recommendation, insurance-report]      # 8/8
services  = knowledge-search: calls=1, source_unchanged=True
events    = 22
```

事件流（节选）：

```
CASE_CREATED      -                     case CASE-E2E-001
ARTIFACT_STORED   client-intake         client-profile
STAGE_COMPLETED   client-intake         seeded via upstream-dialogue (gate=human_review satisfied upstream)
STAGE_START       coverage-gap-analysis coverage-gap-analysis
STAGE_COMPLETED   coverage-gap-analysis
STAGE_START       solution              solution
STAGE_COMPLETED   solution
STAGE_START       product-recommendation
SERVICE_CALLED    product-recommendation knowledge-search purpose=SOLUTION_VALIDATION source_unchanged=True
ARTIFACT_STORED   product-recommendation knowledge-evidence
STAGE_NEEDS_REVIEW product-recommendation
APPROVED          product-recommendation human review cleared
STAGE_START       report-generation
STAGE_COMPLETED   report-generation
```

终产物 `InsuranceReport`：`status=success`、04 章节 `derivation=canonical`、4 个缺口 / 4 条策略 / 5 条证据、Markdown 成稿约 5.3k 字符，且**不含任何保险公司品牌词**。

---

## 5. 为什么 knowledge-search 不是 Stage 6

用户评审修改 ③ 的落地方式：如果把它写成线性第 6 步，架构就会退化为「固定流水线」，无法表达：

```
Product Recommendation --"缺某责任证据"--> Knowledge Search --> Evidence --> 继续 Recommendation
```

现在它的原子操作被固化为 `Skill → Evidence Request → Knowledge Search → Skill`，编排层只负责**在某个 stage 声明它的需要**并记账。E2E 探针 `P5` 会**加一个 knowledge-search stage** 让形状检查失败，反向证明这条约束不是空话。

---

## 6. 验证结论

| 套件 | 结果 |
|---|---|
| **E2E 全链路**（闸门暂停→批准→续跑） | **36/36 ALL GREEN** |
| **编排不变量 + 负向探针** | **21/21 ALL GREEN** |
| 契约测试（9） | ALL GREEN |
| 全部既有数据集/单测 | ALL GREEN |
| **全工程合计** | **17/17 套件 GREEN，0 失败** |

### 6.1 E2E 检查（36 项，节选）

- workflow 形状：7 个线性 stage、顺序正确、**knowledge-search 不是 stage**、index 连续
- seeding：CaseState schema 合法、provided stage 为 COMPLETED、seed 已包成 Canonical 信封
- **闸门**：`stop` 时确实 `PAUSED_NEEDS_REVIEW`；被闸 stage `NEEDS_REVIEW`；下游仍 `PENDING`；`next_runnable` 仍指向被闸 stage（**无法跳过**）；**重试也无法绕过**；批准后完成
- 产物：8 个 Artifact **逐一通过其 Canonical Contract 校验**
- 报告：`derivation=canonical`、缺口/策略/证据章节非空、无品牌词
- 证据：service `calls=1`、`source_unchanged=True`
- 冻结：篡改已完成 Artifact 被拒，且原 Artifact 未变
- 持久化：`case_state.json` + 逐份 Artifact 落盘、重载后**逐字节相等**、重载后仍 schema 合法
- 记账：每个 python stage `attempts == 1`

### 6.2 不变量与负向探针（21 项，节选）

每条探针都是**单点变异 + 反向断言**（证明它不是恒真/恒假的橡皮图章）：

| 探针 | 单点变异 | 期望 | 反向断言 |
|---|---|---|---|
| P1 | 把已完成的 `solution` 改回 `PENDING` | `NON_MONOTONIC` | P1r 同等状态但无后继完成 → **通过** |
| P2 | 删除 `risk-assessment` | `MISSING_INPUT_ARTIFACT` | — |
| P3 | 改一个字节 | 拒绝 | P3r 传同一对象副本 → **通过** |
| P4 | 把生产者置为 `NEEDS_REVIEW` | `INPUT_NOT_RELEASED` | P4r 生产者 `COMPLETED` → **通过** |
| P5 | 把 knowledge-search 加成 stage | 形状检查失败 | P5r 原 workflow → **通过** |
| P6 | 不给 `risk-assessment` seed | `BLOCKED`，且**不编造**该 Artifact、下游全 `PENDING` | — |

---

## 7. 变更范围

`git status` 显示本阶段新增未跟踪：`state/`、`workflow/`、`tests/e2e/`（`tests/` 整体未跟踪）。
`git diff --stat` **仅包含 Phase 5（recommendation）与 Phase 6（report-generation）的历史改动**，
**Phase 7 对既有 Skill 为 0 修改**——`client-intake` / `requirement_analysis` / `risk-analysis` /
`knowledge-search` 全程未被触碰，`coverage-gap-analysis` / `solution` 亦未改。

---

## 8. 如何运行

```bash
# 生成 E2E seed（取自 report-generation V2 数据集的 v2_full_chain 用例）
python tests/e2e/_gen_e2e_fixture.py

# 全链路 E2E（含人工闸门暂停/批准/续跑、契约校验、持久化）
python tests/e2e/run_e2e.py

# 编排不变量 + 负向探针
python tests/e2e/test_orchestration_invariants.py
```

Python 侧需要 `PyYAML`（本阶段加入托管 venv）。
运行产物写入 `tmp/e2e/<case_id>/`（`tmp/` 不计入基线）。

---

## 9. Phase 7 完成结论

- **State 层**：CaseState 成为跨 8 个 Skill 的唯一事实源；单调性 / 前置条件 / 冻结三不变量可机检。
- **Workflow 层**：stage 图声明式、单一真源；执行器只调用 Skill 自己声明的入口，不复制其逻辑；输入键与形状、适配器边界均**显式声明**。
- **人工复核闸门**：真实存在且不可绕过——停在闸门的 stage 会挡住下游，批准才放行。
- **Evidence Provider**：保持非线性共享服务语义，回环只读（`source_unchanged`）。
- **验证**：E2E 36/36、不变量+探针 21/21、全工程 17/17 套件 GREEN；既有 Skill 0 修改。

至此 **V2.0 骨架闭环**：`contracts/ · adapters/ · skills/ · evidence/ · state/ · workflow/ · tests/`。

**V2.1（按用户评审暂缓）**：抽取 `domain/insurance/`（Domain Pack / Playbook / References / Overlays）。
