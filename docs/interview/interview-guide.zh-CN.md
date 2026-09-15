> 🌐 **Language:** 🇺🇸 [English](interview-guide.md) · 🇨🇳 中文

<a id="interview-guide--q-a"></a>
# 面试指南 — 问答

面试官（Agent 开发工程师 / Agent 产品经理）很可能提出的十个问题，每个问题配有 30 秒速答、2 分钟深入解析，以及可精确指向的代码位置。

---

<a id="q1--why-not-just-a-simple-workflow--dag"></a>
## Q1 — 为什么不直接用简单的 workflow / DAG？

**30 秒：** 静态 DAG 假设每一步总是可预测地成功或失败。真实的 agent 会遇到*未知*输入、缺失证据和相互矛盾的事实。我需要的是一个将**状态、产物、评估、修复、证据与检查点作为一等公民概念**来对待的运行时，而不是图中的一个节点。

**2 分钟：** 编排器（Orchestrator）并不会硬编码一个 for 循环。每一轮，它会向状态层询问 `next_runnable(state, workflow)` 和 `can_run(state, stage)`。这意味着无法继续推进的阶段（例如没有种子数据、证据缺失）会真正*阻塞*，而非被跳过。DAG 的边在 `insurance-analysis.yaml` 中声明；新增或重排某个阶段只需修改 YAML，而不必改动代码。

**代码：** `runtime/orchestrator.py` · `runtime/state/transitions.py` · `runtime/insurance-analysis.yaml`

<a id="q2--why-do-you-need-a-casestate"></a>
## Q2 — 为什么需要一个 CaseState？

**30 秒：** 因为“agent 当前掌握了什么信息”必须是一个显式的、可查询的、不可变的唯一真相来源，由所有 skill 共享——而不是每个 skill 各自从其自身记忆中重新推导。

**2 分钟：** CaseState 是唯一的共享黑板：产物、产物注册表（血缘 + 指纹）、任务账本、评估、检查点、事件、链路。三项不变量由机器校验：**单调性（monotonicity）**（阶段不可回滚）、**前置条件（preconditions）**（某阶段的产出者必须先达到 `COMPLETED` 才能被消费）、以及**不可变性（immutability）**（已发布的产物若 sha256 发生变化即判定为 `ARTIFACT_MUTATION`）。`UNKNOWN` 是一个一等公民的第三态——缺失数据绝不会被静默地当作 `FALSE` 处理。

**代码：** `runtime/state/case_state.py` · `runtime/state/transitions.py`

<a id="q3--why-not-let-the-llm-judge-its-own-output-eval"></a>
## Q3 — 为什么不让 LLM 判定它自己的输出（eval）？

**30 秒：** 因为*产出*结果的组件无法可信地对其*打分*。评估必须与产出方相互独立。

**2 分钟：** `eval_engine.py` 是一个确定性的规则引擎：执行 `schema`、`required_fields`、`contamination`（上游边界穿越）、`provenance`、`cross_artifact` 以及 `invariant` 校验。任何它无法判定的结果均记为 **FAIL**——不存在 `MANUAL`/`UNKNOWN` 的放行路径。正是这一点，让那些安全闸门（产品幻觉 = 0、证据溯源失败 = 0、非法续作 = 0）值得信赖。

**代码：** `runtime/eval_engine.py` · `runtime/resources/config/eval.rules.json`

<a id="q4--why-is-repair-capped-at-2-attempts"></a>
## Q4 — 为什么修复被限制在 2 次尝试？

**30 秒：** 重试预算是一个*上限，而非配额*。对一个本质上已损坏的输入无限重试，只会放大成本并掩盖根本原因。

**2 分钟：** `repair.py` 将一次失败的校验映射为一个动作（`RERUN_FROM_UPSTREAM`、`DROP_INVALID_PRODUCTS`）。它只改变某个阶段的*输入*，绝不会改动一个已冻结的产物。经过 2 次修复后，该阶段进入 `NEEDS_REVIEW`，由人工（或下游闸门）来决定——agent 不会为了让自身脱离失败而陷入幻觉循环。

**代码：** `runtime/repair.py` · `AGENTS.md` (`MAX_REPAIR_ATTEMPTS = 2`)

<a id="q5--how-does-the-agent-prevent-a-hallucinated-product"></a>
## Q5 — agent 如何防止出现被幻觉出的产品？

**30 秒：** 产品目录是一个显式的信任边界。一个被推荐的产品必须真实存在于目录中，且能通过某个经过校验的候选产品触达——没有任何产品仅凭断言就能进入报告。

**2 分钟：** 三层防护：(1) `product-candidate-provider` 只*生成*候选产品，不做排序；(2) `product-recommendation` 会硬性拒绝任何未通过 `candidate_known` 以及附加的 `catalog_has_primary_product` 不变量的产品（产品 ID 必须存在于 `catalog.product_ids` 中）；(3) 报告层运行一道 `FABRICATED_PRODUCT` 护栏，拒绝任何不在候选集中的产品。一个被幻觉出的 ID（`C999`、`CATALOG_NON_EXISTENT`）会导致 `primary = 0`、`unverified_products = []`，且报告中不出现任何产品。

