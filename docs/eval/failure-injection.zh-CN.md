> 🌐 **Language:** 🇺🇸 [English](failure-injection.md) · 🇨🇳 中文

# 故障注入（Failure Injection）

本文档描述运行时被**显式测试**的**对抗性故障场景**。它们是**运行时可靠性测试**，不是业务场景。
这些输入被有意设计为恶意的，用来证明智能体**安全地失败（fail safely）**，而不是产出一个看起来
 plausible 的错误答案。

测试框架注入每个故障后，验证如下链路：

```
Inject failure → Eval FAIL → Repair → Re-evaluate → (PASS | FAIL → retry, max 2) → NEEDS_REVIEW
```

## 场景（F1–F6）

| 故障 | 注入方式 | 预期行为 |
| --- | --- | --- |
| **F1 — Schema 违规** | 畸形 / 缺必填字段的 artifact | Eval **FAIL**；stage 被阻断，绝不向后传播 |
| **F2 — 证据缺失** | 空知识库 | Repair ×2 → **NEEDS_REVIEW**（不伪造） |
| **F3 — 无资格产品** | 不可能的投保资格（如年龄超范围） | 候选标记 `ELIGIBILITY_INELIGIBLE` → `NO_CANDIDATES` / 不推荐 |
| **F4 — 幻觉产品** | 未知 / 不在 Catalog 中的产品 ID | 在推荐与报告边界被阻断；`primary = 0`，`unverified_products = []` |
| **F5 — 溯源缺失** | 非法 / 空 `chunk_id` 引用 | 被 provenance eval 拒绝；声明不被采纳 |
| **F6 — 非法续跑** | 畸形 artifact 引用 / 被篡改的 checkpoint | `CHECKPOINT_INVALID` / 跨 artifact 失败；自愈或阻断 |

## 为什么这些场景重要

Benchmark 的正常用例证明智能体*能*成功；这些用例证明智能体*知道什么时候不能做*。一个只在
精心挑选的输入上演示成功的智能体，展示的不是可靠性——是运气。

每个场景由以下三层覆盖：

- `evals/agent-benchmark/` 中的显式负向用例（adversarial + insufficient_evidence + no_candidates 三族），
- `tests/workflow/test_step4_phase13_guardrails.py` 中的护栏断言（`FABRICATED_PRODUCT` 等），
- `tests/workflow/test_step3_mutation.py` 中的变异测试（篡改 artifact、孤儿引用、checkpoint 篡改）。

## 实测行为（真实运行）

- **F2（bm-noev-001）：** 3 次评估失败（1 次初始 + 2 次修复）→ `CASE_NEEDS_REVIEW`；
  knowledge-evidence `status = insufficient_evidence`、`evidence = []`；无推荐 artifact。
- **F4（bm-adv-invalid-product）：** 推荐 `primary = 0`、`unverified_products = []`，报告
  不点名任何产品——由 `FABRICATED_PRODUCT` 护栏与 golden case G-007 独立确认。
- **F3：** 无资格候选 `C004 (P011)` 经 `ELIGIBILITY_INELIGIBLE` 报告为 `not_recommended`，
  而有资格的 `C001 (P001)` 被正常推荐。

> **设计立场：** 不要求智能体永远成功。要求它**安全地失败**。
