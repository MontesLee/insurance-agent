# 28.K.28-II-OD12 · Claim Support 验收门槛与灰度治理（冻结版）

Date: 2026-09-29 · Mode: **GOVERNANCE DESIGN ONLY**（生产逻辑/基线/
语料/测试零修改）· **K.28-II-OD12: PASS（框架已定义并冻结）**
——**不代表 Production Authority 已授予**

## 1. OD12_BASELINE（§3-4·永久引用）

| 指标 | 冻结值 | 证据 |
|---|---|---|
| False Support | **5**（历史语料基线） | k28iish/k28ii metrics |
| Unsupported Escape | **0** | live-gray/FIX1/reverify |
| FIX1 False Refusal | **0/6** | k28ii_reverify_fr.json |
| Support P / R | **0.80 / 0.80** | 冻结语料×生产模块 |
| Streaming（支持） | T_first < T_final（0.0-0.097s 实测） | 同上 |
| Streaming（拒答） | delta_count = 0 | 同上 |
| Consumer Metadata Leakage | **0** | 全 transcript/delta 扫描 |
| Frozen Regression | **865 passed + 2 skipped** | 全电池 |
| RV4-A | C2 = 0 qualified | 真实检索 live |
| RV4-B | REFUSED / no delivery | 生产回归 |

**证据表述原则（§4·冻结）**：以上为**当前 shadow corpus + Golden +
Live Gray/FIX1/Reverify 验证范围内的观测结果**——不得表述为「真实
线上总体错误率」、不得外推为「所有保险问题上的真实概率」、
「Escape=0」的正确表述为**「当前验证范围内未观察到 Unsupported
Escape」**。基线索引（含代码 sha/证据文件/运行态）：
`tmp/obs/k28ii_od12_baseline.json`。

## 2. 三层 Gate（§5·不设总分）

Safety-critical grounding 控制不使用综合评分——**任何 Quality 高分
不得抵消 Safety 失败**。三层各自独立判定。

## 3. Gate A · Hard Safety Gate（§6·任一命中=BLOCK）

| # | 条件 | 基线 | 失败动作 |
|---|---|---|---|
| A1 | **Unsupported Escape** | 0 | >0 → **BLOCK**（无例外） |
| A2 | **新增 False Support**（新观察期增量·非历史 5） | 增量 0 | >0 → BLOCK / OWNER REVIEW |
| A3 | **Consumer Metadata Leakage**（claim_id/run_id/support_state/内部评分/evaluator 字段/router 内件/debug） | 0 | >0 → BLOCK |
| A4 | **Unsafe Streaming Leakage**（unsupported delta>0 或先输出后拒答） | 0 | >0 → BLOCK |
| A5 | **RV4-B 回归放行** | refused | released → BLOCK |
| A6 | **冻结组件行为回归**（C2/Intent/C1/K.26/Auth/Ownership/Governance） | 0 | >0 → BLOCK（不自行修） |

## 4. Gate B · Quality Gate（§7·Review 语义·非安全放行条件）

| # | 指标 | 基线 | 规则 |
|---|---|---|---|
| B1 | False Refusal | 0/6 | 新增→REVIEW；**同 root cause 重复**→BLOCK EXPANSION；孤立单例→OWNER REVIEW。**不得因单例自动改生产逻辑**；False Refusal≠Unsupported Escape（§13 冻结：前者=Quality/Availability→Review，后者=Safety→Block/Rollback） |
| B2 | Support P/R | 0.80/0.80 | 冻结基线；观察 distribution shift；**显著**下降→OWNER REVIEW（「显著」不自行造无依据百分比——由 Owner 结合分布裁决） |
| B3 | Citation-only / Wrong Product / Partial / Stuffing / Wrong Version / Temporal / Contradiction | 全 blocked | 任何新增 escape → 归入 Gate A（Hard） |

## 5. Gate C · Operational / Governance Gate（§8）

扩大灰度前必须确认：Runtime 可回滚（`CLAIM_SUPPORT_ENABLED=0`）·
ON/OFF signature 可复现（既有 FIX1 签名）·Evidence 可追踪·
Observation 可审计·Report 可复核·**Owner 明确知晓当前 rollout
state**。

## 6. Rollout 状态机（§9·冻结）

```
S0 = OFF
S1 = CURRENT_GRAY      ← 当前（:8123 PID 25928·env=1）
S2 = EXPANDED_GRAY
S3 = PRODUCTION_AUTHORITY
```

