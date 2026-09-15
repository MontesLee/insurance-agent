# Failure Taxonomy (Step 4 · Phase 6)

> 每一种失败都必须能回答四个问题：**怎么被发现？能不能自动修？修不好怎么办？要不要人？**
> 本文件只描述**当前代码真实存在**的机制，不写"应该有"的东西。每条都标注实现位置与验证用例。

---

## 0. 分层与状态词汇

```
Client → Orchestrator → Skills → Artifacts → Eval → Repair → Checkpoint → Report
```

| 层 | 失败被谁发现 | 终止状态 |
|---|---|---|
| 输入层 | `orchestrator.check_client_information()` | `WAITING_FOR_USER` |
| 编排层 | `state/transitions.py` 四类守卫 | `BLOCKED` |
| 执行层 | 引擎异常 / 服务失败 | 进入 Eval 或直接 `NEEDS_REVIEW` |
| 契约/Eval 层 | `workflow/eval_engine.py` 6 类检查 | `PASS` / `FAIL` |
| 修复层 | `workflow/repair.py` `plan()` | 重跑该 stage 或 `ESCALATE` |
| 状态层 | `workflow/checkpoint.py::validate()` | `CHECKPOINT_INVALID` |

Eval 检查 id 全集（真实存在）：`schema`、`required_fields`、`required_non_empty`、`contamination`、
`evidence_document_chunk`、`recommendation_evidence`、`solution_gap_refs`、`gap_risk_refs`、
`gap_requirement_refs`、`catalog_exists`、`candidate_known`。

---

## F1 — Input Failure（客户事实缺失 / 冲突）

- **原因**：blocking 字段（`existing_protection.existing_insurance` / `family_profile.age` /
  `financial_profile.annual_income`）为 `UNKNOWN`，或 `conflicts[]` 非空。
- **检测**：`orchestrator.rules.json → insufficient.blocking_fields`；`also_block_when_status_unknown: true`。
- **可否自动修复**：**否**。机器不得替客户编造事实，也不得在冲突里择一。
- **修复策略**：生成 `next_questions` 交回客户；`status=WAITING_FOR_USER`，下游 stage 全部保持 `PENDING`。
- **是否需人工**：不需要（客户回答即可继续），但**必须由人提供事实**。
- **验证**：benchmark `bm-insufficient-001..004`、`bm-conflict-001..005`；golden `G-002`、`G-003`。
  反向对照 `bm-insufficient-005`（非 blocking 字段未知 → **不得**误停，防止"宁可错停"式假安全）。

## F2 — Requirement Failure（需求层产物不合格）

- **原因**：`requirement-analysis` 缺 `payload`，或产物**污染**（泄漏具体产品/公司/购买措辞），
  或引用不存在的上游 id。
- **检测**：`required_fields` + `contamination`（含运行时加载的 Catalog 词表）+
  `gap_requirement_refs`（下游反查）。
- **可否自动修复**：**否**（上游为 `executor: provided`，由对话式 Skill 产出，Orchestrator 无重生成能力）。
- **修复策略**：`ESCALATE` → `NEEDS_REVIEW`，并在 `review.failed_checks` 中留下具体 check。
- **是否需人工**：是。
- **验证**：`seed_case()` 对 provided 产物同样跑 Eval（`NON_MONOTONIC`/污染产物不得下推）；
  `tests/workflow/test_step3_mutation.py` M-A/M-C 反向断言。

## F3 — Risk Failure（风险层产物不合格）

- **原因**：`risk-analysis` 缺 `payload.risks`；或风险的 `risk_id` 被下游引用却不存在。
- **检测**：`required_fields`；下游 `coverage-gap-analysis` 的 `gap_risk_refs`（source→target 解析）。
- **可否自动修复**：**否** → `ESCALATE`。
- **是否需人工**：是。
- **验证**：同上（provided 阶段 Eval + 变异测试）。

## F4 — Gap Failure（缺口层）

- **原因**：`payload.gaps` 缺失；或 `gaps[].related_risk_ids` / `related_requirement_ids`
  指向不存在的对象（悬空引用）。
- **检测**：`required_fields`；`gap_risk_refs`、`gap_requirement_refs`。
- **可否自动修复**：**是**。悬空引用 → check id 含 `orphan_refs` → `RERUN_FROM_UPSTREAM`
  （丢弃陈旧产物，从当前上游重新推导）。
- **是否需人工**：仅在修复预算耗尽后。
- **验证**：`repair.rules.json → repairable.cross_artifact_orphan_refs`；`bm-repair-001` 用一次性
  悬空引用证明**真的能自愈**（`repairs_succeeded ≥ 1`），而不是一律转人工。

