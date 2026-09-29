# 28.K.28-I-FIX · Intent 最小修复设计审计

Date: 2026-09-29 · Mode: **FIX DESIGN AUDIT ONLY**（零生产代码/配置/
schema 修改；仅本设计文档）· Baseline：phase-28k28-intent-production-
readiness-audit.md（corpus v1 224·core 220·865+2 回归基线）

## 1. Audit Baseline（复核确认）

Accuracy 90.00% · Behavior 90.45% · MacroF1 0.9025 · P0=0 · P1=19
（8.64% 错族）· P2=1 · P3=3 · 确定性稳定性 100%（220×5）· C1
precision 95.35%/recall 97.62% · candidate OFF（8/18 stable）·
ROUTER_ERROR=0。证据：tmp/obs/k28i_{results,p1,failures}.*（本轮逐条
复核，无重算偏差）。

## 2. P1 Failure Matrix（19 例逐条·非摘要）

| Cluster | n | Case（expected→actual） | 消息原文（尾轮） | 下游错配 | 根因 |
|---|---|---|---|---|---|
| ①plan 名词压问句 | 8 | TRAP-04 qa→plan | 家庭保障规划一般包括什么？ | qa 证据管线→规划 8 阶段全管线 | MISSING SIGNAL（什么 不在 definition markers）+RULE PRIORITY |
| | | TRAP-05 qa→plan | 保险配置的一般原则是什么？ | 同上 | RULE PRIORITY（是什么 命中规则 5 但规则 4 先跑） |
| | | TRAP-06 qa→plan | 我的保障够不够？ | 同上 | MISSING SIGNAL（A-not-A 句式无标记） |
| | | TRAP-08 qa→plan | 投保前需要注意什么？ | 同上 | MISSING SIGNAL（什么）+投保 名动歧义 |
| | | QA-16 qa→plan | …到底该怎么选，…预算也不多… | 同上 | RULE PRIORITY（背景词 预算 命中 plan；怎么选 无标记） |
| | | MIX-04 qa→plan | 先别规划了，直接告诉我重疾险买哪个 | 同上 | RULE PRIORITY+否定缺失（先别） |
| | | BORDER-07 qa→plan | 我已经有一份保险了，还需要你们的规划吗 | 同上 | RULE PRIORITY（需要…吗 跨词未匹配；规则 4 无问句守卫） |
| | | SW-10 unknown→plan | 你们这个规划收不收费？ | unknown 澄清→规划全管线 | RULE PRIORITY+TAXONOMY AMBIGUITY（服务元问题） |
| ②省略指示词 | 6 | FU-01/ELL-01 pq→unknown | 那这个呢？ | product 证据管线→clarify | RULE GAP（这个/那这个 不在 product_specific 表） |
| | | FU-02/ELL-02 pq→unknown | 这个需要买吗？ | 同上 | 同上 |
| | | FU-03/ELL-05 pq→unknown | 那第二款呢 / 第二款呢 | 同上 | RULE GAP（第二款 序数指称不在表） |
| ③C1 假延续 | 2 | SW-09 unknown→plan(auto) | 不买了不买了，我想退款 | unknown 澄清→规划延续重跑 | CONTINUATION_GAP（服务祈使句无切换标记） |
| | | BORDER-12 unknown→plan(auto) | 上次说的那个再解释一下 | 同上 | 同上 |
| ④口语规划漏 | 1 | PLAN-09 plan→governed-unknown | 家里老人60多了，想给他们配点保险，怎么配？ | 规划→治理澄清（安全但漏） | RULE GAP（配点/怎么配 不匹配 配置/怎么买 子串） |
| ⑤上下文省略 | 1 | QACHAIN-06 qa→ungoverned-unknown | 一般多久到账（上下文=理赔） | qa→**非治理**澄清 | CONTEXT MISSING（rule 5 无上下文继承；消息无锚） |
| ⑥pending 推荐 | 1 | SW-03 qa→plan(auto) | 先帮我推荐一款重疾险呗（pending 中） | qa→规划延续 | TAXONOMY AMBIGUITY（推荐无 intent；祈使句非答问） |

（taxonomy_issue 另 3 例 REC-01/02/03 单列不计。）

