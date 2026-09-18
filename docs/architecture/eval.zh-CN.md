# Eval 与 Repair —— 质量边界

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](eval.md)

事实来源：`runtime/eval_engine.py`、`runtime/repair.py`、
`runtime/harness/harness.py`（`_run_eval_and_repair`）、
`runtime/resources/config/eval.rules.json`。

## 1. 边界

```text
Agent → 工具 → artifact 候选 → ARTIFACT_READY
        ↓
     HARNESS
        ↓
     Eval ──PASS──▶ 继续（checkpoint、下一批任务）
        └──FAIL──▶ Repair（≤ 2）→ 重跑 agent → Eval
                       └──耗尽──▶ NEEDS_REVIEW（下游 BLOCKED）
```

- **Agent** 永不判 PASS。**工具**在 agent 模式下不做评估
  （`skip_eval=True`）。**Worker** 无法自评 —— 并行模式下只有 eval 分支
  能产生 PASS（有"试图自评的 executor"回归测试）。**LLM** 不给任何
  东西打分。
- **Harness** 拥有 Eval、Repair、Retry 与 NEEDS_REVIEW。这是本运行时
  最重要的所有权规则。

## 2. Eval 引擎（确定性、规则驱动）

每个 artifact 都由确定性检查评估；阈值、路径与词表全部来自
`eval.rules.json` —— 引擎不硬编码任何判断：

| 检查族 | 证明什么 |
| --- | --- |
| `schema` | artifact 通过其声明的规范契约 |
| `required_fields` | 声明的 payload 路径存在 |
| `required_non_empty` | "存在但为空"也算失败（如证据检索一无所获） |
| `contamination` | 分析层不泄漏具体产品/公司 |
| `provenance` | 推荐 → 证据 → 文档链可解析 |
| `cross_artifact` | artifact 间引用（缺口→风险、方案→缺口）可解析 |
| `invariant` | 领域不变量，如候选 `product_id` 必须在目录中 |

诚实规则：无法评估的检查报 FAIL，绝不报 PASS —— 没有 MANUAL/UNKNOWN
通过。eval 记录以顺序编号（`EVAL-%03d`）追加进 CaseState
（`evaluations`）。

## 3. Repair（有界、局部、绝不改写 artifact）

```text
eval FAIL
 ↓ 失败检查 → repair.plan()（规则驱动的动作映射）
可修复（catalog_exists、cross_artifact_orphan_refs）
    → 重跑 agent（artifact 已冻结；repair 是重新产出）
    → 重新 eval                                    ── 最多 2 次 repair
不可修复 → 立即 NEEDS_REVIEW
预算耗尽（1 次初始 + 2 次 repair）→ NEEDS_REVIEW
```

- Repair 绝不编辑已产出的 artifact —— artifact 是冻结的；repair 改变的
  是生产路径并重跑。
- 上游永不回滚；只有失败的任务重试。
- 精确预算（代码与测试双重验证）：**每个任务最多 2 次 repair、3 次
  执行**。

## 4. 与参考模式的一致性

在前 agent 时代的确定性运行时里，`_execute_stage` 在 stage runner 内部
运行同一个 eval 引擎（对话式播种的 artifact 同样过门禁）。agent 时代
把 eval 的**所有权**移到 Harness，但 eval 的**严格度**没变 —— 同一份
规则文件、同一套检查。

## 5. 可观测性

Eval 与 repair 发出完整生命周期（trace 里的
`EVAL_STARTED/COMPLETED`、`REPAIR_STARTED/COMPLETED/EXHAUSTED`；
runtime 事件 `eval_started`、`eval_passed/failed`、`repair_*`）。边界
本身的测试覆盖：`tests/runtime/test_eval_boundary.py`（工具不评估；
harness 评估；每次尝试恰好一次 eval；repair 会重新评估；repair 有界；
agent/工具不能自评 PASS）。
