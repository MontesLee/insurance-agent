# 28.K.28-I-FIX-IMPL · Intent 最小修复实施

Date: 2026-09-29 · Owner 授权 D1-D5（D1 实施 C→B-narrow→A·D2 不扩
intent·D3 指称不猜·D4 B2 缓·D5 六项验收阈值）·
**STATUS: PASS（D5 全达标）**

## 1. Baseline（K.28-I）

Accuracy 90.00% · Behavior 90.45% · MacroF1 0.9025 · P0=0 ·
v1-P1=19（8.64%）· C1 precision 95.35%/recall 97.62%·假延续 4%·
稳定 100% · 电池 865+2。语料 v1 冻结未动（§十一 零 expected 修改）。

**严重度双轨说明（透明）**：v1=K.28-I 原仪器（族失配+锚→P1）；v2=任务
§十 Owner 定义（P1 仅当**错 Agent/工作流路径被执行**；clarify/治理
unknown 落地=安全摩擦=P2）。两轨同源数据、每步同轨对比，单调性双轨
成立。D5「Business-impacting」按 Owner 定义即 v2。

## 2. Fix C — False Continuation Guard（第一步）

- **改动**：`intent-rules.yaml context.plan_continuation.negative_signals:
  [退款,退保,取消,投诉,再解释,再讲一遍,帮我推荐]`（外置）；
  `classifier.py` 规则 4.5 切换判定并入负向命中（4 行）。
- **受影响**：S5-SW-09（退款→非治理澄清✓）·S6-BORDER-12（再解释→
  非治理澄清✓）·S5-SW-03（帮我推荐→落规则链→insurance_qa✓）。
- **C1 回归**：42 正例零变化（词表与正例零重叠·已验证）·recall
  97.62% 不变·假延续 4%→**0%**·15 ack/35 switch 零变化。
- **门**：acc 90.00→91.36 · v1-P1 19→16 · v2-P1 11→8 · 簇单调 ✓。

## 3. Fix B-narrow — Explicit Reference Signals（第二步）

- **改动**：`markers.product_specific += [第一款,第二款,前者,后者,
  第一份,第二份]`（仅 yaml；**上下文锚要求不变**=无保险上下文不点火
  =fail-closed；这个/那个/那这个/它 按 D3 明确不收）。
- **受影响**：S4-ELL-05（第二款呢→product_qa✓）。ELL-07（这个呢）
  保持 unknown ✓（D3 保护实证）；ELL-06/12（后者/第一个，上下文仅
  产品 id 无锚词）保持 unknown=语料期望 ✓。
- **已知边界（记录不修）**：S2-QA-FU-03（那第二款呢，上下文=P001和
  P002 哪个好）不点火——纯产品 id 上下文不携带锚。扩展「产品 id=
  上下文锚」会翻转 ELL-06/12 两个语料正确例（净 -1）→ 拒绝；留
  corpus v1.1 二审裁决。
- **门**：acc 91.36→91.82 · v1-P1 16→15 · 无 QA/Planning 新假阳 ✓。

## 4. Fix A — Question Protection（第三步·核心）

- **改动**（全部外置 yaml `markers.question_protection` + 规则 4/5
  各一小段 classifier 逻辑；plan signals += [怎么配,怎么安排]）：
  - 问句形态：markers [什么,哪个,哪些,为什么,怎么,怎么回事,是否] +
    patterns [A-not-A `([一-鿿]{1,3})不\1`·`需要.{0,8}吗`·
    `应该.{0,8}吗`]。
  - **豁免**（防「规划请求+问号」误归 QA——TRAP-01/02/03 锚定）：
    邻接 `(怎么|如何)(规划|配置|配|买|投保|安排|设计|做)`（含
    实施中发现补入的 **做**：report.py 语料「怎么做保障方案」电池
    捕获）；祈使 `(帮我|给我|请|麻烦).{0,8}(做|出|设计|配置|规划|
    安排|看|评估|分析|检查|梳理)`；建议类 [建议,思路,意见,指南]
    （PLAN-08「想投保，有什么建议」保持 plan）。
  - 规则 4：问句形态命中且无豁免→抑制 plan 落原链。
  - 规则 5（b）：**仅当** 消息含 plan 信号 + 消息自带保险锚 +
    无既有 qa 信号 → question_form 分类 qa（`rule:qa:question_form`）
    ——窄构造：无 plan 名词的模糊锚问句（RV2「一家三口」/K.5 S06
    「什么保险比较好」）保持治理 unknown 路径不抢占（D2）；域外
    问句无锚不自动路由。
- **受影响（8+1 全修）**：TRAP-04（包括什么→qa✓）·TRAP-05（是什么
  →qa✓）·TRAP-06（A-not-A 够不够→qa✓）·TRAP-08（注意什么→qa✓）·
  QA-16（怎么选→qa✓）·MIX-04（买哪个→qa✓）·BORDER-07（需要…吗
  →qa✓）·SW-10（收不收费→无锚→**非治理 unknown**✓=D2 理想解）·
  PLAN-09（怎么配 信号→plan✓）。
- **plan↔qa 结果**：25/25（baseline 20/25）。
- **门**：acc 91.82→95.91 · v1-P1 15→6 · v2-P1 8→**0**。

## 5. Monotonicity（逐阶段·双轨）