## 3. Cluster 1 根因（§三 8 问逐答）

1. **问号导致？** 部分否——8 例中 4 例有 ？，但规则 4 对问号零感知
   （问号仅在 4.5 continuation 里作切换信号）；裸 ？ 不是充分修复
   面（NP-05「还有别的方案吗」带问号且应为 plan——裸问号守卫会
   误伤它）。
2. **疑问词导致？** 主因之一——什么/怎么选/哪个/A-not-A（够不够/
   收不收费/是不是）四类问句信号在 markers 中大面积缺席。
3. **「什么/怎么/为什么/区别/是否/吗/呢」类？** 是——但必须区分：
   定义类（是什么/包括什么/注意什么）可直接护；怎么+规划动词
   （怎么规划/怎么配置/怎么买）**必须豁免**（TRAP-01/02、PLAN-04
   现为正确 plan）；吗/呢 裸用不可护（NP-05 误伤面）。
4. **product noun rule 优先级过高？** 否——product 分支无涉；是
   **plan 信号（名词性子串）优先级高于问句语义**。
5. **planning action word 缺失？** 正是——规划/配置/保障/投保/预算
   作为子串无词性/角色检测：TRAP-05「配置的一般原则」配置=话题
   名词；QA-16「预算也不多」预算=背景事实；TRAP-08「投保前」
   投保=时间状语。缺「信号的角色判定」。
6. **「用户背景+问题」误判？** 是——QA-16（二胎/预算背景+怎么选
   问题）与 BORDER-07（已有一份保险+需要规划吗）同型：背景含
   plan 名词→吞问句。
7. **deterministic 可修？** 7/8 可（问句信号+邻接豁免+祈使豁免，
   见 Fix A）；SW-10（服务元问题）语义理想解=unknown，问句保护只
   能将其送 qa（有据拒答）——**部分修复**（消除错管线，标签仍非
   理想）。
8. **天然 taxonomy ambiguity？** 2 例——SW-10（服务元问题不属任何
   intent）；MIX-04 的否定（先别规划）属可修信号但「否定后紧接
   产品挑选问」的正确落点（qa）与推荐 taxonomy 灰区相邻。

## 4. Cluster 2 根因（§四）

六例真实身份判定：FU-01/02、ELL-01/02（这个/那这个/这个需要买吗）
= **指称前件的类型不可确定性判定**——ELL-07 对照例证明：同样「这个
呢」在概念讨论上下文（免责条款）中指概念非产品。序数指称（第二款/
后者/第一款）在枚举购物上下文（P001/P002 哪个好）中**强指向产品**。
现有可用上下文：conversation_context（8 条·仅锚继承给 product 分支）
+pending_clarification；active case=恒 None（ADR-024 阻塞·**本设计不
引入 case lifecycle**）。
结论：序数指称=deterministic 可修（B-narrow）；这个/那这个=**不最小
可修**（需前件类型判定=ADR-024/candidate 线·Owner）——修了反而制造
ELL-07 类新错误（概念指称误入 product 管线）。

## 5. Cluster 3 根因（§五·C1 已 SEALED·最谨慎）

1. 为何识别为 continuation：pending=True 且消息无任何切换信号
   （退款/再解释不含问号/定义/评价/plan 动作/modify 动作/特定产品
   指称）→落入「无信号=答问」区间。
2. continuation rule 命中：规则 4.5 的 else 分支（plan:continuation
   理由码，非 ack 路径——两例均 >6 字）。
3. 原始消息确有 pending planning：是（corpus prev=waiting_plan）。
4. C1 switch signals 是否不足：**轻微不足**——服务性祈使动词
   （退款/退保/取消/再解释/再讲一遍）不在切换表，但这与 C1 设计
   前提（裸产品名词=答问内容）不冲突：负向护栏是**加法子表**，
   不改既有切换语义。
5. 可否极少负向信号解决：**可以**——见 Fix C；验证：42 个 C1
   答问正例与护栏词表**零重叠**（本轮逐一核对）。
6. 是否伤 C1 正例：结构上不可能伤——护栏仅在 4.5 内部分流到
   「继续走原规则链」，42 正例不含护栏词→行为逐字节不变。

