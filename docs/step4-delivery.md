# Step 4 · 交付报告（Production Hardening + Agent Evaluation + Demo Readiness）

> 本文件对照 spec §三十四 的 12 项交付逐条作答。**所有数字来自真实执行**，无手工填写。
> 约束遵守：未新增业务 Skill、未重写 Orchestrator、未换 Agent/RAG 框架、未接真实产品 API、未引入 K8s/Redis/Kafka（spec §二）。

---

## 1. Audit（发现了哪些问题）

Phase 1 只读审计见 **`docs/step4-audit.md`**（10 问逐一回答 + 文件:行 证据）。核心发现：

| # | 发现 | 严重度 | 处置 |
|---|---|---|---|
| A1 | 无统一 Execution Trace（仅 `state["events"]` 原始日志，无 `duration_ms`、无外置文件） | 中 | **P2 已解决** |
| A2 | 无统一 Agent Benchmark / Baseline（只有分散 E2E） | 高 | **P3/P5 已解决** |
| A3 | Evidence 仅 document/chunk 级溯源，**无属性级 grounding** | 高 | **P7 已解决** |
| A4 | Catalog **无版本字段** → 历史 Case 无法还原推荐依据 | 中 | **P8 已解决** |
| A5 | 无产品化 CLI / 无 `main()` 用户入口 | 中 | **P10 已解决** |
| A6 | `product-candidate-provider` 测试最薄弱（仅 2 文件） | 中 | **P3 补异常用例（现 19/19）** |
| A7 | 无 Failure Taxonomy、无 ADR、无对外 README/架构图 | 中 | **P6/P12 已解决** |

**审计过程中额外发现的真实缺陷（非计划内，但必须修）**：

| # | 缺陷 | 性质 | 修复 |
|---|---|---|---|
| B1 | Recommendation 适配器「无准入候选即清空候选」的桩，丢掉了引擎区分 `INCOMPLETE_EVIDENCE`/`NO_CANDIDATES` 所需的元数据 | implementation bug（**桩在掩盖更深缺陷**） | 移除桩 |
| B2 | 推荐引擎状态优先级错：硬产品校验（不可保）未压过证据状态；总体状态用跨所有候选的 `evidence.status` 判断 | implementation bug | 两处修正（`has_hard` 提前、改用 `insuff`） |
| B3 | `eval_engine._flatten` 对 `allowed` 未做对称展平 → 任何 list 值字段触发 `TypeError: unhashable type: 'list'`，**Eval 直接崩溃而非给出判定** | implementation bug（安全洞） | 加 `_flatten_set()` 对称展平 |
| B4 | `report_generation_engine.REPO_ROOT` 高了一级（`dirname` 多算一层），导致独立运行时报 `FileNotFoundError` | implementation bug（潜伏） | 修正为 `HERE` + 4 级 |
| B5 | Benchmark 幻觉指标从未检查**主推荐产品**（产品嵌在 `product.product_id`，非顶层）→ 硬门形同虚设 | metric bug（假通过） | 修正观测路径 |
| B6 | Report 从不标记 DEMO 产品（违反 §30） | guardrail 缺口 | 实现 `disclosure`（并对照 catalog **独立复核**） |

> 纪律：以上均按「不修改 baseline 掩盖失败」处理 —— 先归类 implementation bug / test bug / contract conflict，再修**正确的那一层**。

---

## 2. Architecture（Step 4 之后的最终架构）

```text
                         Customer
                            │
                            ▼
                    ┌──────────────┐
                    │ Orchestrator │  ← 无业务判断；行为由 insurance-analysis.yaml 驱动
                    └──────┬───────┘
                           │
                     ┌─────▼─────┐
                     │ CaseState │  ← 唯一事实源（artifacts/tasks/registry/evals/checkpoints/trace）
                     └─────┬─────┘
                           │
                    ┌──────▼──────┐
                    │ Skill Graph │  8 层，单向：FACT→REQ→RISK→GAP→SOLUTION→PRODUCT→REPORT
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       Business          Evidence         Product
        Skills            RAG              Catalog
          │                │                │
          └────────────────┼────────────────┘
                           ▼
                       Artifacts
                           │
                           ▼
                          Eval (确定性 6 类)
                       ↙       ↘
                    PASS       FAIL
                     │           │
                     │        Repair → Rerun (≤3)
                     │           │
                     └─────┬─────┘
                           ▼
                      Checkpoint (校验后信任)
                           │
                           ▼
                         Report
                           │
                           ▼
                     Benchmark / Trace / Demo
```

