# 28.K.28-I · Intent Production Readiness Audit

Date: 2026-09-29 · Mode: **AUDIT ONLY**（零生产代码/配置/schema/测试修改
——新增件仅 evaluation corpus + evaluator + tmp/obs 证据 + 本报告）·
Status: **THRESHOLD_UNDECIDED**（§17：项目无冻结 intent 验收阈值——
输出完整 metrics，不自行宣布 PASS/FAIL）

## 1. Executive Summary

- 冻结金标语料 **224 cases**（v1·6 suites·12+ 真实历史源·30+ 硬负例）
  对生产 classifier+router 全量离线评测（进程内·N=5·零生产台账污染）。
- **核心指标（taxonomy-issue 4 例除外·n=220）**：Accuracy **90.00%** ·
  Behavior Accuracy **90.45%** · Macro F1 **0.9025** ·
  Business-impacting（错 Agent 族）**19/220 = 8.64%** ·
  **P0=0**（fail-closed 结构保证被证明）·P1=19·P2=1·P3=3。
- **确定性稳定性 100%**（220×5 零漂移）；**LLM candidate（当前生产
  OFF）实测不稳定 8/18**，且会对真实模糊问法（RV2「一家三口」类）
  漂移出 plan 自动路由——不建议开启（Owner 决策）。
- **C1 continuation 复评（§20）**：precision 95.35% · recall 97.62% ·
  false continuation 4%（2 例：退款请求/再解释请求被当答问）·
  missed 2.38%（1 例：3 字答问落 ack 阈值）——C1 净收益成立、
  假阳性有界且已定性。
- 19 个 P1 聚为 6 簇根因（§14）：最大=**plan 名词压问句**（规划/
  保障/配置/投保/预算出现在疑问句中→规划全管线，8 例）与
  **省略指示词缺口**（这个/那这个/第二款/后者 不在 marker 表→
  clarify，6 例）。
- 回归：backend 电池 **865 passed + 2 skipped**（与 C2 基线一致·
  C1 12 节/K.26/K.27-S1/C2/QA/Planning/Router/Grounding 全含）零回归。

## 2. Current Intent Taxonomy（代码盘点·非文档推断）

词汇表 5（schema enum 冻结）·规则序 1-7（intent-rules.yaml 头注与
classifier.py 逐行核对）·C1 continuation=规则 4.5（pending+无切换信号；
切换=问号/定义/评价/特定产品/plan 动作/modify 动作；裸产品名词≠切换；
ack≤6 字 fail-closed）。

| Intent | 语义 | 规则信号（实测） | 下游 Agent | Router | 澄清行为 | 兜底 |
|---|---|---|---|---|---|---|
| insurance_qa | 保险概念/知识/区别/必要性问句 | definition markers（是什么/区别/有必要吗/需要吗/应该买吗）+ qa 名词（重疾险/医疗险/等待期/社保/…） | insurance-qa-agent | registry_lookup | 无 | — |
| product_qa | 特定产品事实/评价 | 特定指称（这款/这个产品/那款/P0xx/目录名·需锚）+ 评价词（怎么样/值得买/多少钱·需锚·非定义） | insurance-qa-agent（product-qa 切片·slices 模式 DEFAULT OFF） | registry_lookup | 无 | — |
| insurance_plan | 规划/配置请求·C1 延续 | plan 动作信号（规划/配置/方案/买保险/怎么买/投保/预算/保障）；4.5 延续（pending+无切换） | insurance-planning-agent | registry_lookup | ack/歧义→clarify | — |
| modify_existing_plan | 修改既有方案 | modify 动作（改成/调整/提高/降低/换成…） | insurance-planning-agent | registry_lookup | **无 active_case 必 clarify**（M1·schema 结构强制） | — |
| unknown_insurance_intent | 兜底 fail-closed | 无信号；含保险锚→domain:insurance_anchor→K.7 治理 QA 缝 | conversation-agent（治理缝→qa 切片） | fallback+clarify | 恒 clarify | 永不猜测 |