### C1 Regression Risk Matrix

| 集合 | n | Fix C 影响 |
|---|---|---|
| C1 positive（答问） | 42 | 零重叠→**零变化**（recall 97.62% 保持） |
| switch | 35 | 2 例假延续转正（SW-09/BORDER-12 属本簇）；其余 33 不含护栏词→零变化 |
| ack | 15 | 护栏在 ack 判定**之后**才需检查？——设计置于 4.5 开关判定后、ack 判定前：ack 词（好的/是的）与护栏词无交集→零变化 |
| false continuation | 2 | →0（precision 95.35%→~100%） |

## 6. 其余三 P1（§六）

- **口语规划漏（PLAN-09）**：存在自然 planning 信号缺口——怎么配/
  配点/配一份/怎么安排/理一份（本轮语料核查：PLAN-09 唯一命中此
  型）。Fix A 的邻接豁免表顺带承接（怎么+配 系）+规则 4 信号表
  增补。deterministic 可修。
- **上下文省略（QACHAIN-06）**：仅凭 recent conversation（T1 理赔）
  语义上可判 qa，但**确定性上下文继承到 rule 5 是新机制类**（现
  仅 product 分支继承），泛化有误伤面（概念漂移）。最小安全解=
  Fix B2：椭圆问句（多久/多少/几天+短消息）+上下文保险锚→
  **governed unknown**（治理澄清，不猜 qa）——修复的是「非治理
  逃逸」而非标签。active case 判定=architecture debt（ADR-024 线，
  本设计不引入）。
- **pending 推荐（SW-03）**：判定=**continuation boundary 与
  recommendation taxonomy 的复合**——祈使句「先帮我推荐」非答问
  （continuation 侧缺陷），但即使识别为切换，落点也无推荐 intent
  （taxonomy 侧缺口）。**不为此单例改 recommendation 路径**；随
  Fix C 的祈使护栏自然缓解（推荐/帮我推荐 入负向表→SW-03 落
  unknown 澄清=安全），taxonomy 裁决留 Owner。

## 7. Proposed Minimal Fixes（≤3·全部 intent 层·rules 优先）

### Fix A · Question Protection（修簇①+④·8 例中 7 全修+1 部分）

- 位置：规则 4（plan）前置守卫（classifier 逻辑 + rules 外置表）。
- 触发：消息含**问句信号**——定义/求解类（是什么/什么/哪个/哪些/
  为什么/区别/包括什么/注意什么）·A-not-A（X不X 正则）·跨词需要/
  应该/能不能（+0-8 字+吗）——且**不满足豁免**。
- 豁免（防「规划请求+问号」误归 QA）：①邻接豁免：怎么/如何+配
  系动词（配置/配/买/投保/安排）→plan 保持（TRAP-01/02、PLAN-04、
  PLAN-09 修复后同获）；②祈使豁免：帮我/请/麻烦+看/评估/分析/
  检查/梳理 开头→plan 保持（TRAP-03 是不是合理）。
- 命中守卫→跳过规则 4 落规则 5（qa 链）；无 qa 信号→unknown
  （带锚=治理澄清，fail-closed）。
- 修复预期：TRAP-04/05/06/08、QA-16、MIX-04→qa ✓；BORDER-07
  （需要…吗 模式）→qa ✓；SW-10→qa（部分：消除规划管线，理想
  unknown 留 taxonomy 线）；PLAN-09 经豁免表+信号增补→plan ✓。

### Fix B · Context/Demonstrative Signals（B-narrow 修簇②之 3-4 例）

- 仅扩 **序数/枚举指称**：第二款/第一款/后者/前者（+上下文锚
  继承既有要求不变——无保险上下文→不点火→unknown，fail-closed
  保持）。
- 修复预期：FU-03/ELL-05（那第二款呢/第二款呢）→product_qa ✓；
  ELL-06（后者呢）→product_qa ✓；ELL-12（第一个呢，corpus
  expected=unknown 系「记录缺口」型期望，语义本应 product_qa——
  列 v1.1 erratum 候选）→product_qa（语义正确）。
- **明确不收**：这个/那个/那这个（ELL-07 反例：概念指称误入
  product 管线）——保持 unknown 澄清，记 architecture gap。