**Step 4 新增层**：`workflow/trace.py`（Execution Trace）、`workflow/observability.py`（性能观测）、
`demo.py`（Demo CLI）、`evidence/attribute_grounding.py`（属性级 grounding）、
`evals/agent-benchmark/`（Benchmark + Golden + Baseline）、`docs/adr/`（7 份 ADR）。
**未改**：Orchestrator 主循环结构、8 个 Skill 的职责边界与判定语义。

完整图 + 执行方式标记（Deterministic/LLM/RAG/External）见 **`docs/architecture.md`**。

---

## 3. Execution Trace（一次真实 Case Trace）

以下为 `python demo.py demo-b`（故障路径）产出的真实 trace（`tmp/demo/bm-noev-001/trace.jsonl` / `trace.md`）：

| time | event | skill | dur(ms) | detail |
|---|---|---|---|---|
| 0.00s | `CASE_STARTED` | - | - | workflow=insurance-analysis |
| 0.09s | `SKILL_COMPLETED` | client-intake | 0.0 | seeded (provided upstream) |
| 0.09s | `SKILL_COMPLETED` | requirement_analysis | 0.0 | seeded (provided upstream) |
| 0.09s | `SKILL_COMPLETED` | risk-analysis | 0.0 | seeded (provided upstream) |
| 0.11s | `SKILL_COMPLETED` | coverage-gap-analysis | 15.05 | stage=coverage-gap-analysis |
| 0.12s | `CHECKPOINT_SAVED` | - | - | CP-001 tasks=4 artifacts=4 |
| 0.14s | `SKILL_COMPLETED` | solution | 14.96 | stage=solution |
| 0.14s | `CHECKPOINT_SAVED` | - | - | CP-002 tasks=5 artifacts=5 |
| 0.18s | `TASK_FAILED` | product-candidate-provider | - | `knowledge-search: EVIDENCE_EVAL_FAIL[EVAL-006]: required_non_empty(empty: payload.evidence)` |
| 0.18s | `REPAIR_STARTED` | product-candidate-provider | - | action=RERUN_FROM_UPSTREAM |
| 0.18s | `REPAIR_COMPLETED` | product-candidate-provider | - | changed=True |
| 0.19s | `TASK_FAILED` | product-candidate-provider | - | `EVIDENCE_EVAL_FAIL[EVAL-007]` |
| 0.19s | `REPAIR_STARTED` / `REPAIR_COMPLETED` | product-candidate-provider | - | 第 2 次修复 |
| 0.19s | `TASK_FAILED` | product-candidate-provider | - | `EVIDENCE_EVAL_FAIL[EVAL-008]` |
| 0.20s | `CHECKPOINT_SAVED` | - | - | CP-003 tasks=5 artifacts=6 |
| 0.21s | `CASE_NEEDS_REVIEW` | product-candidate-provider | - | repair_exhausted |

**这段 trace 能回答「为什么最终没有推荐产品」**：知识库为空 → Evidence Eval 失败（`required_non_empty`）
→ 两次自动 Repair（重取上游）仍失败 → 耗尽 3 次尝试 → `NEEDS_REVIEW`，且**根因写在事件里**（非只有 `ERROR`）。

事件枚举（13+）与字段定义：`CASE_STARTED / TASK_CREATED / TASK_STARTED / SKILL_STARTED /
SKILL_COMPLETED / EVAL_STARTED / EVAL_COMPLETED / REPAIR_STARTED / REPAIR_COMPLETED /
CHECKPOINT_SAVED / CHECKPOINT_LOADED / TASK_FAILED / CASE_WAITING / CASE_COMPLETED / CASE_NEEDS_REVIEW`，
每条携带 `trace_id / case_id / task_id / skill / event / attempt / input_artifacts / output_artifact /
eval_status / duration_ms / timestamp`。详见 `docs/execution-trace.md`。

