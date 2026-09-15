> 🌐 **Language:** 🇺🇸 [English](demo-b.md) · 🇨🇳 中文

<a id="demo-b--safe-failure-path-bm-noev-001"></a>
# Demo B — 安全失败路径 (`bm-noev-001`)

**目的：** 当知识库无法支撑一条推荐时，展示该智能体**安全地失败**，而非编造证据。

```bash
python demo.py demo-b
```

<a id="setup"></a>
## 准备工作

本用例以**空知识库**预先注入。没有任何文档语料可供检索证据。上游的 client/requirement/risk 阶段与 Demo A 中一样被预置；失败被注入在证据边界处。

<a id="what-the-runtime-does"></a>
## 运行时执行的内容

```
Empty Knowledge Base
   → Knowledge Search returns insufficient_evidence (evidence = [])
   → product-candidate-provider Eval FAIL
   → Repair #1 (RERUN_FROM_UPSTREAM)
   → Eval FAIL (still no evidence)
   → Repair #2 (RERUN_FROM_UPSTREAM)
   → Eval FAIL (still no evidence)
   → Repair budget exhausted (max 2 repairs)
   → CASE_NEEDS_REVIEW
```

<a id="verified-results-from-the-real-run-artifacts"></a>
## 已验证结果（来自真实运行产物）

- `knowledge-evidence` 产物：`status = "insufficient_evidence"`，`evidence = []`。
- `product-candidate-provider` 评估**失败 3 次**（1 次初始 + 2 次修复），根因相同：
  ```
  EVIDENCE_EVAL_FAIL[EVAL-006]: required_non_empty(empty: payload.evidence);
  provenance_evidence_document_chunk(no nodes at payload.evidence[])
  ```
- 每次失败都触发 `REPAIR_STARTED` → `REPAIR_COMPLETED`（`action=RERUN_FROM_UPSTREAM`），该动作重新运行了上游的证据获取。由于没有语料，重新运行无济于事——而系统**并未**编造证据来跳出循环。
- 在第 2 次修复后，编排器（Orchestrator）发出 `CASE_NEEDS_REVIEW`（`repair_exhausted: product-candidate-provider`）。
- `case_state.status = "NEEDS_REVIEW"`；**未创建任何 `product-recommendation` 产物**，因此**报告中不出现任何产品**。

<a id="excerpt-from-the-execution-trace-tracejsonl"></a>
### 执行链路摘录（`trace.jsonl`）

```
SKILL_COMPLETED  coverage-gap-analysis   eval_status=PASS
SKILL_COMPLETED  solution                eval_status=PASS
TASK_FAILED      product-candidate-provider  EVAL-006 required_non_empty(empty: payload.evidence)
REPAIR_STARTED   product-candidate-provider  action=RERUN_FROM_UPSTREAM
TASK_FAILED      product-candidate-provider  EVAL-007 required_non_empty(empty: payload.evidence)
REPAIR_STARTED   product-candidate-provider  action=RERUN_FROM_UPSTREAM
TASK_FAILED      product-candidate-provider  EVAL-008 required_non_empty(empty: payload.evidence)
CASE_NEEDS_REVIEW repair_exhausted: product-candidate-provider
```

<a id="why-this-is-the-important-demo"></a>
## 为何这是重要的一次演示

> 有趣的行为**并非**智能体失败了。
> 有趣的行为是它**安全地停下**，而非编造一个产品来填补缺口。

一个总是"成功"的系统并不可靠。一个*可预测、可解释、且不产生幻觉地*失败的系统，才是 Agent Systems 工程师真正在售卖的东西。
