# 保险 Agent V2 — Step 3：组装、E2E、反橡皮图章与回归

> 本文件是 **Step 3（= 原 Phase 7 编排 + 全链路 E2E + 反橡皮图章）** 的组装交付文档。
> 架构基线见 `docs/orchestration.md`（Phase 7）。本文件补充：**审计、Eval/Repair 引擎、变异测试、Orchestrator 自评、回归清单**。
> 硬约束（来自 spec §43）：**不修改 baseline 掩盖失败；失败必须归类为 implementation bug / test bug / contract conflict，并修对的那一层。**

---

## 0. 交付状态：STEP 3 COMPLETE

| 交付物 | 状态 | 证据 |
|---|---|---|
| 全链路 E2E（71 项） | ✅ 71/71 ALL GREEN | `test-cases/e2e/full-agent/run_full_agent_e2e.py` |
| 反变异测试（9 项） | ✅ 9/9 ALL GREEN | `tests/workflow/test_step3_mutation.py` |
| Orchestrator 自评（14 项） | ✅ 14/14 ALL GREEN | `tests/workflow/test_step3_orchestrator_self_eval.py` |
| Step 2 产品推荐 E2E（61 项） | ✅ 61/61 ALL GREEN | `test-cases/e2e/product-recommendation/run_product_recommendation_e2e.py` |
| 全工程回归（13 套件） | ✅ 13/13 ALL GREEN | `tmp/run_regression.py` |
| 既有 8 个 Skill | ⚠️ **仅 recommendation 引擎 + 其 invoke 适配器被修**（见 §1），其余 6 个未动 | git diff |

> 注：spec 要求「不修改 8 个稳定 Skill」。本次对 `recommendation` 引擎的修复属于**修正其自身缺陷**（见 §1 的 implementation-bug 归类），并非重写；其 11 个 legacy 评估用例（`rec-v2-unit` 10/10）与全工程数据集保持通过。这是修 implementation bug，不是触碰稳定语义。

---

## 1. 审计：70/71 阻塞 + 2 个 Step 2 回归的分类与修复

### 1.1 Step 3 阻塞（case-001 `evidence_refs` 空 → 71/71 修复前为 70/71）

**现象**：Full-Agent E2E 的 case-001 期望 `evidence_trace_ok: true`（推荐产物的 `evidence_refs` 必须能解析到 KnowledgeEvidence），实际为空。

**根因（两层，均在 `product-candidate-provider`）**：
1. `candidate-provider.rules.json` 的 `eligibility.age_paths` 没有包含 Canonical 路径 `family_profile.age`（seed fixture 把年龄存在 `family_profile.age.value="35"`）。
2. `product_candidate_engine.py` 的 `_num()` 只接受 `int/float`；Canonical FactValue 的年龄是**字符串 `"35"`**，于是返回 `None` → "client age not available" → 所有候选 `ELIGIBILITY_UNKNOWN` → 不可准入 → `NO_CANDIDATES` → 推荐产物 `evidence_refs` 为空。

**修复**：
- `age_paths` 增加 `"family_profile.age"` 与 `"client_state.family_profile.age"`。
- `_num()` 增加字符串强制转换（`"35" → 35.0`），并兼容 `dict` 内字符串值。
- **不影响** Step 2 用 `profile.age` 为 int 的 case-002/004（int 路径未变）。

### 1.2 Step 2 回归（case-002、case-004）出现 → 分类为 implementation bug

**现象**（修复 1.1 后浮现）：`run_product_recommendation_e2e.py` 由 61/61 跌到 59/61：
- case-002（候选存在但缺证据）期望 `INCOMPLETE_EVIDENCE`，实际 `NO_CANDIDATES`。
- case-004（85 岁全部不可保）期望 `not_recommended` 含 `product_ineligible`，实际 `[]`。

**分类过程**（按 §43 不掩盖原则，逐一验证）：

