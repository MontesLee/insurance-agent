# Pre-UAT OBS-1 Deterministic Signal Fix

Date: 2026-09-30 · Mode: **最小确定性 signal 补全**（2 词·零 LLM·
零 taxonomy/Router/C1 变更）· **PRE-UAT OBS-1 DETERMINISTIC FIX: PASS**
（+ **D-08 SPAN RESEAL REQUIRED**——intent-rules.yaml 为 e306118 封印件）

## 1. Current Reproduction（修复前·当前码实跑）

10 条逐字复现：**OBS1-02「重疾保额通常建议多少？」= 唯一 miss** →
`unknown_insurance_intent`（governed 兜底）→ conversation-agent；
其余 9 条均已达 sealed 期望（01/03/05-10=qa·04=plan）。

## 2. Root Cause（§2·信号表实读）

- QA 信号表（intent-rules.yaml insurance_qa.signals）：产品名词带
  险 后缀（重疾险/医疗险…）+ 概念词（等待期…）+ 量词族（多少合适/
  该买多少/买多少合适）。
- **OBS1-02 miss 机制**：「重疾**保额**」无「险」后缀→名词信号不
  命中；「通常建议多少」不在量词族→零命中→unknown（有锚=治理）。
- benchmark 增益点唯一定位：G-05 det-wrong/llm-right 4 例中 OBS1-02
  是唯一纯信号缺口（其余=E-04 语义张力/E-18/FU-03 既有边界）。
- 对 Planning 的影响：plan 动作信号（rule 4）先于 qa（rule 5）——
  新 qa 信号不可能抢走已含 plan 动作词的消息。

## 3. Minimal Fix（§3·原则 A-D 全守）

`insurance_qa.signals += [建议多少, 多少保额]`（2 词·yaml 单点）。
- **原则 C**：非裸高频词——「建议多少/多少保额」为量词问句复合形
  （与既有 多少合适/该买多少 同族同粒度）；裸 建议/配置/多少/购买/
  合格 未动。
- **优先级（原则 D）**：plan-first 不变（rule 4 先于 rule 5）——
  含 plan 动作词的消息恒 plan；新信号仅在 qa 规则内生效。

## 4. Before / After（OBS-1 矩阵·sealed gold 口径）

| Case | 前 | 后 | sealed gold |
|---|---|---|---|
| 01 | qa | qa（+rule:qa:多少保额） | qa ✓ |
| **02** | **unknown** | **qa（rule:qa:建议多少）** | **qa ✓ 缺口闭合** |
| 03 | qa | qa（不变） | qa ✓ |
| 04 | plan | plan（不变） | plan ✓ |
| 05/06/08/09 | qa | qa（不变） | qa ✓ |
| 07 | qa | qa（不变） | qa ✓ |
| 10 | qa | qa（不变） | qa ✓ |

**10/10 sealed-gold 正确**。注（如实）：任务书 §4 表将 03/07/10 标
为 Planning——与 **e306118 封金黄标**（S1-QA-19/20 同型=qa）冲突；
按 §4 规则「不要自行改变 Gold」以 sealed gold 为准，差异列
OWNER_DECISION（个性化量词问句 qa↔plan 语义=既有 GOLD_UNCERTAIN
张力，非本修复引入）。

## 5-6. 污染与语义对照（新 test_obs1_signal_fix.py **52/52**）

- **Planning contamination（15+2 例）**：全部 plan 保持（含「帮我
  规划，重疾险一般建议多少」——plan 动作词优先实证）；pending 中
  「建议多少」问句=切换（frozen C1 语义）·纯答案形=延续。
- **QA contamination**：8 例 qa 保持；**量词族捕获非保险问句=
  既有 sealed 特性**（PRE-fix 实证：「手机买多少合适」→qa——修复
  前即如此；新 2 信号与该族行为一致·记录不扩修=最小范围纪律）；
  无量词信号的非保险消息保持 unknown。
- **最小对照**：positive/negative/near-miss 各 2（「建议买多少」买
  介入≠命中·「保额多少」序≠命中·一词翻转 03↔04 形）全过。

## 7. 完整回归

| 套件 | 结果 |
|---|---|
| Intent Golden（220） | **95.91%·F1 0.9486·逐位不变**（零回归） |
| intent_fix_regression must-pass | 失败=同 6 例 D3/D4 锁定类（修复前同集合·零新增） |
| arbitration benchmark det | 79 分之 69→**0.873（+0.012·OBS1-02 修复**·其余 miss=既有张力族不变） |
| C1（12 节） | 12/12 |
| Router 路径（qa/plan/pq/non/invalid） | 全部不变（52 项内） |
| 决策链 E2E+FI | **22/22** |
| **全电池** | **865 passed + 2 skipped** |

## 8. LLM 状态

`INSURANCE_AGENT_INTENT_LLM`=未设（OFF）·LLM Candidate 不参与判定
·Deterministic=AUTHORITY——本修复纯词表·零 LLM（§8 ✓）。

## 9. E2E 验证

- QA path：OBS1-02 形 → insurance_qa → insurance-qa-agent
  （registry_lookup）→ 空检索 → **insufficient_evidence 诚实拒答**
  ——**Intent routing fixed ≠ Knowledge coverage 修复**（§10 区分
  如实：G-1 语料限制保留，拒答为正确 fail-closed）。
- Planning path：`帮我做家庭保障规划` → plan → planning-agent 不变。

## 10. G-1 remaining limitation

语料缺口（28.C-3 BLOCKED@JWT）**未触碰未修复**——修 Intent 后用户
将看到治理拒答（换说法/稍后再试）而非沉默 unknown：路由修正+覆盖
受限两事实并存。

## 13. Production State / Rollback

- 生产状态：LLM=CANDIDATE ONLY·Det=AUTHORITY·S2 OPEN-UNSTARTED·
  Batch-2 未分发·Authority NOT GRANTED·C1/C2/K.26/Claim Support
  零触碰。
- **D-08 SPAN RESEAL REQUIRED**：intent-rules.yaml 属 e306118
  （D-08 intent seal）封印范围——本修复已修改该文件，intent seal
  需 Owner 续封（复验证据=本报告+逐位不变的 golden 指标）。
- Rollback：删除 2 信号行（行为即回 OBS1-02 unknown 兜底）。

## 16. Final Decision

**PASS**（sealed-gold 口径 10/10·缺口闭合·零污染·零回归·零 LLM）
——随附 **OWNER_DECISION ×2**：①03/07/10 个性化量词问句 qa↔plan
语义（任务表 vs 封金黄标冲突·gold 未动）②D-08 intent span 续封
授权。