关键结构事实：active_case_id 生产恒 None（ADR-024 阻塞·server:673）；
LLM candidate 仅在规则全空时咨询（advisory·schema 门·HD-1 高危
0.75 floor·decision_source 无 llm 值=Router 契约结构性排除）。

## 3. Evaluation Corpus（tests/golden/intent-golden-corpus.v1.json·v1 冻结）

- **总 224**：S1 单轮 65 · S2 两轮 53 · S3 三轮+ 30 · S4 上下文依赖
  （A/B 双跑）30 · S5 topic-switch 20 · S6 歧义 26。
- 真实历史源 **12+**：RV4 T1/T2 逐字（永久回归）、run_50389328
  （K.12 首真人）、run_24562be1（K.18）、run_a7d9ccb9（RV2 一家三口）、
  K.5 S05/S06/S07/S09 形态、C2-LIVE T1/等待期阳性对照。
- 硬负例 ≥30（§七 全类：产品名词/问号/推荐动词/规划名词/延续名词/
  混合意图/topic-switch/超短/指示代词陷阱）。
- taxonomy_issue 4（推荐类·无冻结 intent·单独报告不计 headline）。
- expected 推导七条 D-规则随语料冻结发布；首跑后 **2 处受审计留痕
  修正**（R1 P003 问句=product_qa 与 S1-PQ-01 一致性；R2 evaluative
  不继承锚=28.A-2 明文设计）——均引用冻结设计文本非迁就输出。
- 已知 erratum（不改 v1·v1.1 修）：S4-ANCH-02 expected_alone 应为
  product_qa（消息自带 产品 锚）→ alone 22/25 实为 23/25。

## 4-6. Overall / Per-intent / Confusion（core n=220）

| Intent | P | R | F1 | support |
|---|---|---|---|---|
| insurance_qa | 1.000 | 0.800 | 0.889 | 55 |
| product_qa | 0.926 | 0.806 | 0.862 | 31 |
| insurance_plan | 0.865 | 0.987 | 0.922 | 78 |
| modify_existing_plan | 1.000 | 0.929 | 0.963 | 14 |
| unknown_insurance_intent | 0.830 | 0.929 | 0.876 | 42 |

Confusion（expected→predicted: n）：

```
              QA   PQ   PLAN  MOD   UNK
QA            44    2     8    0     1
PQ             0   25     0    0     6
PLAN           0    0    77    0     1
MOD            0    0     1   13     0
UNK            0    0     3    0    39
```

热点：**qa→plan 8**（规划名词压问句簇）·**pq→unknown 6**（省略指示词
缺口）·unk→plan 3（假延续）·qa→pq 2（怎么样/多少钱 评价词吸走概念问）。

## 7. Boundary Accuracy

plan↔continuation **27/27** · qa↔product_qa 10/10 · qa↔recommendation
3/3 · modify↔plan 11/12 · plan↔qa **20/25（80%·最低）** ·
continuation↔topic_switch 31/36（86.1%）· context_dependent 39/46
（84.8%）· ambiguous 39/42。Suite：S1 55/61 · S2 48/53 · S3 29/30 ·
S4 27/30 · S5 16/20 · S6 23/26。

## 8. Continuation Metrics（§20·C1 复评）

pending 语料 98（答问 42·切换 35·ack 15）：**precision 95.35%** ·
**recall 97.62%** · **false continuation 4%**（S5-SW-09「我想退款」/
S6-BORDER-12「再解释一下」——无切换标记的祈使句被当答问）·
**missed 2.38%**（S4-PEND-02「孩子5岁」3 字落 ack 阈值→clarify）。
落地路径：41 例答问中 33 经 plan:continuation 理由、8 经消息内 plan
信号同达 plan（结果等价·理由路径并存记录）。
**结论：C1 显著提升延续准确性且假阳性有界（2/50 非答问 pending）；
未扩大至切换类（35 切换仅 2 假阳）。**