## F5 — Solution Failure（策略层）

- **原因**：`payload.solutions` 缺失；`solutions[].related_gap_ids` 指向不存在的 gap。
- **检测**：`required_fields`；`solution_gap_refs`。
- **可否自动修复**：**是**（`RERUN_FROM_UPSTREAM`）。
- **是否需人工**：否（修不好才转人工）。
- **验证**：golden `G-008`；benchmark `bm-repair-001`。

## F6 — Evidence Failure（证据层）★ 最典型

- **原因**：知识检索命中 0 条（空语料 / 无该 domain 文档）；或证据缺 `document_id`/`chunk_id`
  导致溯源链断裂。
- **检测**：`required_non_empty(payload.evidence)`；`evidence_document_chunk`（逐条要求
  `evidence_id`+`document_id`+`chunk_id`）。
- **可否自动修复**：**否**。`repair.rules.json` 里这两项**没有** AUTO 动作 → `plan()` 返回 None → `ESCALATE`。
- **修复策略**：`NEEDS_REVIEW`。**绝不允许**用模型记忆补知识。
- **是否需人工**：是。
- **验证**：benchmark `bm-noev-001..003`、`bm-lowrisk-002`；golden `G-005`。
  Demo B 展示完整链路：`Eval FAIL → Repair ×2 → CASE_NEEDS_REVIEW`，trace 里 `TASK_FAILED.detail`
  直接写明 `knowledge-search: EVIDENCE_EVAL_FAIL[...]`。

## F7 — Candidate Failure（候选层）

- **原因**：候选的 `product_id` 不在 Catalog；或（历史缺陷）年龄等关键字段读不到导致全部候选
  `ELIGIBILITY_UNKNOWN`。
- **检测**：`catalog_exists`（`candidates[].product_id` ∈ Catalog）。
- **可否自动修复**：**是** → `DROP_INVALID_PRODUCTS`（只从 stage input 剔除非法候选后重跑，
  **绝不**发明替代产品）。
- **是否需人工**：预算耗尽后。
- **验证**：`bm-adv-invalid-product`（注入 `P999`）；golden `G-007`（断言非法 id 不出现在任何
  已登记 artifact 中）。空清单 = 全量放行这类"空列表短路"缺陷已在 Step 2 修复并有守卫。

## F8 — Recommendation Failure（推荐层）

- **原因**：推荐了不在 `admissible_candidate_ids` 里的候选；无候选却仍给主推荐；推荐状态与
  证据状态自相矛盾。
- **检测**：`candidate_known` 不变式；`recommendation_evidence`（`evidence_refs` 至少 1 条且能在
  `knowledge-evidence` 中解析）；引擎内状态优先级（不可保 > 缺证据 > 匹配度不足）。
- **可否自动修复**：**否** → `ESCALATE`。
- **是否需人工**：是。
- **验证**：Step 3 修复的状态优先级 bug（不可保候选被误标 `INCOMPLETE_EVIDENCE`）由
  `case-002/004/005` 三向自洽锁死；benchmark `bm-nocand-001..003`、golden `G-004`。

## F9 — Orchestration Failure（编排层）

- **原因**：绕过顺序 / 缺前置产物 / 读未放行产物 / 完成后篡改产物。
- **检测**：`runtime/state/transitions.py` 四个守卫，机检码：
  `NON_MONOTONIC`、`MISSING_INPUT_ARTIFACT`、`INPUT_NOT_RELEASED`、`ARTIFACT_MUTATION`。
- **可否自动修复**：**否**。这是**结构错误**，不是数据错误。
- **修复策略**：`BLOCKED`（或 `CHECKPOINT_INVALID`），并且 **gate 重试不可绕过**。
- **是否需人工**：是（属实现/配置缺陷）。
- **验证**：`tests/e2e/test_orchestration_invariants.py`（21/21，含负向探针）；
  `tests/workflow/test_step3_orchestrator_self_eval.py` SE-1/SE-2/SE-5。

## F10 — Eval Failure（评估自身失败）

- **原因**：规则指向不存在的字段/路径；schema `$ref` 解析失败；跳过规则误配置。
- **检测**：Eval 引擎第三态原则 —— **无法评估 = FAIL**，不存在 `MANUAL`/`UNKNOWN` 通过
  （`eval_engine.py` 文件头注释即为契约）。
- **可否自动修复**：否 → `NEEDS_REVIEW`。
- **是否需人工**：是。
- **验证**：`verify-contract.py` 校验规则引用；`skipped` 只在 `skip_artifact_when` 显式命中时产生，
  且**不计入通过**（`test_step3_mutation.py` M-B0 正是断言"被跳过的产物不是因为通过才被跳过"）。

