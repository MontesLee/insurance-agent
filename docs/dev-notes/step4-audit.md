# Step 4 · Phase 1 架构审计（Audit Report）

> 范围：**只读**。本阶段不改动任何系统代码（spec §三「先不要编码」「不要先改代码」）。
> 审计对象为当前 `D:/Workspace/insurance-agent` 仓库真实代码，结论均附 `文件:行` 证据。
> 配套文档：`docs/dev-notes/step3-assembly.md`（Step 3 组装）、`docs/architecture/orchestration.md`（P7 架构）、`docs/architecture/architecture-v2.md`。

---

## 0. 审计结论（一句话）

系统**已具备可验证、可修复、可恢复的运行骨架**（Step 3 完成）：有真实执行入口、CaseState 单一事实源、Artifact 血缘、确定性 Eval、局部 Repair、Checkpoint/Resume。
但**尚缺「统一执行 Trace」「统一 Agent Benchmark」「Golden Cases」「Failure Taxonomy」「属性级 Evidence Grounding」「Catalog 版本化」「成本/性能 Observability」「Demo Mode」「对外文档与 ADR」** —— 这些正是 Step 4 的 14 个 Phase 要补齐的。

**Phase 1 判定：可进入 Phase 2，无需先改代码。**

---

## 1. 当前架构快照

```text
                        Customer (对话 / 表单)
                                │  (executor: provided)
                                ▼
                     client-profile (artifact)
                                │
   ┌────────────────────────────┼─────────────────────────────┐
   ▼                            ▼                             ▼
requirement-analysis     risk-assessment            (二者均 provided)
   │                            │
   └─────────────┬──────────────┘
                 ▼
        coverage-gap-analysis  (python engine)
                 │
                 ▼
            solution-plan      (python engine)
                 │
                 ▼
     product-candidate-provider (python engine)
                 │  ├─ services: knowledge-search (Evidence Provider, 非线性)
                 ▼  ▼
        product-candidates ──► knowledge-evidence
                 │
                 ▼
       product-recommendation  (python engine, 含 Repair 适配)
                 │
                 ▼
          insurance-report     (python engine + post_adapter)

控制层（全部在 workflow/ + state/）：
  Orchestrator  →  eval_engine → repair → checkpoint
  CaseState     →  transitions (单调性/前置/冻结) + tasks (执行台账) + artifact_registry (血缘)
```

**真实执行入口（§三·问题1 详见 §2）**：`workflow/orchestrator.py::run()` 是唯一运行时循环；
测试/演示通过 `test-cases/e2e/full-agent/run_full_agent_e2e.py` 与 `tests/e2e/run_e2e.py` 驱动它。
**没有面向用户的产品化 CLI**（如 `insurance-agent demo CASE-001`）—— Phase 10 补齐。

**数据落地**：每个 Case 一个目录 `<root>/<case_id>/case_state.json` + `artifacts/<type>.json`（`state/store.py`）。

---

## 2. §三 十个问题逐一回答（附证据）

### Q1. Agent 的真实执行入口是什么？
- **运行时核心**：`workflow/orchestrator.py`
  - `run(state, ...)`（`orchestrator.py:495`）—— 主循环：`next_runnable → can_run → _execute_stage → OK/GATE/NEEDS_REVIEW → 闸门/续跑`。
  - `seed_case(wf, case_id, seeds, ...)`（`orchestrator.py:231`）—— 把对话/上游产生的 `client-profile / requirement-analysis / risk-assessment` 作为 `executor: provided` 注入 CaseState。
- **测试/演示驱动**：
  - `test-cases/e2e/full-agent/run_full_agent_e2e.py`（71 检查，5 案例）—— 调 `seed_case` + `run`。
  - `tests/e2e/run_e2e.py`、`tests/contracts/run_contract_tests.py`、`tests/workflow/test_step3_*.py`。
  - ~~`scripts/run-regression.ps1`~~（**已删除**，2026-09-15 结构迁移：引用不存在的 `01-client-intake/` 幽灵目录，运行即污染仓库；回归入口已由 `tmp/run_regression.py` 29 套件取代）。
- **8 个 Skill 的 `invoke-*.py` 入口**：由 Orchestrator 以 `executor: python` 反射调用（`_invoke_python_stage`，`orchestrator.py:150`；入口在 `insurance-analysis.yaml` 的 `entrypoint`）。生产态**不**独立运行，全部经 Orchestrator。
- **缺口**：无产品化 CLI / 无 `main()` 用户入口 —— **Phase 10（Demo Mode）** 补。

