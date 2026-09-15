> 🌐 **Language:** 🇺🇸 [English](5-minute-demo-script.md) · 🇨🇳 中文

<a id="5-minute-demo-script"></a>
# 5 分钟演示脚本

一份你可以在面试中实时演示的走查脚本。时间均为近似值；重点在于叙事，而非计时。

<a id="000-030-the-one-liner"></a>
## 0:00 – 0:30 — 一句话定位

> "本项目的重点不在于展示一个出色的保险产品推荐。
> 它要回答的是一个问题：**当智能体犯错时，我们如何确保它不会继续自信地滔滔不绝？**"

将 `README.zh-CN.md` 的首屏展示出来：那句一句话定位 + 核心能力清单。

<a id="030-130-architecture"></a>
## 0:30 – 1:30 — 架构

讲解 `docs/architecture/portfolio-architecture.svg` 中的架构图：

```
CaseState → Orchestrator → Skills → Artifacts → Eval → Repair → Checkpoint
```

重点强调**可靠性层（Reliability Layer）**框。工程贡献不在于任何一个单独的技能——而在于环绕它们的*运行时契约*：状态、产物、确定性评估、有界自修复、证据溯源、检查点、链路追踪。

<a id="130-230-demo-a-success"></a>
## 1:30 – 2:30 — Demo A（成功）

```bash
python demo.py demo-a
```

展示一个单一医疗需求的案例完成：8 个阶段全部 `PASS`，检查点已保存，最终报告中 `is_demo = true`、`catalog_checked = true`、`unverified_products = []`。

说：*"该报告中的每一项主张都可追溯到某个候选产品、某个解决方案、某个保障缺口、某个风险、某个需求，并最终追溯到带有 `document_id` + `chunk_id` 的证据。"*

<a id="230-330-demo-b-safe-failure"></a>
## 2:30 – 3:30 — Demo B（安全失败）

```bash
python demo.py demo-b
```

以**空知识库**预置。观察：

```
Eval FAIL → Repair → Eval FAIL → Repair → CASE_NEEDS_REVIEW
```

说：*"智能体找不到证据，于是它停下了——没有产品，没有编造的推荐。"*

<a id="330-415-show-the-trace"></a>
## 3:30 – 4:15 — 展示链路

打开 `tmp/demo/bm-noev-001/.../trace.jsonl`（或渲染后的 `trace.md`）：

```
CASE_STARTED
SKILL_COMPLETED  coverage-gap-analysis   PASS
SKILL_COMPLETED  solution                PASS
TASK_FAILED       product-candidate-provider  EVAL-006
REPAIR_STARTED    product-candidate-provider
TASK_FAILED       product-candidate-provider  EVAL-007
REPAIR_STARTED    product-candidate-provider
TASK_FAILED       product-candidate-provider  EVAL-008
CASE_NEEDS_REVIEW repair_exhausted
```

指出：仅靠事件本身即可读懂因果链——无需进行日志考古。

<a id="415-500-the-benchmark-and-the-honest-boundary"></a>
## 4:15 – 5:00 — 基准测试，以及诚实的边界

展示数字（真实数据，来自 `tmp/run_regression.py` 与基准测试）：

```
30/30 regression   ·   71/71 full-agent E2E   ·   33 benchmark cases   ·   9/9 golden
false-pass = 0
```

然后**主动交代边界**：

> "有一件事我一直刻意保持诚实：当前作品集自**结构化客户状态**起验证 Agent 运行时。
> 原始自然语言 → 客户状态录入**尚不属于**已执行边界的一部分，因此我**不会**将其包装成一个完整的对话式智能体。
> 工程故事讲的是运行时可靠性，而非 NLP 录入。"

将 `docs/interview/stories.md` 与 `docs/interview/interview-guide.zh-CN.md` 交给对方以便追问。
