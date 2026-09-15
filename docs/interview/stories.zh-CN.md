> 🌐 **Language:** 🇺🇸 [English](stories.md) · 🇨🇳 中文

# 面试故事集 —— 真实的工程事件

五个可以讲述的短故事，用来展示你*实际上如何思考智能体可靠性*。每个故事都基于本项目的
真实 artifact / 测试。

---

## 故事 1 —— 假通过（The False Pass）

我们有一个 benchmark 指标上报 `product_hallucination_rate = 0%`。看起来很漂亮。然后我注意到
观测路径写错了：产品嵌套在 `product.product_id` 下，而指标读取的是更浅的路径。检查是绿的，
因为它从未真正检查过产品——它返回「什么都没找到」，然后把那当成「没有问题」。

**教训：** 一个不看正确字段的绿灯，比红灯更糟。修正观测路径后，一个真实存在的产品缺失
浮出了水面。我现在把「0 失败」当作一个要攻击的假设，而不是一个值得庆祝的结果。因此
eval 引擎禁止 `MANUAL`/`UNKNOWN` 通过路径，并要求每条断言都指向真实存在的字段。

**指向哪里：** `runtime/eval_engine.py`（无 `MANUAL` 通过）· `tests/workflow/test_step4_phase13_guardrails.py`。

---

## 故事 2 —— 当 Eval 引擎崩溃时

跑到一半，eval 引擎抛出 `TypeError: unhashable type: 'list'`。一个 list 值字段被拿去做
集合成员检查。危险之处在于：eval 里的异常看起来和「检查没触发」一模一样。如果当时把它
吞掉，一个损坏的 artifact 就会以 PASS 的姿态一路通关。

**教训：** *Eval 崩溃绝不能和 eval 通过混为一谈。* 我加了对称的 `_flatten` / `_scalar`
辅助函数，让 list/dict 值字段在任何集合运算前先归一化，并且引擎对任何意外输入返回
`FAIL`/`ERROR` 而不是抛异常。崩溃就是一次失败的检查，绝不可能是静默通过。

**指向哪里：** `runtime/eval_engine.py`（`_flatten`、`_scalar`、`evaluate()` 对意外输入返回 FAIL）。

---

## 故事 3 —— 证据缺失（Demo B）

我们用一个空知识库构造了一个 case。朴素的智能体要么永远卡住，要么更糟——编造一个理由。
我们的系统触发了证据 eval 失败，尝试了两次 `RERUN_FROM_UPSTREAM`，仍然一无所获，然后
**停在 `NEEDS_REVIEW`**——没有推荐任何产品，报告中没有任何声明。

**教训：** 有界修复 + 安全失败本身就是产品。有价值的结局不是「它恢复了」，而是「它拒绝
撒谎」。修复预算（最多 2 次）是上限而不是配额——耗尽就升级给人，而不是循环进入幻觉。

**指向哪里：** `docs/demo/demo-b.md` · `tmp/demo/bm-noev-001/.../trace.jsonl`。

---

## 故事 4 —— 幻觉产品

我们给智能体一个点名不存在产品（`C999` / 未知 ID）的推荐请求。候选层、推荐层、报告层
各自独立地拒绝了它。最终状态：`primary = 0`、`unverified_products = []`，报告不点名任何产品。

**教训：** Catalog 是显式的信任边界。生成与选择是分离的（`product-candidate-provider`
生成，`product-recommendation` 选择），所以产品无法「自我推荐」。硬不变量
（`catalog_has_primary_product`）加上报告层的 `FABRICATED_PRODUCT` 护栏，让幻觉成为
*结构上的不可能*，而不是一个愿望。

**指向哪里：** `runtime/resources/config/eval.rules.json` · `tests/eval/test_recommendation_catalog_guard.py`。

---

## 故事 5 —— 独立红队

开发者自己的测试通过了。那不等于验收。我跑了一次不信任 README、不信任历史、不信任作者
所写 eval 的独立评审：读代码、注入故障（F1–F6）、变异 artifact、读 trace、把溯源追到
`chunk_id`，并主动 hunting 假通过（`all([])` 空真、被吞的异常、未实现的检查）。

**教训：** 开发者测试回答「我建的是不是我想要的？」独立验收回答「别人凭什么信它？」
红队发现 **0 个假通过**，确认了 `30/30` 回归、`71/71` E2E、`33` 个 benchmark case、
`9/9` golden——但它也逼出了一次诚实的 `PARTIAL E2E` 披露（原始自然语言录入不在已执行
边界内）。那份诚实本身就是交付物。

**指向哪里：** `docs/eval/independent-acceptance-report.md`。