---

## 4. Benchmark（`evals/agent-benchmark/`）

**33 个合成 / 匿名 Case**（全部为对已验证全链种子的变异；上游 seed 注入，下游真实执行）。

### Case 分布

| Category | n | Passed |
|---|---|---|
| complete | 7 | 7 |
| insufficient_information | 5 | 5 |
| conflicting_information | 5 | 5 |
| low_risk | 3 | 3 |
| high_risk | 3 | 3 |
| no_candidates | 3 | 3 |
| insufficient_evidence | 3 | 3 |
| adversarial（故障注入） | 3 | 3 |
| repairable | 1 | 1 |
| **合计** | **33** | **33** |

### Agent-Level Metrics（真实运行）

| Metric | Value |
|---|---|
| **Task Success Rate** | **100.0%** (33/33) |
| **Hard Gate Failures** | **0** |
| **Provenance Completeness** | **100.0%** |
| **Repair Success** | 9.1% (1/11) 全量 / **100.0% (1/1) repairable only** |
| Product Hallucination Rate | **0.0%** |
| Invalid Continuation Rate | **0.0%** |
| Unsupported Claim Rate | **0.0%** |
| Human Review Rate | 21.2% |

### Safety Hard Gates（§11：不用总分掩盖风险）

| Gate | 要求 | Result |
|---|---|---|
| product_hallucination_zero | 0 | **PASS** |
| critical_provenance_failure_zero | 0 | **PASS** |
| invalid_continuation_zero | 0 | **PASS** |

> `repair_success_rate` 的分母**故意包含不可修复的注入故障**，故全量值偏低；真实能力看
> `repairable only = 100%`。报告同时给出两个值，避免用单一数字夸大或贬低。
> 基线：`evals/agent-benchmark/baseline.json`；报告：`evals/agent-benchmark/report.md`。

---

## 5. Golden Cases（`evals/agent-benchmark/golden.json`）

9 个 Golden Case，**断言行为与约束**，不固定最终文本。

| ID | 场景 | 测试目的 |
|---|---|---|
| G-001 | 完整客户 | 全链路走通 + artifact 齐全 + 报告产出 |
| G-002 | 信息不足（blocking 字段缺失） | **必须停在 `WAITING_FOR_USER`**，不得进入需求/产品层 |
| G-003 | 信息冲突 | 冲突**保留 UNKNOWN + 列候选**，不得自行择一 |
| G-004 | 无候选产品（年龄超限） | 必须 `NO_CANDIDATES` + `primary=None`；**不得**推荐不可保产品 |
| G-005 | 证据不足 | 必须阻断并转人工，**禁止**用模型记忆补知识 |
| G-006 | 高风险 | 必须识别出指定高风险 |
| G-007 | 可修复 | Repair 必须发生且**最终转正**（repair 有效性） |
| G-008 | 损坏 artifact（故障注入） | Eval 必须拦下，**不得**带病下推 |
| G-009 | 单一需求完整客户 | 必须落到**具体 demo 产品**，且报告**标记 DEMO** + 产品在 catalog 内（§13/§31） |

Regression 门禁：`run_golden_cases.py` 支持 Before/After 对比并留存基线（`--update-baseline`）。
当前 **9/9 PASS**。

---

## 6. Failure Taxonomy（`docs/failure-taxonomy.md`）

F1–F12 分类（Input / Requirement / Risk / Gap / Solution / Evidence / Candidate / Recommendation /
Orchestration / Eval / Repair / State-Checkpoint），每类记录：**原因 / 检测方式 / 可否自动修复 /
修复策略 / 是否需人工**，并以实际错误码为锚（如 `NON_MONOTONIC` / `MISSING_INPUT_ARTIFACT` /
`INPUT_NOT_RELEASED` / `ARTIFACT_MUTATION` / `CHECKPOINT_INVALID` / `ELIGIBILITY_INELIGIBLE` /
`EVIDENCE_MISSING` / `EVIDENCE_UNSUPPORTED` / `NO_CANDIDATES` / `INCOMPLETE_EVIDENCE`）。