**代码：** `runtime/resources/config/eval.rules.json` (`candidate_known`, `catalog_has_primary_product`, `catalog_exists`) · `tests/workflow/test_step4_phase13_guardrails.py`

<a id="q6--why-does-provenance-need-document_id--chunk_id"></a>
## Q6 — 为什么证据溯源需要 `document_id` + `chunk_id`？

**30 秒：** 一条仅以“知识库”为背书的断言是不可审计的。你必须能够精确指向支撑它的那句话。

**2 分钟：** 评估要求每一条证据引用都必须携带 `evidence_id` + `document_id` + `chunk_id`。随后，属性级溯源会将某个具体的产品属性与某个具体的文本块进行比对。正是这一点，把“我们认为这覆盖门诊”变成了“文档 #D 的文本块 #X 声明门诊被覆盖”。这也是为什么缺失或空的 `chunk_id` 会被拒绝，而不是被原谅。

**代码：** `knowledge/evidence/` · `runtime/resources/config/eval.rules.json` (`provenance` rule)

<a id="q7--how-is-the-orchestrator-actually-state-driven"></a>
## Q7 — 编排器（Orchestrator）究竟是如何“状态驱动”的？

**30 秒：** 它通过*每一轮查询 case 状态*来决定下一步，而不是执行一段固定的调用序列。

**2 分钟：** 证据：种入一个空的 case，它会**在 `client-intake` 处阻塞**（没有上游种子 → 它不会凭空捏造一个客户）。注入 `INSUFFICIENT`/`CONFLICTING` 的客户信息，它会转入 `WAITING_FOR_USER`，而不是去猜测数值。在一次修复用尽后，它会停在 `NEEDS_REVIEW`。这些状态转移（`next_runnable`、`can_run`、`guard_*`）都独立于任何具体 skill 进行了单元测试。

**代码：** `runtime/state/transitions.py` · `runtime/orchestrator.py` (`run()` main loop)

<a id="q8--how-does-checkpointresume-avoid-re-execution"></a>
## Q8 — 检查点 / 恢复如何避免重复执行？

**30 秒：** 一个已完成的阶段会被带上指纹记录存档；在恢复时，只有非 `PASS` 的任务会运行，而系统会*报告*那些本会被重新运行的 `PASS` 任务（通常为 0）。

**2 分钟：** `checkpoint.py` 在每一个阶段之后保存 `case_state.json` + `checkpoints[]`，随后 `load()` 会执行 5 项校验（存在性、解析、`case_id` 匹配、schema、注册表指纹、任务→阶段完整性）。任何一项失败 → `CHECKPOINT_INVALID`；运行绝不会在已损坏的状态上悄悄继续。恢复只重新运行未完成的工作。

**代码：** `runtime/checkpoint.py`

<a id="q9--why-arent-all-skills-autonomous-agents"></a>
## Q9 — 为什么并非所有 skill 都是自主 agent？

**30 秒：** 因为对于一条可靠性至上的流水线而言，在产出结构化产物的那一层，确定性胜过自主性。

**2 分钟：** 上游的三个阶段（`client-intake`、`requirement-analysis`、`risk-analysis`）为 `executor: provided`——它们以结构化产物的形式到达（在本作品集中，由精心整理的 fixtures 播种而来）。下游的五个阶段（`coverage-gap`、`solution`、`product-candidate`、`product-recommendation`、`report`）为 `executor: python`——确定性、规则驱动、离线、可回归测试。这使得系统中*可验证*的部分完全可由机器校验，并将 LLM 的不确定性排除在安全关键路径之外。

**代码：** `runtime/insurance-analysis.yaml` (`executor:` per stage)

<a id="q10--what-is-the-single-biggest-limitation"></a>
## Q10 — 最大的单一局限是什么？

**30 秒：** 当前的作品集对 Agent Runtime 的验证，是从**结构化客户状态（Structured Client State）**开始的。原始的“自然语言 → 客户状态”接入，**尚不属于**已执行边界的一部分。

**2 分钟：** 具体而言：该 demo 的上游阶段是由 fixtures 播种而来，而非一个在线的“自然语言→状态”模型。我有意**不**将其包装成一个完整的对话式 agent，因为那样会夸大系统的能力。其他坦诚的局限包括：目录为 `is_demo=true`（12 个虚构产品），只有 `coverage_type` 是阻断性的溯源属性（其余为上报 / 非阻断），并且没有生产级基础设施（Redis/Kafka/K8s/multi-tenant）。这些都是范围上的取舍，而非隐藏的缺陷。

**代码 / 文档：** `docs/eval/independent-acceptance-report.zh-CN.md` → "坦诚的局限性" ·
`README.zh-CN.md` → "坦诚的局限性"