## 9. Stability

- 确定性（生产现行）：220×5 重复 **100% 稳定·零漂移**（含全部
  hard/ambiguous——规则层无采样）。
- LLM candidate（OFF·§11B 实测）：18 rule-miss 例×3 → **稳定仅 8/18**；
  漂移实例含 RV2 真实问法「一家三口需要哪些保险」{plan,unknown}——
  高置信 plan 提案会**自动路由进规划全管线**（行为级改变）。

## 10. Context Ablation（§13·S4 全 30 例）

full 27/30（90%）· alone 22/25（88%·erratum 后 23/25）。关键三态：

| Case | alone | +ctx | +ctx+pending | 证明 |
|---|---|---|---|---|
| S4-PEND-01（RV4 T2 逐字） | **qa**（原始事故复现） | **qa**（会话上下文不解决） | **plan 延续** | 决定性上下文=server 派生的 pending 信号（C1），非原始会话文本 |
| S4-PEND-05/09 | unknown(+锚治理) | unknown | plan 延续 | 同上 |
| S4-ANCH-01（天气） | ungoverned | ungoverned | ungoverned | 评价词不继承锚（28.A-2 设计保持） |

## 11. LLM Candidate vs Deterministic（§11·live glm·进程内 env 门控）

- 触发面：仅规则全空（unknown 类）；18 例×3 实弹。
- **治理正确性 PASS**：候选提案经 schema/禁键门→确定性 resolver 终裁；
  Router decision_source 全程仅 {fallback, registry_lookup}（llm 无值=
  契约排除·实测零例外）；候选 error/超时 100% fail-closed 降级
  （llm:candidate_error→unknown）；**HD-1 floor 实弹触发**（「好的」
  无 pending→plan 提案 conf 0.7/0.6 <0.75→clarify 而非自动路由）。
- **正确性/稳定性 NOT READY**：final-match 11/18；稳定 8/18；修复 2
  （多久到账→qa·怎么配→plan）同时破坏 3（语义可辩但改变 K.5/K.27
  真实案例的治理路径）。
- **建议维持 OFF**（生产现状一致）；启用=Owner 决策（需先解决漂移
  与高置信假阳对模糊问道的自动路由风险）。

## 12. Production-like Shadow

进程内全量 classify 记录（220×5+候选 54 次）→tmp/obs/k28i_results.json
（零生产 shadow.jsonl 写入·零 server 参与）。生产 shadow.jsonl 交叉
核对：RV4 T2 真实记录 reason_codes 与本评测逐字一致
（rule:qa:重疾险/医疗险）——离线评测与生产行为同构。

## 13. P0/P1 Inventory（19 P1·全量字段在 k28i_results.json）

六簇（§14 同）：①plan 名词压问句 8（TRAP-04/05/06/08·QA-16·
MIX-04·BORDER-07·SW-10）②省略指示词 6（FU-01/02/03·ELL-01/02/05）
③C1 假延续 2（SW-09 退款·BORDER-12 再解释）④口语规划漏 1（PLAN-09
「怎么配/配点保险」→治理 unknown）⑤上下文省略 QA 1（QACHAIN-06
「一般多久到账」）⑥pending 内推荐 1（SW-03）。taxonomy_issue 另 3
（推荐→qa 路由·单列）。

## 14. Root Cause Classification

| 簇 | 根因类 | 机制 |
|---|---|---|
| ①plan 名词压问句（8） | RULE_PRIORITY | 子串信号无词性/否定检测：「…规划一般包括什么」「我的保障够不够」「先**别**规划了」「投保前注意什么」中的规划/保障/配置/投保/预算先于问句语义命中规则 4 |
| ②省略指示词（6） | RULE_GAP | markers.product_specific 仅 这款/这个产品/这份产品/那款/那个产品——「这个/那这个/第二款/后者/第一个」不在表→上下文锚继承无从附着→unknown |
| ③C1 假延续（2） | CONTINUATION_GAP | 无切换标记的祈使句（退款/再解释）落在「无信号=答问」区间 |
| ④口语规划漏（1） | RULE_GAP | 「配点保险/怎么配」不匹配 配置/怎么买 子串 |
| ⑤⑥ | CONTEXT_MISSING / 设计灰区 | 概念追问无自身信号；pending 内推荐类祈使句 |