**Failure Matrix（节选）**：

| Failure | Detect | Retry | Repair | Human Review |
|---|---|---|---|---|
| Missing information | Eval/Orchestrator | No | Ask user | No |
| Retrieval / no evidence | Eval | Yes | 重取上游（RERUN_FROM_UPSTREAM） | Yes（耗尽后） |
| No candidate（资格） | Rule | No | No | Maybe |
| Invalid product | Rule | No | DROP_INVALID_PRODUCTS | Yes |
| Schema / required 失败 | Eval | Yes | Regenerate | Maybe |
| Broken checkpoint | Validator | No | 恢复前一检查点 | Yes |
| Artifact 篡改 | 冻结校验 | No | 拒绝写回 | Yes |
| 上游缺 seed | Orchestrator | No | 补 seed | Yes（BLOCKED） |

---

## 7. Evidence Grounding（属性级 grounding 是否已支持）

**是，已支持（V0.2，5 个关键属性）。**

```text
Product Attribute → Evidence Requirement → Evidence Chunk → SUPPORTED / UNSUPPORTED / CONFLICT
```

- 模块：`evidence/attribute_grounding.py`；规则外置：`evidence/resources/config/attribute-grounding.rules.json`。
- 覆盖属性：`coverage_type / eligibility_age / renewal_period / deductible / coverage_term`（§19 明确「不一次做完」）。
- 四态：`SUPPORTED / UNSUPPORTED / CONFLICT / NOT_CHECKABLE`；**NOT_CHECKABLE 是独立第三态，绝不折成 SUPPORTED**。
- 结论已下沉到候选层：`evidence.attribute_rollup` + `evidence_unsupported_attributes`；
  推荐层投影保留 `evidence_attribute_rollup`（`product_candidates_to_candidate_solutions.py`）。
- 无证据的产品**不得**作为有依据的推荐（`EVIDENCE_MISSING` / `EVIDENCE_UNSUPPORTED`）。

> 关键原则：仅凭 `domain = medical` **不足以**认为证据足够 —— 必须落到「哪个属性被哪条 chunk 支持」。
> 当前匹配为字符串级（含金额单位归一，如 `10000元` ↔ `1 万元`），非语义蕴含；故**假阴性倾向**，
> 不确定时判 UNSUPPORTED/NOT_CHECKABLE 而不判 SUPPORTED。验证：`test_step4_phase7_evidence_grounding.py` **24/24**。

---

## 8. Observability（记录哪些指标）

`workflow/observability.py`（复用 P2 trace 的 `duration_ms`）：

| 指标 | 记录 |
|---|---|
| **latency** | 每 Skill `total_ms`（per-skill 聚合） |
| **task count** | `call / done / fail` 三列 |
| **retry / repair** | `repairs` 次数（含失败尝试） |
| **retrieval** | `knowledge_search_calls`（services 计数） |
| **artifact / eval / checkpoint** | 各自数量 |

**真实样本（`python demo.py demo-a`，`bm-complete-006-single-medical`）**：

```text
status=COMPLETED  wall=0.30s
Stage calls: 5 executed + 3 provided(upstream) = 8 stages
Service calls: knowledge-search=1
Total skill invocations for this case: 9
Repairs: 0   Artifacts: 9   Evals: 9   Checkpoints: 6

skill                         call  done  fail   total_ms
coverage-gap-analysis            1     1     0      14.19
solution                         1     1     0      14.60
product-candidate-provider       1     1     0      41.64
product-recommendation           1     1     0      17.11
report-generation                1     1     0      23.77
```

**失败样本（`demo-b`，`bm-noev-001`）**：`wall=0.21s`，`knowledge-search=3`，`Total=11`，`Repairs=2`。

> 回答 spec §22 的问题：**一个完整 Case 跑完需要 9 次 Skill 调用（含 1 次 knowledge-search）**；
> 失败 Case 因 2 次 Repair 重取，升至 11 次。JSONL 落盘，无复杂 tracing infrastructure。