## F11 — Repair Failure（修复失败）

- **原因**：`plan()` 找不到可用动作；动作执行后 `changed=False`；预算耗尽（`max_repairs: 2`，
  `max_attempts: 3`）。
- **检测**：`repair.plan()` 返回 None；`repair.apply()` 返回 `changed=False`；`attempt >= max_attempts`。
- **可否自动修复**：否（修复本身失败）。
- **修复策略**：`NEEDS_REVIEW`，并完整保留 `failed_checks` + `repair_attempts` + 修复轨迹。
- **是否需人工**：是。
- **验证**：benchmark `bm-noev-*`（Eval 失败不可修）、`bm-adv-*`（故障持续注入，重试不可绕过）；
  演示 `Repair #1/#2` 出现在 trace 且计数 == 2。

## F12 — State / Checkpoint Failure（状态层）

- **原因**：checkpoint 与 `case_id` 不匹配；schema 不再合法；artifact 指纹与登记不符（被篡改）；
  task 指向未知 stage。
- **检测**：`checkpoint.validate()`，统一报 `CHECKPOINT_INVALID` + 具体原因。
- **可否自动修复**：**否**。绝不"跳过校验继续跑"。
- **修复策略**：`load()` 返回 `(None, reasons)`；恢复策略是**回退到上一个合法 checkpoint**，
  由人决定。
- **是否需人工**：是。
- **验证**：`test_step3_mutation.py` M-D（篡改已 checkpoint 的产物 → `CHECKPOINT_INVALID`；
  未篡改 → 正常加载），含反向断言。

---

## Failure Matrix

| Failure | Detect | Retry | Repair | Human Review |
|---|---|---|---|---|
| F1 客户事实缺失 | `check_client_information` | No | Ask user（生成 next_questions） | No（客户回答） |
| F1' 客户事实冲突 | 同上（`conflicts[]`） | No | Ask user（保留双候选） | No |
| F2 需求产物不合格 | `required_fields` / `contamination` | No | ESCALATE | Yes |
| F3 风险产物不合格 | `required_fields` / `gap_risk_refs` | No | ESCALATE | Yes |
| F4 缺口悬空引用 | `gap_*_refs_orphan_refs` | Yes | `RERUN_FROM_UPSTREAM` | 预算耗尽后 Yes |
| F5 策略悬空引用 | `solution_gap_refs_orphan_refs` | Yes | `RERUN_FROM_UPSTREAM` | 预算耗尽后 Yes |
| F6 证据缺失 | `required_non_empty` | Yes（重跑，但无动作可改） | ESCALATE | Yes |
| F6' 证据断链 | `evidence_document_chunk` | Yes | ESCALATE | Yes |
| F7 非法产品 | `catalog_exists` | Yes | `DROP_INVALID_PRODUCTS` | 预算耗尽后 Yes |
| F8 推荐越界 | `candidate_known` / `recommendation_evidence` | No | ESCALATE | Yes |
| F9 编排越界 | transitions 四守卫 | No | Blocked（重试不可绕过） | Yes |
| F10 Eval 不可判定 | 第三态 = FAIL | No | — | Yes |
| F11 修复失败 | `plan()==None` / `changed=False` / 预算耗尽 | 至 `max_attempts` | NEEDS_REVIEW | Yes |
| F12 状态损坏 | `checkpoint.validate` | No | 回退上一 checkpoint | Yes |

> 表中「Retry」列一律受 `max_attempts = 3`（初始 + 2 次修复）硬约束 —— **失败后不是无限重试**。
> 这条约束由 `repair.rules.json` 声明、由 `_execute_stage` 强制执行、由 `bm-adv-*` 证明（持续故障
> 下重试到预算耗尽即停，绝不无限循环）。

---

## 覆盖情况

| Failure | 有专门测试 | 用例 |
|---|---|---|
| F1 / F1' | ✅ | benchmark ×10、golden G-002/G-003 |
| F2 / F3 | ✅ | seed 阶段 Eval + 变异测试 M-A/M-C |
| F4 / F5 | ✅ | bm-repair-001、golden G-008 |
| F6 / F6' | ✅ | bm-noev-001..003、bm-lowrisk-002、golden G-005、Demo B |
| F7 | ✅ | bm-adv-invalid-product、golden G-007 |
| F8 | ✅ | bm-nocand-001..003、golden G-004、Step 2 E2E |
| F9 | ✅ | orchestration-invariants 21/21、SE-1/2/5 |
| F10 | ✅ | M-B0、契约校验 |
| F11 | ✅ | bm-adv-*、trace 修复计数断言（P9） |
| F12 | ✅ | M-D、SE-4（resume 不重跑 PASS） |