无 SCHEMA_ERROR / ROUTER_ERROR / LLM_CANDIDATE_ERROR（生产路径）。

## 15. Business Impact（§15/§16）

- **ROUTER_ERROR=0**：全部 224 例 Router 行为严格跟随 IntentResult
  （lookup/clarify/unknown fallback 零偏差）——错误全部在意图层，
  修复轨道=意图层（K.28-I-FIX），非 Router。
- 19 错族中：**13 例错进规划全管线**（概念/元问题触发完整 8 阶段
  LLM 工作流——成本+错工作流+可能自答非证据类建议）；6 例错落
  clarify（安全降级·UX 摩擦）；2 例假延续重复规划。无证据链污染类
  （P0=0：消息级保险锚结构上强制治理路径）。
- §16 纪律：所有判定基于 intent/router 契约，未引用下游「碰巧合理」
  输出。

## 16. Regression

`pytest tests/runtime tests/contract` → **865 passed + 2 skipped**
（406s；与 C2 后基线完全一致）：C1（test_agent_intent 12 节含 RV4
两轮一等回归）/C2（k27rv4c2 8 节）/K.26 流式/K.27-S1 单写/QA/
Planning/Router/Grounding 全绿。生产文件 mtime 未动
（classifier/server/rules=09-28 22:2x）。

## 17. Known Limitations

1. 无冻结 intent 验收阈值（本报告=观测值；THRESHOLD_UNDECIDED）。
2. 单评审人语料（expected 由 D-规则推导并随语料发布，建议 Owner
   或第二评审人复核 224 例）。
3. COMPLETED 后补充声明落 qa（RV4 原始形态·设计内·ADR-024 线）。
4. CJK 子串匹配无词边界（根因①的机制面）。
5. T1 ask-vs-proceed 模型方差非意图层问题（C2-LIVE 已记 O-1）。
6. product_qa 切片 slices 模式 DEFAULT OFF（full authority 下行为
   依赖部署配置）。
7. erratum S4-ANCH-02（§3）。

## 18. Owner Decisions Required

1. **验收阈值**：overall accuracy / macro F1 / 关键边界（plan↔qa）/ 
   business-impacting 上限 / stability 下限（建议就观测分布裁决，
   如 P1 簇①是否属可接受 UX 损失 vs 必修）。
2. **K.28-I-FIX 立项与否**（与本审计严格分阶段）：候选最小修复=
   ①问句保护（定义/问号语境下 plan 名词降权）②指示词表扩展
   （这个/那个/第二/后 者+上下文锚）③假延续护栏（祈使动词表）；
   均为 intent 层（rules/classifier），不动 Router/Agents。
3. **LLM candidate 处置**：维持 OFF（建议）或立项漂移治理。
4. 语料 v1 冻结确认 + 第二评审人复核；v1.1 erratum。

## 最终状态（§二十四）

**THRESHOLD_UNDECIDED** — 完整 metrics+失败分析如上；存在 19 例
P1（8.64% 错 Agent 族·13 例错进规划工作流），是否构成 NOT_READY
由 Owner 阈值裁决；P0=0（无 unsafe evidence path）。**STOP：不进入
修复/Phase 2；如需修复另立 28.K.28-I-FIX。**

---

## 附：可复现命令

```
PYTHONIOENCODING=utf-8 python tools/intent_production_eval.py   # 主评测
PYTHONIOENCODING=utf-8 python tmp/probe_k28i_llm_candidate.py  # 候选实测
# 证据：tmp/obs/k28i_results.json · k28i_llm_candidate.json · k28i_failures.txt
```