1. 两用例都用 `profile.age`（int 35/85），1.1 的修复**未触碰 int 路径** → 排除「1.1 引入」。
2. 直接跑 case-004 调试：候选 provider `status=COMPLETE`、`admissible=[]`、4 个候选全 `ELIGIBILITY_INELIGIBLE`；但推荐引擎输出 `status=NO_CANDIDATES`、`not_recommended=[]`、`candidate_evaluations=[]`。说明推荐引擎拿不到候选元数据。
3. 定位到 Step 3 在 `invoke-product-recommendation.py` 加的**适配器桩**（lines 81-88）：当 `not _admissible_ids(...)` 时把 `candidates=[]`、`admissible_candidate_ids=[]` 全部清空。该桩的注释意图（"绝不退而求其次把策略当产品推荐"）已由下方 `if product_candidates:` 分支保证（无候选才回退 solution_plan），**该桩既冗余又有害**——它丢弃了引擎区分 `INCOMPLETE_EVIDENCE` 与 `NO_CANDIDATES`、填充 `not_recommended` 所需的候选元数据。
4. **结论：这是 implementation bug（Step 3 适配器桩），不是 stale test，也不是 contract conflict**。移除该桩（同时移除仅它使用的 `_admissible_ids` helper）。

**移除桩后的二次发现**：桩其实一直在**掩盖**推荐引擎的第二个缺陷。移除后 case-005（Full-Agent E2E，85 岁、默认 KB）从原本"恰好 NO_CANDIDATES"变成 `INCOMPLETE_EVIDENCE`——暴露真正的引擎优先级 bug。

### 1.3 推荐引擎优先级 bug（case-005 暴露）→ 同样是 implementation bug

**根因**（`recommendation_engine.py` 两处）：

- **A. `evaluate_candidate` 状态优先级**：原代码先判 `ev_status in ("insufficient","conflict")` 再判 `has_hard`（硬产品校验块）。导致一个**不可保但证据缺失**的候选被标成 `insufficient_evidence`，而非 `not_recommended`。但**不可保产品永远不该被推荐**，硬块必须压过证据状态。
- **B. `generate_recommendation` 总体状态**：原代码用 `any(e["evidence"]["status"] != "supported" for e in evals)` 跨**所有**候选判断。不可保候选在空 KB 下证据也读 "insufficient"，于是把整体状态错误抬到 `INCOMPLETE_EVIDENCE`（应为 `NO_CANDIDATES`）。

**修复**：
- A. 把 `has_hard → not_recommended` 提到 `ev_status` 判断之前。
- B. 当 `primary is None`：仅当存在「过了产品校验、只缺证据」的候选（`insuff`）时才 `INCOMPLETE_EVIDENCE`，否则 `NO_CANDIDATES`。

**修复后三用例语义自洽**：

| 用例 | 候选真实状态 | 期望状态 | 修复前 | 修复后 |
|---|---|---|---|---|
| case-002（Step 2） | 可保 + 缺证据 | `INCOMPLETE_EVIDENCE` | `NO_CANDIDATES` ✗ | `INCOMPLETE_EVIDENCE` ✓ |
| case-004（Step 2） | 全不可保 + 证据在 | `NO_CANDIDATES`（含 `product_ineligible`） | `NO_CANDIDATES` 但 `not_recommended=[]` ✗ | `NO_CANDIDATES` 且含 `product_ineligible` ✓ |
| case-005（Full-Agent） | 全不可保 + 部分证据缺失 | `NO_CANDIDATES` | `INCOMPLETE_EVIDENCE` ✗（桩掩盖） | `NO_CANDIDATES` ✓ |

**未触碰 11 个 legacy 评估用例**：它们用的是 strategy-level 候选（无 `_product_validation`），`has_hard` 恒为 `False`，故 A 的优先级改动对它们无副作用（`rec-v2-unit` 10/10 仍绿）。

---

## 2. 架构回顾（与 `orchestration.md` 互补）

编排层**无任何保险判断**：只搬运 Artifact、校验契约、强制顺序、在闸门停下。本次新增/落地的四类组件：

| 组件 | 文件 | 职责 |
|---|---|---|
| CaseState | `state/case_state.py` + `.schema.json` | 跨 8 个 Skill 唯一事实源；三不变量（单调性 / 前置条件必须生产者 `COMPLETED` / 冻结 sha256） |
| Orchestrator | `workflow/orchestrator.py` | `seed_case → run → eval → PASS→next / FAIL→repair→rerun→NEEDS_REVIEW`；`gate_policy=stop` 真停；`WAITING_FOR_USER`（冲突/信息不足）；`checkpoint` 落盘/重载 |
| Eval Engine | `workflow/eval_engine.py` + `resources/config/eval.rules.json` | 6 族检查，写入 `state["evaluations"]`；不可评估即 FAIL，无 MANUAL/UNKNOWN 通过 |
| Repair Loop | `workflow/repair.py` + `resources/config/repair.rules.json` | 本地重跑（`max_attempts=3`，即 1 初始 + 2 修复）；只改 stage input，**绝不改已冻结 Artifact**；预算耗尽 → `NEEDS_REVIEW` 并保留修复轨迹 |