- B2（可选子项）：椭圆问句+上下文锚→governed unknown（QACHAIN-06
  非治理逃逸→治理澄清）。

### Fix C · False Continuation Guard（修簇③+顺带⑥·2+1 例）

- 位置：规则 4.5 内部、切换判定后：负向服务/祈使词表 {退款·退保·
  取消·投诉·再解释·再讲一遍·帮我推荐·推荐一款}→不延续，落原
  规则链（→unknown 澄清·SW-09/BORDER-12 无锚=非治理、SW-03
  重疾险 qa 信号→qa）。
- 词表极小且与 42 正例零重叠（已验证）；不改 C1 任何既有语义
  （设计只加 else 内部分流）。

## 8. Alternative Designs Rejected（§八 禁令核对）

新 Router/Agent/Case Store/Intent Service/LLM authority/embedding/
整单重分类/Router authority/QA/Planning/Grounding/C2/evidence gate
——**均未采用亦不需要**；被否决的设计备选：①裸问号守卫（误伤
NP-05「方案吗」）②这个/那个 入 demonstrative 表（ELL-07 概念指称
反例）③rule 5 通用上下文继承（概念漂移误伤面未量化）④否定解析器
（先别/不买了——超出最小面，MIX-04 由 哪个 问句信号已覆盖）
⑤把 SW-10 送 unknown 的服务问题分类器（新 taxonomy 面=Owner）。

## 9. C1 Regression Risk（§五矩阵+实施级）

**LOW**：C 仅在 4.5 内加负向分流；42/15/33 集合零重叠已验证；
A/B 不触 4.5（A 守卫在规则 4 主链、B 在规则 1 markers）。残余
风险=词表意外子串命中（如 取消 出现在答问里「取消社保」——
语料 42 例无此形态；实施时负向表逐词过 K28I_FIX_REGRESSION）。

## 10. C2 Compatibility

**NONE/无涉**：A/B/C 全在 runtime/intent+config/intent-rules.yaml；
qa_agent/grounding/gate/loop 零触碰。次级效应（如实告知）：簇①
修复后概念问句改道 QA 切片→C2 资格下限+引用门流量上升——G-1
语料缺口（28.C-3）的拒答会更常见（正确 fail-closed，但 Owner
应预期「修好意图层后知识线拒答率上升」）。

## 11. Test Corpus（K28I_FIX_REGRESSION·§十）

Must-pass（冻结 corpus 子集+锚定例）：19 P1 全部 + C1 42 正例 +
35 切换 + 15 ack + plan↔qa 25 + 真实 12+ + 豁免锚定例
（TRAP-01/02/03·PLAN-04·NP-05·SW-13·SW-20·SW-15「明天再说」
不得被 再讲一 误伤）≈ **130 cases must-pass**；全量 224 复评
+ 865+2 电池（C1 12 节·C2 8 节在内）。不允许只跑既有 unit。

## 12. Expected Metric Impact（设计估计·非实测）

| 指标 | 现在 | A+B+C 后（估计） | 说明 |
|---|---|---|---|
| Accuracy | 90.00% | ~93-94% | 净修 ~12-13/220 |
| plan↔qa 边界 | 20/25 | ~24-25/25 | 簇①主体消除 |
| Business-impacting | 8.64%（19） | ~2.7-3.2%（6-7） | 残留=这个类 4+QACHAIN-06 降级+SW-03/10 |
| C1 precision/recall | 95.35%/97.62% | ~100%/97.62% | recall 不动（护栏零重叠） |
| false continuation | 4% | 0% | 2 例转正 |
| 稳定性 | 100% | 100% | 纯确定性加法 |

约束（§十一）：实施后全指标重算；**Business-impacting 上升的
任何「总体提升」不算改进**；must-pass 130 例零回归为门槛。

## 13. Owner Decisions Required

1. 三修复（A/B-narrow/C[+B2 可选]）实施授权——实现属
   **K.28-I-FIX-IMPL 独立阶段**（动 classifier.py+intent-rules.yaml
   =生产代码，本审计未动一行）。
2. SW-10（服务元问题）与 recommendation taxonomy（SW-03/REC-01..03）
   是否立项 taxonomy 裁决（ADR-019 词表或维持 fail-closed）。