**S0→S1**：已完成（DESIGN→SHADOW→LEDGER-AUDIT→IMPL→LIVE-GRAY→
FIX1→REVERIFY）。

## 7. S1 → S2 Expanded Gray（§10·须同时满足）

- Safety：Escape=0·新增 False Support=0·Leakage=0·Unsafe
  Streaming=0·RV4-B=REFUSED
- Quality：False Refusal 无重复性回归·P/R 无明显恶化
- Operations：Rollback verified·Observation evidence 在案·无
  runtime scope drift
- **Governance：Owner 显式批准（无批准不得扩大）**

## 8. S2 → S3 Production Authority（§11）

须满足：**连续 observation window + 全程无 Hard Safety failure +
无重复性 regression + Owner approval**。窗口时长与流量比例**不在本
阶段指定**（无既有平台 rollout policy 依据——具体数值属 Owner /
Release Governance 决策；本文件只冻结上述结构性条件）。

## 9. Rollback Policy（§12）

任一 Hard Safety Gate 失败：**S1/S2/S3 → S0 OFF**，步骤：
①`CLAIM_SUPPORT_ENABLED=0` ②按机制 restart ③验证 OFF signature
④验证旧路径恢复 ⑤记录 incident evidence ⑥**不自行修改 Claim
Support**。触发面=A1-A6 全集。

## 10. False Refusal 分级原则（§13·冻结）

False Refusal ≠ Unsupported Escape——前者 Quality/Availability
（Review/Investigate），后者 Safety（Block/Rollback）。除非 Owner
后续明文提高，两者不共用等级。

## 11. Owner Decision Matrix（§15·冻结）

| Gate | Current Baseline | Failure | Action |
|---|---:|---|---|
| Unsupported Escape | 0 | >0 | BLOCK / ROLLBACK |
| New False Support | 0 incremental | >0 | BLOCK / OWNER REVIEW |
| False Refusal | 0/6 | regression | REVIEW |
| Support P/R | 0.80/0.80 | significant degradation | REVIEW |
| RV4-B | refused | released | BLOCK |
| Partial | blocked | released | BLOCK |
| Wrong Product | blocked | released | BLOCK |
| Citation-only | blocked | released | BLOCK |
| Unsafe Streaming | 0 | >0 | BLOCK |
| Consumer Leakage | 0 | >0 | BLOCK |
| Frozen Regression | 0 | >0 | BLOCK |
| Rollback | verified | unavailable | BLOCK |
| Owner Approval | required | absent | NO EXPANSION |

## 12. Planning Claim Support 独立轨道（§16·冻结）

QA/ProductQA 已验证边界 ≠ Planning 边界（USER/DERIVED/
RECOMMENDATION/C-FACT 混合形态）——**QA 通过 OD-12 不自动开启
Planning**；Planning 须独立 Design→Shadow→Gray 轨道。

## 13. LLM Claim Judge（§17·冻结）

保持 **OFF**。生产 authority=Deterministic Claim Support；shadow
对照为历史实验依据，不经 OD-12 升级。

## 14. D-08 Span Seal · Release Evidence Index（§18）

Seal 条件已满足（IMPL+FIX1+GRAY+REVERIFY 全 PASS）——统一索引
建立于 `tmp/obs/k28ii_od12_baseline.json`：八份阶段报告（design/
shadow/ledger-audit/impl/live-gray/fix1/reverify/od12）·测试
（test_k28ii 48 检查+冻结语料 114）·十条 evidence 文件·运行态
（PID 25928=S1）·commit 关联（e306118 + IMPL/FIX1 工作树——
**实际 seal commit=Owner 后续 D-08 续封动作，本阶段不自动提交**）。

## 15. 本阶段合规声明（§20 核对）

生产逻辑修改=0（全部生产文件 mtime 早于本阶段）·基线/语料/历史
失败 case/历史 evidence 零改动·无新阈值造数·无 Quality 抵消
Safety·未扩大灰度·未开 Authority·未触 Planning/LLM。

---

```
K.28-II-OD12: PASS（acceptance framework 定义并冻结）

Claim Support:        READY_FOR_OWNER_DECISION
Current Rollout:      CURRENT_GRAY（S1）
Production Authority: NOT GRANTED
Planning Claim Support: NOT ENABLED（独立轨道）
LLM Claim Judge:      OFF
```
