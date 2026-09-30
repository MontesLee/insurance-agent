# Pre-UAT Intent Semantic Arbitration Benchmark（G-05）

Date: 2026-09-30 · Mode: **BENCHMARK/EVIDENCE ONLY**（LLM=candidate
only·进程内 env·生产零改动）· **PRE-UAT INTENT SEMANTIC ARBITRATION:
COMPLETE** · 场景判定：**Scenario C（无实证优势）+ 局部 Scenario B**

## 1. Frozen Baseline

HEAD 24082d5（Intent SEALED @ e306118：golden 220 acc **95.91%**·
macroF1 **0.9486**）·`INSURANCE_AGENT_INTENT_LLM` env=**未设（OFF）**
（hd2.env/.env 均 0 命中）·Deterministic Resolver=AUTHORITY·
LLM=CANDIDATE ONLY·Router authority unchanged·生产行为零变化。

## 2. Dataset（tests/golden/intent-arbitration-benchmark.v1.json·v1 冻结）

**88 例** = A 金标边界子集 40 + C/E 设计边界 38 + D OBS-1 逐字 10。
边界分布：plan↔qa 36·cont↔new 24·clarify↔proceed 15·ins↔non 5·
switch 3·pq↔plan 3·general 2。**GOLD_UNCERTAIN 9 例**（taxonomy 张力
→OWNER_DECISION_REQUIRED·不计入准确率分母——如实排除非隐藏）。

## 3. Human Gold 方法论

依**冻结 taxonomy**（ADR-019 + FIX 裁决 D2/D3）推导，非模型意见；
无法唯一确定者标 GOLD_UNCERTAIN（9 例：如「按照我家的情况配置多少」
=quantity-question 语义 vs 配置 plan-action 子串的张力）。

## 4-6. 三路结果（真实 glm·88 cases·~5 min）