### Q2. CaseState 在哪里？
- `state/case_state.py` —— 单一事实源，结构见 `new_case_state()`（`case_state.py:30`）：
  `case_id / workflow / status / waiting_for_user / stages{} / artifacts{} / artifact_registry{} / tasks[] / evaluations[] / checkpoints[] / services{} / events[] / review`。
- 双写纪律：`tasks[].status` 与 `stages[].status` 经 `tasks.set_status()`（`tasks.py:71`）单一路径同步，`check_mirror()`（`tasks.py:162`）可机检。
- 运行态在内存；持久化见 Q6。

### Q3. Artifact 如何保存？
- **内存**：`state["artifacts"][type]`（`case_state.put_artifact`，`case_state.py:160`），写入前做冻结校验 `guard_immutable`（`transitions.py:106`）。
- **磁盘**：`state/store.py::save`（`store.py:25`）→ `<root>/<case_id>/case_state.json` + `artifacts/<type>.json`（每个 artifact 单文件，可 diff）。
- **血缘/元数据**：`workflow/artifact_registry.py::register`（`artifact_registry.py:46`）只存元数据（producer、input_artifacts、fingerprint、evidence_refs），**不复制内容**；`lineage()`（`artifact_registry.py:97`）可回溯到 client 事实；`verify()`（`artifact_registry.py:118`）按 fingerprint 防篡改。

### Q4. Eval 如何触发？
- **引擎**：`workflow/eval_engine.py::evaluate`（`eval_engine.py:291`），6 类检查：
  `schema / required_fields / contamination / provenance / cross_artifact / invariant` + `required_non_empty`。
- **触发点（全自动，非手动）**：
  1. 每个 stage 跑完即评：`_execute_stage` 内 `ev.evaluate(...)`（`orchestrator.py:423`）—— **PASS 才放行**，否则进入 repair/NEEDS_REVIEW。
  2. 种子 artifact 也评：`seed_case` 内 `ev.evaluate(...)`（`orchestrator.py:256`）。
  3. Evidence Provider 返回即评：服务调用后 `ev.evaluate(...)`（`orchestrator.py:209`）。
- **诚实规则**：无法评估的检查 → `FAIL`，**绝不** `MANUAL/UNKNOWN` 通过（`eval_engine.py:16` 注释 + `check_schema` 等实现）；full-agent E2E 显式断言「无 MANUAL 通过」（`run_full_agent_e2e.py:190`）。

### Q5. Repair 如何触发？
- **引擎**：`workflow/repair.py`，`plan(failed_checks)`（`repair.py:36`）把失败检查映射到动作（`RERUN_FROM_UPSTREAM` / `DROP_INVALID_PRODUCTS`）。
- **触发点**：`_execute_stage` 中 eval FAIL 且 `attempt < max_attempts`（`orchestrator.py:451`）→ `repair.apply()` 改 **stage INPUT**（绝不改已产出的 artifact）→ 重跑。
- **预算**：`max_attempts=3`（1 初始 + 2 repair）；耗尽 → `NEEDS_REVIEW`，保留 repair 轨迹（`state["stages"][sid]["repairs"]` + `tasks[].repairs`）。
- **纪律**：repair 只改输入重新派生，不动已冻结 artifact（`repair.py:7` 注释；`apply` 对 `RERUN_*` 直接返回「re-derive」）。

### Q6. Checkpoint 如何保存和恢复？
- **保存**：`workflow/checkpoint.py::save`（`checkpoint.py:30`）→ 记 `checkpoints[]` 条目 + `store.save` 落盘；在每阶段 OK/GATE/NEEDS_REVIEW 后由 `run()` 调用（`orchestrator.py:534-597`）。
- **恢复**：`checkpoint.load`（`checkpoint.py:78`）读 `case_state.json`，`validate()`（`checkpoint.py:53`）做 5 项校验：文件存在/解析、`case_id` 匹配、schema 校验、`registry.verify`（fingerprint 一致性）、task→stage 引用完整。
- **不信任原则**：任一失败 → `CHECKPOINT_INVALID` + 原因列表，**绝不**从损坏状态静默续跑（`checkpoint.py:12` 注释）。`resume()`（`checkpoint.py:94`）加载后继续 `orch.run`，并报告哪些 PASSed task 被重跑（应为空）。

