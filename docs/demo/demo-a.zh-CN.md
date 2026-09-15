> 🌐 **Language:** 🇺🇸 [English](demo-a.md) · 🇨🇳 中文

<a id="demo-a--successful-path-bm-complete-006-single-medical"></a>
# Demo A — 成功路径 (`bm-complete-006-single-medical`)

**目的：** 展示该智能体完成一次完整的端到端保险分析运行，并产出一项**以证据为依据、经产品目录核验、且被明确标记为演示（demo）**的推荐。

```bash
python demo.py demo-a
```

<a id="pipeline"></a>
## 流水线

```
Input (structured Client State)
   → Requirement
   → Risk
   → Gap (coverage-gap-analysis)
   → Solution
   → Knowledge Search (evidence)
   → Product Candidate Provider
   → Recommendation
   → Report
```

<a id="what-the-runtime-actually-does"></a>
## 运行时实际执行的内容

编排器（Orchestrator）运行完整的 8 阶段链路。上游三个阶段（`client-intake`、`requirement-analysis`、`risk-analysis`）**由精心准备的测试桩（fixture）预先注入**（`executor: provided`）——它们并非在运行时由模型重新生成。从 `coverage-gap-analysis` 阶段开始，**每个阶段都在本地执行、经确定性评估，并写入检查点**。

这正是当前作品集诚实的执行边界：运行时自**结构化客户状态**起被验证。原始的自然语言录入被有意地排除在当前执行边界之外。

<a id="verified-results-from-the-real-run-artifacts"></a>
## 已验证结果（来自真实运行产物）

- 全部 8 个阶段评估为 **PASS**（`EVAL-004` … `EVAL-009`）。
- 检查点 `CP-001` … `CP-006` 在每个阶段完成后保存。
- 主推荐：**P001** — `catalog_version 0.1`，`is_demo = true`，资格判定 `ELIGIBLE`，`evidence_status = AVAILABLE`，附带 `provenance` + `evidence_refs`。
- 报告 `disclosure` 字段：`is_demo = true`，`demo_products = [P001, P002, P003]`，`unverified_products = []`，`catalog_checked = true`。
- 最终案例状态：**`CASE_COMPLETED`**。

<a id="excerpt-from-the-execution-trace-tracejsonl"></a>
### 执行链路摘录（`trace.jsonl`）

```
CASE_STARTED                                  workflow=insurance-analysis
SKILL_COMPLETED  coverage-gap-analysis        eval_status=PASS
SKILL_COMPLETED  solution                     eval_status=PASS
SKILL_COMPLETED  product-candidate-provider   eval_status=PASS
SKILL_COMPLETED  product-recommendation       eval_status=PASS
SKILL_COMPLETED  report-generation            eval_status=PASS
CHECKPOINT_SAVED CP-005 stage=report-generation tasks=8 artifacts=9
CASE_COMPLETED   stages=1
```

<a id="honest-scope-note"></a>
## 诚实的范围说明

> **P001 是一个虚构的演示产品目录条目，仅用于运行时验证。**
> `is_demo = true` 被附带在产品、候选产品、推荐以及报告之上。
> 它**并非**真实的保险产品、保费或保险公司的实际产品。

Demo A 的重点不在于"这是你应该购买的产品"。而在于：*给定一个结构化客户状态，智能体能够产出一个推荐，其每一项主张都可追溯到某个候选产品、某个解决方案、某个保障缺口、某个风险、某个需求，并最终追溯到带有 `document_id` + `chunk_id` 的证据。*
