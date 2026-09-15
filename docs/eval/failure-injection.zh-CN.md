> 🌐 **Language:** 🇺🇸 [English](failure-injection.md) · 🇨🇳 中文

<a id="failure-injection"></a>

# 故障注入

本文档描述了运行时被明确测试所针对的**对抗性故障场景**。这些是**运行时可靠性测试**，而非业务场景。它们是有意构造的敌对输入，旨在证明智能体能够*安全地失败*，而不是给出一个看似合理却错误的答案。

测试框架注入每一个故障，然后验证整条链路：

```
Inject failure → Eval FAIL → Repair → Re-evaluate → (PASS | FAIL → retry, max 2) → NEEDS_REVIEW
```

<a id="scenarios-f1f6"></a>

## 场景（F1–F6）

| 故障 | 注入方式 | 预期行为 |
| --- | --- | --- |
| **F1 — Schema 违规** | 格式错误 / 缺失必填字段的产物 | Eval **FAIL**；阶段被阻断，永不向下传播 |
| **F2 — 缺失证据** | 空知识库 | 自修复 ×2 → **NEEDS_REVIEW**（不编造） |
| **F3 — 不符合资格的产品** | 不可能的资格判定（例如年龄超出范围） | 候选产品被标记为 `ELIGIBILITY_INELIGIBLE` → `NO_CANDIDATES` / 不被推荐 |
| **F4 — 幻觉产品** | 未知 / 非产品目录的产品 ID | 在推荐 + 报告边界处被阻断；`primary = 0`，`unverified_products = []` |
| **F5 — 缺失证据溯源** | 无效 / 空的 `chunk_id` 引用 | 被证据溯源评估拒绝；主张不被采纳 |
| **F6 — 无效续跑** | 格式错误的产物引用 / 被篡改的检查点 | `CHECKPOINT_INVALID` / 跨产物失败；自修复或阻断 |

<a id="why-these-matter"></a>

## 为何重要

基准测试的常规用例证明了智能体*能够*成功。这些用例证明了智能体*知道何时必须拒绝*。一个仅在精选输入上展示成功的智能体，并没有证明可靠性——它证明的只是运气。

每个场景都通过以下方式覆盖：

- 在 `evals/agent-benchmark/` 中的显式负面用例（adversarial + insufficient_evidence + no_candidates 系列），
- `tests/workflow/test_step4_phase13_guardrails.py` 中的护栏断言（`FABRICATED_PRODUCT` 等），
- `tests/workflow/test_step3_mutation.py` 中的变异测试（被篡改的产物、孤儿引用、检查点篡改）。

<a id="observed-behavior-real-runs"></a>

## 观测到的行为（真实运行）

- **F2 (bm-noev-001)：** 3 次评估失败（1 次初始 + 2 次修复）→ `CASE_NEEDS_REVIEW`；knowledge-evidence `status = insufficient_evidence`，`evidence = []`；无推荐产物。
- **F4 (bm-adv-invalid-product)：** 推荐 `primary = 0`，`unverified_products = []`，报告未提及任何产品——由 `FABRICATED_PRODUCT` 护栏与黄金用例 G-007 独立确认。
- **F3：** 不符合资格的候选产品 `C004 (P011)` 通过 `ELIGIBILITY_INELIGIBLE` 被报告为 `not_recommended`，而符合资格的 `C001 (P001)` 被推荐。

> **设计立场：** 智能体不要求总是成功。它要求的是**安全地失败**。