### Q7. 每个 Skill 是否都有独立测试？
**有，但覆盖不均。**

| Skill | evals/ 文件数 | 备注 |
|---|---|---|
| client-intake | 72 | 充分（8 个 CASE + 回归集） |
| requirement_analysis | 21 | 充分 |
| risk-analysis | 48 | 充分（Phases 1–9） |
| coverage-gap-analysis | 8 | 有 dataset runner |
| solution | 8 | 有 dataset runner |
| knowledge-search | 8 | 有 dataset runner |
| report-generation | 4 | 有 dataset runner |
| recommendation | 4 | 有 E2E（Step 2） |
| product-candidate-provider | **2** | **薄弱**（Step 2 新建成，仅最小用例） |

外加 E2E 套件：`full-agent`(71)、`core-analysis`、`product-recommendation`(61)；契约测试 9 份（`tests/contracts/`）；工作流级 `mutation`(9) + `self_eval`(14)。
**缺口**：`product-candidate-provider` 测试最少 —— Phase 3 Benchmark 应补其异常用例。

### Q8. Full E2E 是否真正从 Client Input 开始？
**是，从 `client-profile` artifact 开始**（即客户 intake 的产物）。
- `run_full_agent_e2e.py:104-113`：`apply_mutations` 改 client-profile → `seed_case` 注入 `client-profile / requirement-analysis / risk-assessment`（三者 `executor: provided`）→ `orch.run` 真实执行 `coverage-gap → solution → candidate → recommendation → report`。
- 断言覆盖 5 个状态对象（CaseState / Task / Artifact 血缘 / Eval / Checkpoint），非仅最终报告（`run_full_agent_e2e.py:139-251`）。
- **边界说明**：E2E 不执行「原始对话 → client-profile」的 intake 本身（架构上 intake 是 `provided` 外部 stage）。若 Demo 想展示 intake→profile，Phase 10 可加一个 intake 演示入口；当前链路起点是 **client-profile 这一可信 artifact**，符合「单一事实源」设计。

### Q9. 当前有没有统一 execution trace？
**部分有，不符合 spec Phase 2 目标。**
- **已有**：`state["events"]` 追加式事件日志（`case_state.record_event`，`case_state.py:144`），捕获 `CASE_CREATED / ARTIFACT_STORED / STAGE_START / EVAL_PASS/FAIL / REPAIR_APPLIED / CHECKPOINT_SAVED / WAITING_FOR_USER` 等（`orchestrator.py`、`tasks.py` 多处调用）。
- **缺口（Phase 2 要补）**：
  1. 缺少 spec §四 要求的**结构化字段**：`trace_id / case_id / task_id / skill / event / attempt / input_artifacts / output_artifact / eval_status / duration_ms / timestamp`；
  2. 缺少 spec §五 的**13 个显式事件类型**（如 `CASE_WAITING`、`TASK_CREATED`、`CASE_NEEDS_REVIEW`）的统一枚举；
  3. 未**外置为独立 trace 文件**（如 `trace.jsonl`）；目前事件嵌在 CaseState 内，跨 run 不易聚合分析；
  4. 无 `duration_ms`（延迟/性能观测缺位）—— 与 Phase 9 关联。

### Q10. 当前有没有统一 benchmark？
**部分有，缺统一 Agent Benchmark。**
- **已有（分散）**：`full-agent` E2E（5 案例/71 检查）、各 skill E2E、9 份契约测试、`mutation`/`self_eval`、`knowledge-evidence-traceability` 等。
- **缺口（Phase 3 要补）**：仓库根 **无 `evals/agent-benchmark/`**（`tmp/test_layout.txt:84` 确认 `NO evals/ dir at repo root`）。即：
  - 没有 20–30 个合成 Case 的统一数据集；
  - 没有 spec §十 的 **Agent 级指标**（Task Success Rate / Unsupported Claim Rate / Product Hallucination Rate / Provenance Completeness / Invalid Continuation Rate / Repair Success Rate / Human Review Rate）；
  - 没有 spec §十五 的 **Eval Baseline**（真实运行数字，禁止编造）；
  - 没有 Golden Cases（Phase 4）与 Regression 门禁（Phase 5）。

---

## 3. 关键缺口 → Step 4 Phase 映射