---

## 9. Demo（如何启动）

```bash
python demo.py demo-a    # 完整案例（单一需求）→ 真正落到一个具体产品 → 推荐 + 报告（标记 DEMO）
python demo.py demo-b    # 故障演示：KB 为空 → Eval FAIL → Repair → 仍失败 → NEEDS_REVIEW
python demo.py demo-c    # 多需求完整客户 → 策略覆盖 5 领域，无单一产品 → 诚实呈现，不硬推
python demo.py --list    # 列出所有可用 case
```

Demo 实时流式显示 `[OK]/[XX] skill … PASS/FAIL (ms)`、checkpoint、repair 动作、最终 RESULT，
并落盘 `trace.jsonl`（结构化）+ `trace.md`（人读视图）。**无前端**，纯 CLI（§24 要求）。

Demo A 真实输出（节选）：

```text
RESULT: COMPLETED
Case bm-complete-006-single-medical  status=COMPLETED  wall=0.30s
OUTCOME
  recommendation status: COMPLETE
  primary product: P001 ... (1.0 / catalog 0.1)
  candidates evaluated: 4 (primary=3, not_recommended=1, insufficient=0)
  evidence refs: 01_medical_insurance_001 ... 005
  SAFETY: DEMO products disclosed -> P001, P002, P003
  SAFETY: catalog_checked=True, unverified_products=[]
```

**Demo B（§31 要求故意制造问题）** 展示：证据不足 → Repair ×2 → 仍失败 → `NEEDS_REVIEW`，
比只展示「成功推荐」更能体现 Agent 工程能力。

---

## 10. Documentation（列出交付文档）

| 文档 | 内容 |
|---|---|
| **`README.md`**（新建） | Problem / Architecture / Skill Graph / CaseState / Artifact / Evidence / Candidate / Orchestrator / Eval / Repair / Checkpoint / Benchmark / Demo / Limitations + **「为什么这么设计」8 问** |
| **`docs/architecture.md`**（新建） | 架构总图 + 执行方式标记（Deterministic / LLM / RAG / External Data） |
| **`docs/adr/ADR-001…007`**（新建） | Skill 架构 / Orchestrator / Artifact lineage / Deterministic Eval / Evidence provenance / Candidate-Recommendation 分离 / Checkpoint-Resume（各含 Context·Decision·Alternatives·Why·Trade-offs） |
| `docs/step4-audit.md` | Phase 1 只读审计（10 问 + 证据） |
| `docs/execution-trace.md` | Execution Trace 事件枚举与字段 |
| `docs/failure-taxonomy.md` | F1–F12 + Failure Matrix |
| `docs/orchestration.md` / `docs/contract-layer.md` / `docs/architecture-v2.md` / `docs/evidence-provider.md` / `docs/product-recommendation-v2.md` / `docs/report-generation-v2.md` / `docs/step2-evidence-recommendation.md` / `docs/step3-assembly.md` | Step 1–3 既有技术文档 |

（spec §27 允许 `architecture.svg` **或** `architecture.md`，本阶段交付 `.md`。）

---

## 11. Regression（完整测试结果）

最终测试矩阵（spec §32）：**29/29 套件 ALL GREEN**。

| 套件 | 结果 |
|---|---|
| contracts（9 契约） | **10/10** PASS |
| e2e-full-agent（Step 3 全链路） | **71/71** PASS |
| e2e-product-rec（Step 2） | **61/61** PASS |
| e2e-core-analysis（Step 1） | **41/41** PASS |
| e2e-run_e2e | **36/36** PASS |
| orchestration-invariants | **21/21** PASS |
| step3-mutation（反橡皮图章） | **9/9** PASS |
| step3-self-eval（依赖/顺序/重试/续跑/闸门） | **14/14** PASS |
| step4-p2-trace | **17/17** PASS |
| step4-p8-catalog-ver | **14/14** PASS |
| step4-p9-observability | **20/20** PASS |
| step4-p13-guardrails | **33/33** PASS |
| step4-p7-evidence-grounding | **24/24** PASS |
| agent-benchmark | **33/33 cases** PASS（硬门 0 违反） |
| golden-cases | **9/9** PASS |
| evidence-invariants / evidence-dataset | ALL GREEN |
| unit-coverage-gap / unit-candidate-provider(19/19) / unit-recommendation-v2(10/10) / unit-report-v2 / unit-solution | ALL GREEN |
| dataset-coverage-gap / solution / knowledge-search / product-rec / recommendation / report / report-v2 | ALL GREEN |
| **OVERALL** | **ALL GREEN (29/29 套件)** |

