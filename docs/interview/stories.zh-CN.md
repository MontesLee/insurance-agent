> 🌐 **Language:** 🇺🇸 [English](stories.md) · 🇨🇳 中文

<a id="interview-stories--real-engineering-incidents"></a>

# 面试故事 — 真实的工程事故

五个简短的故事，你可以用它们来展示*你究竟是如何思考智能体可靠性的*。每一个都根植于本项目真实的产物/测试。

---

<a id="story-1--the-false-pass"></a>

## 故事 1 — 假通过

我们曾有一个基准测试指标，报告 `product_hallucination_rate = 0%`。看起来很棒。但随后我注意到观测路径是错的：产品嵌套在 `product.product_id` 下，而指标读取的是更浅的路径。检查之所以是绿色的，是因为它从未真正检视过产品——它返回了"未找到任何内容"，并把那当作"没有任何问题"。

**经验教训：** 一个不检视正确字段的绿色测试，比红色测试更糟糕。修复观测之后，一个真正缺失的产品浮出水面。我现在将"0 次失败"视为一个需要去攻破的假设，而不是一个值得庆祝的结果。因此，评估引擎（Eval Engine）禁止 `MANUAL`/`UNKNOWN` 通过路径，并要求每条断言都指向一个真实、存在的字段。

**指向何处：** `runtime/eval_engine.py`（无 `MANUAL` 通过）· `tests/workflow/test_step4_phase13_guardrails.py`。

---

<a id="story-2--when-the-eval-engine-crashed"></a>

## 故事 2 — 当评估引擎（Eval Engine）崩溃时

运行途中，评估引擎（Eval Engine）抛出了 `TypeError: unhashable type: 'list'`。一个列表值字段正在被哈希，用于集合成员检查。危险之处在于：评估中的异常，看起来与"检查未触发"一模一样。如果我们把它吞掉了，一个损坏的产物就会以 PASS 的身份畅通无阻地通过。

**经验教训：** *评估崩溃绝不能与被误认为评估通过相混淆。* 我添加了对称的 `_flatten` / `_scalar` 辅助函数，以便在任何集合操作之前将列表/字典值字段归一化；而对于任何意外输入，引擎返回 `FAIL`/`ERROR` 而不是抛出异常。崩溃是一次失败的检查，绝不是一个静默的通过。

**指向何处：** `runtime/eval_engine.py`（`_flatten`、`_scalar`、`evaluate()` 在意外输入时返回 FAIL）。

---

<a id="story-3--missing-evidence-demo-b"></a>

## 故事 3 — 缺失证据（Demo B）

我们植入了一个知识库为空的用例。一个幼稚的智能体会要么永远卡住，要么——更糟——凭空编造一个理由。我们的智能体未能通过证据评估，尝试了两次 `RERUN_FROM_UPSTREAM`，仍然一无所获，随后**停在了 `NEEDS_REVIEW`**——没有推荐任何产品，报告里也没有任何主张。

**经验教训：** 有界自修复 + 安全失败，才是这个产品本身。有价值的成果不是"它恢复了"，而是"它拒绝说谎"。修复预算（最多 2 次）是一个上界，而非配额——耗尽它会升级给人类，而不是陷入幻觉的循环。

**指向何处：** `docs/demo/demo-b.md` · `tmp/demo/bm-noev-001/.../trace.jsonl`。

---

<a id="story-4--the-hallucinated-product"></a>

## 故事 4 — 幻觉产品

我们向智能体喂入了一个推荐请求，其中点名了一个不存在的产品（`C999` / 未知 ID）。候选产品层、推荐层与报告层各自独立地拒绝了它。最终状态：`primary = 0`，`unverified_products = []`，且报告未提及任何产品。

**经验教训：** 产品目录是一个明确的信任边界。生成与选择是分离的（`product-candidate-provider` 负责生成，`product-recommendation` 负责选择），因此一个产品无法"自我推荐"。一个硬性不变量（`catalog_has_primary_product`）加上报告级别的 `FABRICATED_PRODUCT` 护栏，使幻觉成为一种*结构性的不可能*，而非一种奢望。

**指向何处：** `runtime/resources/config/eval.rules.json` · `tests/eval/test_recommendation_catalog_guard.py`。

---

<a id="story-5--independent-red-team"></a>

## 故事 5 — 独立的红队

开发者自己的测试通过了。那不算验收。我运行了一次独立的评审，它不信任 README、历史记录，也不信任作者自己写的评估：我审阅了代码、注入了故障（F1–F6）、对产物做了变异、读取了链路（trace）、将证据溯源追查到 `chunk_id`，并主动猎寻假通过（`all([])` 空洞真理、被吞掉的异常、未实现的检查）。

**经验教训：** 开发者测试回答的是"我是否造出了我本意要造的东西？"；独立验收回答的是"任何人应该信任这个吗？"红队发现了 **0 个假通过**，并确认了 `30/30` 回归、`71/71` E2E、`33` 个基准测试用例、`9/9` 黄金用例——但它也迫使作出一次诚实的 `PARTIAL E2E` 披露（原始 NL 录入不在已执行的边界内）。那份诚实，才是交付物。

**指向何处：** `docs/eval/independent-acceptance-report.md`。