3. 这个/那这个 类前件指称：维持 unknown 澄清（建议）vs ADR-024/
   candidate 线授权。
4. corpus v1.1：ELL-12 expected 修正 + 第二评审人复核授权。
5. 验收阈值 5 项（沿 K.28-I 待裁）。

## 14. Recommended Implementation Order

**C（最低风险·C1 内部·2+1 例）→ B-narrow（孤立 marker 增补·3-4 例
[+B2 可选]）→ A（守卫+豁免矩阵·7-8 例·复杂度最高）**——各自独立
可上线可回滚（rules/代码小步）；每步后跑 K28I_FIX_REGRESSION 130
+全量 224 复评+电池，Business-impacting 单调下降方可进下一步。

---

## 最终输出（§十四）

```
28.K.28-I-FIX DESIGN AUDIT: COMPLETE

P1:
- total: 19 (+3 taxonomy-issue 单列)
- plan/qa: 8 (7 deterministic-fixable via Fix A; 1 partial SW-10)
- context: 7 (3-4 ordinal-demonstrative fixable via Fix B-narrow;
  4 这个-class NOT minimally fixable — documented gap; 1 QACHAIN-06
  partial via B2 governed-unknown)
- continuation: 2 (both fixable via Fix C negative guard)
- other: 2 (PLAN-09 via Fix A carve-out+signals; SW-03 taxonomy
  ambiguity — mitigated not fixed)

Root Causes:
- RULE_PRIORITY: plan-noun substrings (规划/配置/保障/投保/预算)
  fire rule 4 before question semantics (4 cases)
- MISSING SIGNAL: question forms absent from markers — 什么-
  questions, A-not-A (X不X), 需要…吗 across-word (4 cases)
- RULE_GAP: ordinal demonstratives (第二款/后者) outside
  product_specific markers (3-4 cases); colloquial plan verbs
  (怎么配/配点) outside plan signals (1)
- CONTINUATION_GAP: service imperatives (退款/再解释) inside
  C1's "no-signal = answer" span (2)
- TAXONOMY AMBIGUITY: recommendation & service-meta have no
  intent (SW-03, SW-10 partial; +REC×3)

Proposed Minimal Fixes:
1. Fix A Question Protection — question-signal guard before rule 4
   with adjacency (怎么+配置/规划/买/投保/安排) and imperative
   (帮我/请+看/评估) carve-outs; rules-externalized signal table
2. Fix B-narrow Context/Demonstrative — add ordinal demonstratives
   (第二款/第一款/后者/前者) to product_specific (context-anchor
   requirement unchanged = fail-closed); 这个/那这个 explicitly
   NOT added (ELL-07 concept-reference counterexample);
   optional B2: elliptical-question + context-anchor → governed
   unknown (not auto-qa)
3. Fix C False Continuation Guard — tiny negative list
   (退款/退保/取消/投诉/再解释/再讲一遍/帮我推荐) inside rule 4.5
   post-switch-check; verified ZERO overlap with C1's 42 positives

C1 Risk: LOW (guard is additive inside 4.5; 42/35/15 sets verified
   zero-overlap; recall unchanged by construction)
C2 Risk: NONE (intent layer only; secondary effect: more concept
   questions reach QA slice → C2 floor/citation-gate refusals
   become more frequent — correct fail-closed, Owner should expect
   it)

Production Behavior Impact: NONE (design audit only — zero code/
   config/schema touched this phase)

Owner Decisions Required:
1. Authorize K.28-I-FIX-IMPL (C → B-narrow [+B2] → A order), a
   separate implementation phase touching classifier.py +
   intent-rules.yaml
2. Taxonomy rulings: service-meta (SW-10) & recommendation
   (SW-03/REC) — new vocabulary vs keep fail-closed
3. 这个/那这个 antecedent class: keep unknown-clarify (recommended)
   vs ADR-024/candidate line
4. Corpus v1.1 (ELL-12 erratum + second-rater review)
5. The 5 acceptance thresholds still pending from K.28-I

Implementation: NOT STARTED

STATUS: OWNER DECISION REQUIRED

STOP
```