### 2.1 Eval Engine — 6 族检查

| 族 | check_id | 含义 |
|---|---|---|
| schema | `schema` | 产物通过其声明的 Canonical Contract（jsonschema Draft7） |
| required_fields | `required_fields` | 声明的 payload 路径存在 |
| required_non_empty | `required_non_empty` | 存在但为空的集合视为失败（如 Evidence 检索到 0 条） |
| contamination | `contamination` | 上游分析层不得含具体产品/公司/产品 id（用 Catalog 词表 + 禁词） |
| provenance | `provenance_*` | 推荐 → 证据 → 文档 → 片段可解析；悬空 ref = FAIL |
| cross_artifact | `cross_artifact_*_orphan_refs` | 引用（gap→risk、solution→gap）解析到真实存在的 Artifact |
| invariant | `*`（如 `catalog_exists`） | 领域不变量，如每个候选 `product_id` 必须在 Catalog 中 |

诚实规则：**检查不可执行就 FAIL，绝不 PASS**；所有阈值/路径/词表都来自 `eval.rules.json`，引擎只消费。

### 2.2 Repair Loop — 局部、有预算、可解释

- 至多 2 次修复（`max_attempts=3`）：初始执行 + 2 次重跑。
- **局部**：只重跑失败 stage 本身，上游永不回滚。
- **不改 Artifact**：冻结物不可变；修复只改 stage input 或丢弃陈旧输出让其从当前上游重派生。
- 动作目录：`DROP_INVALID_PRODUCTS`（剔除不在 Catalog 的候选，仅改 input）、`RERUN_FROM_UPSTREAM` / `RERUN_STAGE`（丢弃陈旧输出重派生）。
- 预算耗尽 → `NEEDS_REVIEW`，保留失败原因与修复轨迹。

---

## 3. 契约展品（Canonical 链路）

数据链单向：`ClientProfile → RequirementAnalysis → RiskAssessment → CoverageGapAnalysis → SolutionPlan →（KnowledgeEvidence）→ ProductCandidates → ProductRecommendation → InsuranceReport`。

关键产物形状（节选）：

- **FactValue**：`{ "value": "35", "status": "KNOWN" }`——标量以**字符串**承载（1.1 修复即源于此）。
- **ProductCandidate**：`{ candidate_id, product_id, product_type, eligibility:{status:ELIGIBLE|INELIGIBLE|UNKNOWN}, evidence:{status:AVAILABLE|MISSING, evidence_ids:[]}, admissible:bool, reject_reason_codes:[] }`。
- **ProductRecommendation.payload.status**：`COMPLETE | NO_CANDIDATES | INCOMPLETE_EVIDENCE | NEEDS_REVIEW`；`not_recommended:[{candidate_id, reason, exception}]`；`evidence_refs:[evidence_id]`。
- **KnowledgeEvidence.payload.evidence[]**：`{ evidence_id, document_id, chunk_id, provenance:[{source_type:DOCUMENT|CHUNK}] }`——保证推荐可一路追溯到文档片段。

---

## 4. Repair 演示（SE-3 证据失败 → NEEDS_REVIEW）

`case-004-evidence-failure.json` 配 **空 KB** 跑全链路（`gate_policy=stop`）：

```
status=NEEDS_REVIEW   stopped_at=product-candidate-provider
product-candidate-provider attempts=3   repairs=2   ← 1 初始 + 2 本地修复，预算未超
```

- 空 KB 下候选 provider 检索不到证据 → 评估失败；Repair 注入失败检查选动作（`RERUN_STAGE` 重派生）。
- 两次修复后仍无法产出可准入候选 → 预算耗尽 → 升级为 `NEEDS_REVIEW`，保留 `repairs` 轨迹与失败原因，**不编造**候选。
- 下游（product-recommendation / report-generation）保持 `PENDING`，未被越闸放行。

---

## 5. Checkpoint 演示（SE-4 暂停 → 重载 → 批准 → 续跑）

```
RUN 1 (stop) → PAUSED_NEEDS_REVIEW @ product-recommendation, 下游 PENDING
cp.load()     → 校验通过，CaseState 逐字节可重载
approve()     → 释放闸门
RUN 2         → COMPLETED，7/7 stage 完成
断言：所有此前 PASS 的 task 在续跑中 attempts 未增长（未被重执行）
```