| 指标 | Deterministic | LLM Candidate |
|---|---|---|
| Overall（79 scorable） | **86.1%** | 63.3%（计失败为错）/**83.3%**（仅 60 应答内） |
| 有效应答率 | 100% | **68/88（77%）**——21 次 raise（超时/传输） |
| **Business wrong-family** | **9** | **9**（持平·但 LLM 含 QA→PLAN 3 例高危：OBS1-03/07/10） |

边界分解（det vs llm）：

| 边界 | n | Det | LLM | 分歧 |
|---|---|---|---|---|
| plan↔qa | 31 | **0.94** | 0.81 | 8 |
| cont↔new | 24 | **0.75** | 0.46 | 14 |
| clarify↔proceed | 15 | **0.87** | 0.40 | 9 |
| topic_switch | 3 | 0.67 | **1.00** | 1 |
| ins↔non / pq↔plan | 5 | 1.00 | 1.00 | 0 |

**LLM 唯一胜面=topic_switch（3 例小样本）**；两个延续族（cont_new/
clarify）LLM 显著更差——其把 ack/答案形消息当新意图（22 例
det-right/llm-wrong 的主因）。

## 7. Disagreement Ledger（36 例·全量在 obs JSON）

- **det-wrong/llm-right：4**（OBS1-02 重疾保额建议多少→det 落
  unknown；E-04/E-18/G-S2-QA-FU-03）——LLM 的真实语义增益点
- det-right/llm-wrong：**22**（延续族误判+QA→PLAN 高危）
- both-wrong：10（taxonomy 张力区为主）
- llm 无效应答 21/88（raise:RuntimeError——4s 超时适配器 fail-closed）

**值得进入下一阶段的分歧（Q6）**：仅 OBS1-02 类（泛化建议量词
question 的 unknown 兜底）——但这可由**确定性词表**修复
（建议多少/通常多少 入 qa 信号），无需 LLM（Owner 裁决）。

## 8. LLM Stability（30 边界例 ×3）

**精确稳定 23/30**；7 例漂移全部=**应答↔raise 振荡**（E-15 三次中
两次超时）——无同输入标签翻转（planning→qa→planning 形态未出现，
但 None↔label 振荡等价于可用性不稳）。

## 9. Failure Modes

- **raise（超时/传输）21/88=24%**——最大失败模式（4s 预算 vs glm
  夜间延迟·沿 K.9 族已知供应商画像）
- invalid schema/unknown label/幻觉 intent：0（适配器契约门有效）
- explanation-vs-label 矛盾：未观察到（explanation 不入判定）
- context 忽略/最新消息忽略：未观察到（但延续族误判=**上下文语义
  权重错误**——LLM 未把 pending 语义纳入，candidate 协议不含
  pending_clarification 输入=架构性限制，ADR-019 M1 候选输入面缺口）

## 10. ADR-019 合规

- **Case A**（同消息异上下文）：deterministic 实证——「那这款呢？」
  无上下文=unknown / P004 上下文=product_qa（锚继承按 ADR-019 规则
  7）✓
- **Case B**（active case）：modify clarify 语义正确分叉 ✓
- **Case C**（prompt 稳定性）：适配器 `_SYSTEM_PROMPT` 为模块常量+
  vocabulary 插值——prompt 非意图源（规则 8）✓；LLM 路径因
  raise 率未做 C 类重复（如实）
- **缺口（记录）**：candidate 输入=（message+recent context）——
  **不含 pending_clarification**→延续族语义盲=结构性输入面缺失。

## 12. OBS-1 裁定（Q7）

10 例逐字结果：det 9/10 正确（唯一 miss=OBS1-02 泛化建议问句→
unknown）；LLM 4/10（3 例 QA→**PLAN** 高危反转+2 raise）。**OBS-1
=正常 taxonomy 内的知识覆盖/信号覆盖问题**：量词问句（建议多少/
通常建议）缺 qa 信号词→落 unknown（governed fail-closed 拒答）+
G-1 语料缺→拒答文案。属 **knowledge/coverage limitation（信号词表
+语料），非 taxonomy 边界/非 router gap**；确定性修复路径存在
（词表 2 词）=Owner 裁决项。

## 13. Limitations

单晚单模型（glm-5.3·夜间延迟画像）·LLM 失败率 24% 压低其指标
（应答内 83.3% 仍低于 det 86.1%）·金标子集 40 例为既有冻结期望·
candidate 无 pending 输入（架构限制影响延续族公平性——但补该输入
=候选协议变更=Owner 决策）。

## 14. 架构建议（非 rollout 决策）

**Scenario C（整体无优势）+局部 B（topic_switch/泛化问句小胜面）**：
- Q1 否（86.1% vs 63.3%/83.3%·且 24% 无效应答）
- Q2 否（plan↔qa 0.94 vs 0.81）
- Q3 否（延续族 0.75/0.87 vs 0.46/0.40——结构性输入缺失）
- Q4 **是**（QA→PLAN 3 例=错工作流执行风险·det 侧同类 0）
- Q5 部分（23/30·漂移=可用性振荡）
- Q6 仅 OBS1-02 类（确定性可修）；LLM 候选不值得进入 authority 立项
- Q7 knowledge/coverage limitation（见 §12）
- **建议**：维持 LLM=CANDIDATE OFF；OBS-1 信号词补全=确定性 FIX
  候选（2 词·Owner 授权另立阶段）；candidate pending-输入扩展仅当
  Owner 欲重启语义轨道时再评估。

## 15. 生产状态（完成确认）

Intent/C1/C2/K.26 SEALED·D-08 SEALED·OD-12 FROZEN·LLM Intent=
CANDIDATE ONLY（env 未设）·Deterministic=AUTHORITY·S2
OPEN-UNSTARTED·Batch-2 未分发·Production Authority NOT GRANTED·
本 benchmark 仅进程内 env·零生产副作用。

证据：`tmp/obs/g05_{arbitration,stability}.json`·数据集
`tests/golden/intent-arbitration-benchmark.v1.json`（v1 冻结）。
