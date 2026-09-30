# Pre-UAT OBS-1 Runtime Reverify + D-08 Intent Span Resead

Date: 2026-09-30 · **PRE-UAT OBS-1 RUNTIME REVERIFY: PASS ·
D-08 INTENT SPAN: RESEALED（reseal commit 见 §9）**

## 1. Pre-Restart Snapshot

HEAD=24082d5·intent-rules.yaml sha **e2ff4899**（旧封印 e306118 blob
sha **f28e7376**）·:8123 PID 33072（旧码）·`INSURANCE_AGENT_INTENT_LLM`
env 未设（OFF）·`CLAIM_SUPPORT_ENABLED=1`·Planning OFF·Authority NOT
GRANTED·S2 OPEN-UNSTARTED·Batch-2 NOT DISTRIBUTED。

## 2. Runtime Restart + Loaded Evidence

- 重启（仅 :8123·启动参数零变化）：**PID 31740**·start
  **2026-09-30 20:48:41**·health 200（~3s）。
- **载入证明（行为级非文件级）**：intent-rules.yaml mtime 20:35 <
  start；live API OBS1-02「重疾保额通常建议多少？」→
  **insurance_qa/knowledge-qa slice fired**（修复前=unknown/
  conversation-agent——两条新信号在运行进程中生效的直接行为签名）。

## 3. OBS-1 Runtime Matrix（live API·10/10 sealed-gold）

| Case | live intent | slice | 终态 | sealed gold |
|---|---|---|---|---|
| 01 | insurance_qa | knowledge-qa | completed | ✓ |
| **02** | **insurance_qa** | **knowledge-qa** | completed | **✓ 缺口 live 闭合** |
| 03 | insurance_qa | knowledge-qa | completed | ✓（sealed；任务表张力→§10） |
| 04 | insurance_plan | plan | waiting | ✓ |
| 05-10 | insurance_qa | knowledge-qa | completed ×6 | ✓ |

**10/10 sealed-gold 一致**（03/07/10 任务表-封金冲突维持
OWNER_DECISION——§10 禁裁）。

## 4. Planning Contamination（live·4 例）

- 「我35岁，房贷80万，重疾险配置多少合适？」→ **plan** ✓
- 「帮我规划一下重疾险，一般建议多少？」→ **plan** ✓（plan 动作词
  优先于新信号·live 实证）
- 「我的家庭收入50万，重疾险一般建议买多少？」→ qa·
  「按照我的家庭情况，重疾险保额应该怎么定？」→ qa——
  **证明性核查：两例均无新信号子串命中**（「建议买多少」买介入·
  「怎么定」无信号；其 qa 来自**既有** 重疾险 名词信号=PRE-fix
  行为逐字不变）→ **非本修复引入**，属 §10 同一个性化量词问句
  语义张力（OWNER_DECISION 沿袭·gold 未动）。

## 5. C1 Pending/Continuation（frozen·4/4）

pending+建议多少问句=切换 qa ✓·上下文锚+保额建议多少=product_qa ✓·
pending+纯答案=plan 延续 ✓·pending+定义问句=切换 qa ✓——OBS-1 信号
未绕过 C1 任何 frozen 行为。

## 6. E2E QA（OBS1-02·live）

insurance_qa → Router=insurance-qa-agent（registry_lookup）→
knowledge-qa slice → 检索 → 终态 completed（诚实终态）——
**Intent routing fixed ≠ Knowledge coverage fixed**：G-1 语料限制
保留（§0 禁增知识；拒答/诚实终态=PASS 口径）。

## 7. Full Frozen Regression

Intent Golden 220 **逐位不变**（95.91/0.9486/sev 全同）·C1 12/12·
C2 8/8·K.26 6/6·B4 7/7·OBS-1 套件 52/52（合并 33 pytest 项）·
决策链 E2E+FI **22/22**·**全电池 865 passed + 2 skipped**。
taxonomy/router/resolver/golden 零变化。

## 8. LLM State

`INSURANCE_AGENT_INTENT_LLM`=OFF（env 未设）·LLM Candidate 不参与
终判·Deterministic=AUTHORITY——全程未变。

## 9. D-08 Intent Span Resead Evidence

| 项 | 值 |
|---|---|
| old sealed hash（e306118 blob） | f28e7376f188de87 |
| new hash（工作树=运行载入） | e2ff4899e0e04a15 |
| **exact diff** | +10 行（8 注释+**2 信号**：建议多少/多少保额·§1 全文在案） |
| tests | OBS-1 套件 52/52 + golden 逐位不变 + C1 12/12 + E2E 22/22 + 电池 865+2 |
| runtime | PID 31740·loaded=行为签名（§2） |
| rollback | 删 2 信号行→回 OBS1-02 unknown 兜底（离线已验·不执行） |
| 不变量 | golden/taxonomy（vocabulary=5）/router/resolver 零变化 |

**D-08 INTENT SPAN RESEALED**（commit：`git log -1` 本报告提交；
证据文件=本报告+pre-uat-obs1-deterministic-fix.md+obs1_runtime_
matrix.json）。

## 10. 03/07/10 Owner Decision（维持）

GOLD_UNCERTAIN / OWNER_DECISION_REQUIRED——gold 与 taxonomy 均未
动（含 §4 两例污染张力同族）。

## 11/12. Rollback + Final State

Rollback=删 2 行（可行·离线验证）。
```
OBS-1 FIX = RUNTIME VERIFIED · D-08 INTENT SPAN = RESEALED
Intent/C1/C2/K.26/Claim Support = SEALED
LLM Intent = CANDIDATE ONLY/OFF · Deterministic = AUTHORITY
S2 = OPEN-UNSTARTED · Batch-2 = NOT DISTRIBUTED
Production Authority = NOT GRANTED
```