**验收判据（spec §32）**：existing regression = PASS ✓ / critical safety gates = PASS ✓ /
golden cases = PASS ✓ / mutation detection = PASS ✓。

---

## 12. Remaining Technical Debt（仍未解决的问题）

| # | 技术债 | 影响 | 建议 |
|---|---|---|---|
| T1 | `product-candidates` 无 Canonical 契约（仅 Skill 级 schema） | 该层无法参与跨文件契约校验；canonical 化需改 9 份 schema 的 `artifact_type` 枚举 | 若后续要接真实产品库，先补该契约 |
| T2 | 属性级 grounding 仅 5 属性 + 字符串级匹配（非语义蕴含） | 假阴性（漏判 SUPPORTED） | 引入语义匹配或人工复核通道；不扩大属性数目前不划算 |
| T3 | 上游三 stage 为 `provided`，不覆盖「原始对话 → client-profile」 | E2E 起点是 client-profile | 若需端到端对话演示，加 intake 演示入口 |
| T4 | Catalog 为 demo（12 产品，全 `is_demo=true`） | 推荐能力受限于虚构产品 | Product Provider 抽象已就绪，接真实数据源无需改 Recommendation |
| T5 | 无并发 / 多租户 / 持久化 DB | 单客户单进程 | 生产化前需引入状态存储与并发控制 |
| T6 | `repair_success_rate` 全量值低（9.1%）易被误读 | 指标语义需解释 | 报告已同时给出 `repairable only`；可进一步按 category 分列 |
| T7 | Eval 不做主观判断（语气/易懂性） | 覆盖不到表达质量 | 有意留白；如需可加独立人工评审环节 |
| T8 | `report` 的 DEMO 披露依赖 catalog 复核，但 catalog 本身是 demo | 披露正确性受 catalog 质量影响 | 接真实 catalog 后需重置基线 |

---

## 附：Step 4 十四 Phase 完成状态

| Phase | 内容 | 状态 |
|---|---|---|
| P1 | 架构审计 | ✅ `docs/step4-audit.md` |
| P2 | 统一 Execution Trace | ✅ `workflow/trace.py`，13+ 事件，`trace.jsonl` |
| P3 | Agent Benchmark（33 Case） | ✅ `evals/agent-benchmark/` |
| P4 | Golden Cases（9） | ✅ `golden.json` |
| P5 | Regression Benchmark + Baseline | ✅ `run_golden_cases.py` + `baseline.json` |
| P6 | Failure Taxonomy F1–F12 | ✅ `docs/failure-taxonomy.md` |
| P7 | 属性级 Evidence Grounding | ✅ `evidence/attribute_grounding.py` |
| P8 | Catalog Versioning | ✅ `catalog/product-catalog.v0.1.json` |
| P9 | 成本/性能 Observability | ✅ `workflow/observability.py` |
| P10 | Demo Mode（CLI） | ✅ `demo.py` |
| P11 | Trace Viewer | ✅ `trace.md` |
| P12 | Documentation + ADR | ✅ `README.md` / `docs/architecture.md` / `docs/adr/*` |
| P13 | Safety Guardrails | ✅ `disclosure` + 提示注入/守卫 |
| P14 | Final Demo + 测试矩阵 + 交付 | ✅ 本文件 |

> **Step 4 完成。** 按 spec §三十五：完成本阶段后暂停大规模开发，进入**作品包装 + 面试准备阶段**，
> 不再继续无限扩功能。