| Step 4 Phase | 当前状态 | 要交付 | 关联证据 |
|---|---|---|---|
| P1 架构审计 | **本阶段，完成** | 本报告 | — |
| P2 统一 Execution Trace | 仅 `events[]` 原始日志 | 结构化 trace + 13 事件类型 + `duration_ms` + 外置 `trace.jsonl` | Q9 |
| P3 Agent Benchmark | 分散 E2E/契约 | `evals/agent-benchmark/` 20–30 合成 Case（正常+异常） | Q10 |
| P4 Golden Cases | 无 | 5–10 个 Golden Case（行为/约束断言，非固定答案） | Q10 |
| P5 Regression Benchmark | 手动跑套件 | Golden Cases 自动回归 + Before/After 对比 | — |
| P6 Failure Taxonomy | 无文档化分类 | `docs/architecture/failure-taxonomy.md` F1–F12 + 检测/修复矩阵 | — |
| P7 Evidence Grounding | 仅 document/chunk 级溯源 | 属性级 grounding（3–5 关键属性 → evidence → SUPPORTED/UNSUPPORTED/CONFLICT） | `knowledge-evidence.schema.json` 无 attribute 字段 |
| P8 Catalog Versioning | **无版本字段** | `catalog_version / product_version / effective_from/to`；Recommendation 留存版本 | `tmp/catalog_probe.txt:7` NONE |
| P9 成本/性能 Observability | 无 duration/计数 | 每 Skill latency、调用次数、repair/retrieval 次数（JSONL/local） | Q9 |
| P10 Demo Mode | 无 CLI | `insurance-agent demo CASE-001` CLI 实时展示 9 步 + 报告 | Q1 |
| P11 Trace Viewer | 无 | Markdown/JSON trace 视图 | P2 |
| P12 Documentation | 有技术 doc，缺对外 README/架构图/ADR | README + `architecture.svg/md` + 7 份 ADR + 「为什么」 | — |
| P13 Security/Safety | 有 contamination/边界守卫 | 明确 Guardrails：禁伪造；标记 DEMO/UNKNOWN/ESTIMATED；事实/分析/假设/建议分离 | — |
| P14 Final Demo + 测试矩阵 | — | Demo A(完整)/B(故意失败) + 最终测试矩阵 + 交付报告 | — |

**不变量（红线，贯穿所有 Phase）**：不新增业务 Skill、不重写 Orchestrator、不换框架/RAG、不接真实 API/K8s（spec §二）。

---

## 4. 审计发现的具体风险点（供后续 Phase 参考）

1. **`product-candidate-provider` 测试最薄弱（2 文件）** —— P3 优先补异常用例（无候选/不可保/证据缺失）。
2. **Evidence 仅 document/chunk 级溯源，无属性级 grounding** —— P7 需扩 `knowledge-evidence` schema（加 `attribute`/`support_status`），并改 eval 的 provenance 检查到属性粒度。
3. **Catalog 无版本字段** —— P8 加字段后，Recommendation 产出须留存 `product_id + product_version + catalog_version`，否则历史 Case 无法还原当时推荐依据。
4. **无结构化 trace / 无 duration** —— P2/P9 合并解决，trace 同时支撑「为什么没推荐」「性能瓶颈」两类问题。
5. **无统一 Benchmark/Baseline** —— P3/P5 解决；注意 **Baseline 数字必须来自真实运行，禁止编造**（spec §十五）。
6. **无产品化入口** —— P10 Demo Mode 是面试展示关键，但应保持 CLI 轻量（不做前端）。

---

## 5. Phase 1 结论与下一步

- **Phase 1（架构审计）完成**：10 个问题已逐条回答并附证据；系统底座健全，缺口明确且全部落在 Step 4 的 14 个 Phase 内。
- **无需先改代码**：所有缺口均为「新增能力」，不要求回改 Step 3 已稳定层。
- **下一步 = Phase 2（统一 Execution Trace）**：在 `state["events"]` 基础上，设计结构化 Execution Trace（trace_id / task_id / skill / event / attempt / input·output artifact / eval_status / duration_ms / timestamp），定义 13 个事件类型枚举，外置 `trace.jsonl`，并保证 Checkpoint 一并落盘。Phase 2 完成后，P9  Observability 可直接复用 duration 数据。

> 本文件为只读审计产物，不修改任何系统代码。