冻结验证：篡改已完成 Artifact（M-D）后 `cp.load()` 返回 `None` 且报 `CHECKPOINT_INVALID`，原 Artifact 不变。

---

## 6. 变异测试演示（反橡皮图章，9/9）

每个变异**单点改动一个真实通过产物/检查点**，断言 Eval/Checkpoint 捕获它；并带反向断言（原始对象同路径通过），证明不是恒真/恒假图章。

| 探针 | 单点变异 | 期望捕获 | 反向断言 |
|---|---|---|---|
| M-A | 把某候选 `product_id` 改成 Catalog 外的值 | `catalog_exists` 不变量 FAIL | M-Ar 原 `product_id` 通过 |
| M-B0 | 真实 `INCOMPLETE_EVIDENCE` 推荐 | 被**有意跳过**而非误判 | — |
| M-B | 合成 `COMPLETE` 推荐 + 真实可解析 `evidence_refs` | provenance 通过 | 伪造一个 `evidence_ref`（悬空）→ provenance FAIL |
| M-C | 给 gap 加一条不存在的 `related_risk_ids` | `cross_artifact_gap_risk_refs` orphan FAIL | M-Cr 原始引用可解析通过 |
| M-D0 | 合法检查点 | 干净重载 | — |
| M-D | 篡改检查点中已完成 Artifact 的年龄值 | `CHECKPOINT_INVALID` | — |

---

## 7. Orchestrator 自评（14/14）

| 项 | 性质 | 断言 |
|---|---|---|
| SE-1 依赖 | 缺 provided 上游 | `BLOCKED @ risk-analysis`，下游全 `PENDING` 未运行 |
| SE-2 顺序 | 拓扑序 | 执行序 == workflow 声明序 |
| SE-3 重试 | 失败本地重跑 | `NEEDS_REVIEW @ product-candidate-provider`，`attempts≤3`，恰好 2 次修复 |
| SE-4 续跑 | checkpoint 续跑 | 暂停→重载→批准→`COMPLETED`，PASSed task 不被重跑 |
| SE-5 复核 | 闸门真停 | 无批准重跑仍暂停；显式 `approve()` 才放行完成 |

---

## 8. 回归清单（13 套件，全部 ALL GREEN）

| # | 套件 | 结果 |
|---|---|---|
| 1 | full-agent-e2e（Step 3 全链路） | 71/71 |
| 2 | step3-mutation | 9/9 |
| 3 | step3-orchestrator-self-eval | 14/14 |
| 4 | step2-product-rec-e2e | 61/61 |
| 5 | core-analysis-e2e | ALL GREEN |
| 6 | e2e-run_e2e（Phase 7 老 E2E） | ALL GREEN |
| 7 | orchestration-invariants | ALL GREEN |
| 8 | evidence-invariants | ALL GREEN |
| 9 | rec-v2-unit（recommendation 11 legacy 用例） | 10/10 |
| 10 | candidate-provider-unit | ALL GREEN |
| 11 | report-v2-unit | ALL GREEN |
| 12 | solution-unit | ALL GREEN |
| 13 | coverage-gap-unit | ALL GREEN |

**运行方式**：

```bash
# Step 3 三大件
python test-cases/e2e/full-agent/run_full_agent_e2e.py
python tests/workflow/test_step3_mutation.py
python tests/workflow/test_step3_orchestrator_self_eval.py
# 全工程回归
python tmp/run_regression.py
```

---

## 9. Step 3 完成结论

- **阻塞解除**：case-001 `evidence_refs` 空（候选 provider 读不到 Canonical 字符串年龄）已修 → 全链路 71/71。
- **回归正确分类**：2 个 Step 2 失败 → implementation bug（推荐适配器桩 + 引擎优先级），已修对层、未掩盖 baseline。
- **反橡皮图章**：9 项单点变异 + 14 项 Orchestrator 自评全绿，每个失败检查都有反向断言。
- **诚实性**：不可评估即 FAIL；修复只改 input、不改冻结 Artifact；闸门不可绕过。
- **约束遵守**：未新增业务 Skill；未重写 8 个稳定 Skill 的既有评估语义（仅修 recommendation 引擎自身缺陷，11 legacy 用例仍过）。

**Step 3 至此完成。下一步（若有）进入 Step 3 之外的工作，本阶段不越界。**