| 阶段 | acc | v1-P1 | v2-P1 | c1 | c2 | c3 | c4 | c5 | c6 |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 90.00 | 19 | 11 | 8 | 6 | 2 | 1 | 1 | 1 |
| +Fix C | 91.36 | 16 | 8 | 8 | 6 | **0** | 1 | 1 | **0** |
| +B-narrow | 91.82 | 15 | 8 | 8 | 5 | 0 | 1 | 1 | 0 |
| +Fix A | 95.91 | 6 | **0** | **0** | 5 | 0 | **0** | 1 | 0 |

**无任何簇上升**；v2 business-impacting 11→8→8→0（≤2% 全程满足）。

## 6. Final Metrics（冻结评测器·core 220·vs baseline）

| 指标 | baseline | final | D5 阈值 | 判定 |
|---|---|---|---|---|
| Accuracy | 90.00% | **95.91%** | ≥95% | ✅ |
| Behavior Acc | 90.45% | 96.36% | — | — |
| Macro F1 | 0.9025 | **0.9486** | ≥0.93 | ✅ |
| plan↔qa | 20/25 | **25/25** | ≥95% | ✅ |
| plan↔continuation | 27/27 | 27/27 | ≥95% | ✅ |
| qa↔product | 10/10 | 10/10 | ≥95% | ✅ |
| Business-impacting（v2=Owner 定义） | 5.0% | **0%** | ≤2% | ✅ |
| （v1 仪器参考值） | 8.64% | 2.73% | — | 参考 |
| Stability ×5 | 100% | **100%** | =100% | ✅ |
| P0 | 0 | **0** | =0 | ✅ |
| C1 precision | 95.35% | **100%** | 不降 | ✅ |
| C1 recall | 97.62% | **97.62%** | 不降 | ✅ |
| False continuation | 4% | **0%** | — | ✅ |
| Missed continuation | 2.38% | 2.38%（1 例既有 ack 阈值） | — | 持平 |

分意图 P/R：qa 1.00/0.945 · product_qa 0.929/0.839 · plan
**0.987/1.000**（过射消除）· modify 1.00/0.929 · unknown
0.875/1.000。其余边界：ambiguous 42/42·none 19/19·
continuation↔switch 34/36（2 例=P3 同 agent 标签细微：多少钱/怎么
样 评价词吸概念问——qa↔product 同管线）·modify↔plan 11/12·
context_dependent 40/46。

## 7. Regression

- C1 专项 `test_agent_intent.py` **12/12** ✓（含 RV4 真实两轮一等回归）
- 全电池 `pytest tests/runtime tests/contract` → **865 passed +
  2 skipped** ✓（中途 2 失败=report.py 语料「怎么做保障方案」缺 做
  于邻接表——电池捕获后补入复绿；教训：豁免动词表须覆盖 做）
- 金标语料 224 全量 + must-pass 集（P1+C1 三集+边界+真实+豁免锚）
  终态失败仅 6 例=全部 D3/D4 锁定类（FU-01/02/03·ELL-01/02·
  QACHAIN-06）
- C2 untouched ✓ · 安全九零（评测零生产写入）✓ · LLM candidate
  保持 OFF（进程未设 env）✓

## 8. Remaining P1/P2/P3（不隐藏）

- v1-P1=6（=v2-P2 安全摩擦，全 clarify 落地·零错工作流）：这个类 4
  （D3 裁定保持 unknown）·FU-03（产品 id 上下文无锚·§3）·
  QACHAIN-06（B2 缓·D4）。
- v2-P3=4：qa↔product 标签细微 3（多少钱/怎么样）+modify→plan 1
  （S2-MOD-FU-01「方案是去年做的」——modify 延续缺口·ADR-024 线）。
- missed continuation 1：S4-PEND-02「孩子5岁」3 字落 ack 阈值
  （C1 设计边界·非回归）。

## 9. Taxonomy Debt（Owner 裁定保留）

SW-10（服务元问题→非治理 unknown）·SW-03（pending 推荐→既有规则 qa）
·REC-01..03（推荐类→既有规则 qa·taxonomy_issue 单列）——**均按 D2
维持 fail-closed/既有映射，未强行归类**。

## 10. LLM Candidate

保持 **OFF**（全程未设 INSURANCE_AGENT_INTENT_LLM；K.28-I 实测 8/18
不稳定结论不变——shadow/future track）。

## 11. Production Readiness（对 D5 阈值）

六项全达标（§6 表）+ C1 preserved + C2 untouched + 簇单调下降 +
电池零新失败 → **28.K.28-I-FIX-IMPL: PASS**。
（注：critical boundary 按 K.28-I 任务指定的三大边界计；若 Owner
将 continuation↔switch（94.4%·2 例为 P3 同 agent 细微）也纳入
critical 定义，请明示——该 2 例不涉错 Agent/工作流。）

## 附：改动清单（§十六 Diff 审计）

- `runtime/intent/classifier.py`（3 小段：4.5 负向并入·规则 4 问句
  守卫+豁免·规则 5 question_form 窄接管）
- `config/intent-rules.yaml`（question_protection 块·序数指称·
  负向词表·plan signals +2）
- 新增工具（非生产）：tools/intent_fix_regression.py
- 未动：router/registry/schema/QA/Planning/Grounding/C2/server/
  WeKnora/Gateway/SSE/EventBus/UI/Artifact（mtime 证据在案）；
  tracked-modified 集与会话起始一致（41）。
- 回滚：yaml 三块删除+classifier 还原（无数据迁移）。
