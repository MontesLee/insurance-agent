# K.29-C FIX-3 Phase 5 · Semantic Judge Authority Readiness Review

Date: 2026-10-02/03 · Mode: **AUDIT/ANALYSIS ONLY**（零生产改动·
authority 未授予·状态全部冻结保持）·终态:
**AUTHORITY_REVIEW_EVIDENCE_SUFFICIENT**（=证据包足以提交 Owner
Authority Decision;≠GRANTED）

---

## Q1 — Judge 是否稳定?（τ×重复×顺序)

- **重复稳定性**:v2 冻结语料 ×3 重放(246 判定)·**精确决策一致
  97.6%**(漂移 2 例逐条列明非均值掩盖:F1-11 1/3·F4-10 2/3);live
  重复簇 95.3% 一致。
- **τ 敏感度**(τ 网格全部离线重算·未动生产):

| τ | ALLOW | KEEP | UNCERTAIN | FU(vs gold) | 高危 ALLOW |
|---|---:|---:|---:|---:|---:|
| 0.50 | 67 | 179 | 0 | 5 | 3(=F5-05×3rep) |
| 0.60 | 67 | 179 | 0 | 5 | 3 |
| 0.70 | 67 | 179 | 0 | 5 | 3 |
| 0.80 | 65 | 179 | 2 | 4 | 3 |
| 0.90 | 54 | 179 | 13 | 1 | 1 |

**判读**:0.5-0.7 为稳定区间(决策不变);≥0.8 只损 utility
(UNCERTAIN 增);**FU 集合对 τ 不敏感**——F5-05 在全部 τ 持续
(高置信外知渗漏·非阈值问题)。live 语料同型(0.5-0.7 ALLOW
107-108·0.9 降至 71)。**安全拐点不存在——阈值调不掉 F5-05。**

## Q2 — 是否只在低风险场景 ALLOW?

**管线形态**(硬类前置终局):live 79 轮 numeric/payment/regulatory
全 KEEP·date 0 样本(前置)·唯一 negation ALLOW=ACR-023(方向一致
真 paraphrase·已裁 SAFE)——**管线高危 ALLOW=0(观察+结构双证)**。

**判定单独形态**(前置旁路·直测判定器):ALLOW 大量出现在
numeric/product/regulatory/date 类——但逐类对照 gold:**除 F5-05
外全部为 gold-ACCEPT 的verbatim正例**(如「P004等待期90天」)。
逐类逃逸精算(唯一案例集):date/numeric/regulatory/R3 族全部
收敛于 **F5-05 单案例**;payment/negation 0;product 0。

## Q3 — FALSE UPGRADE ledger

`tmp/obs/k29c_fix3_phase5_false_upgrade_ledger.jsonl`(rep1·τ0.7·
全字段 22 条 ALLOW 逐条)。**FU=1(F5-05·high·逐条可审计)**:
claim「该办法自2019年12月1日起施行」/证据正文无日期(仅治理锚
effective_from)/gold=REJECT(pin)/judge=ALLOW 0.9/confidence 0.9/
归因=**外部知识渗漏**(模型自知道该办法施行日期)/处置=SHADOW_ONLY
·**管线前置拦截(日期词形)——设计捕获·可解释**。另 pooled 漂移面
F1-11(2/3 rep)·main 模型 1 例(见 Q4)。无不可解释高危 FU——但
BF 清单成立(见矩阵)。

## Q4 — 单模型限制可否解除?

**MODEL_DIVERSITY = VERIFIED**(离线 comparator·glm-5.3 main×82):
决策一致 **95.1%**;main 专属 ALLOW=F1-11·**main 高危 FU=0**
(F5-05 main 判 KEEP——主模型不渗漏该日期);flash 专属=F1-03/
F4-10/F5-05。**两模型各有一个互不重叠的弱点**:flash=元数据日期
外知渗漏(高危·管线可拦)·main=「所有」泛化(低危·**前置不可拦**)。

## Q5 — 高危覆盖是否足够?

| 层 | 样本 | ALLOW | 逃逸 |
|---|---:|---:|---|
| numeric | 149 | 32 | 0(全 gold-ACCEPT) |
| product | 76 | 24 | 0 |
| regulatory | 38 | 6 | 0 |
| payment | 31 | 0 | 0 |
| date | 27 | 9 | 0(8 正例+F5-05) |
| negation | 6 | 1 | 0(ACR-023 SAFE) |
| R3(F5 族) | 48 | 21 | 0(管线) |
| **R4 direct** | **0** | — | **COVERAGE_INSUFFICIENT** |

**如实声明**:管线高危零=结构(前置)+观察双证;判定单独高危
逃逸=F5-05 单案例(非零);R4 直测样本=0。

## meta-prose 专项

累计 118 meta claim·31 ALLOW·**高危 ALLOW=0**·零传播证据(高危词
形仍前置终局)→ **WATCH_ONLY 维持**(BF-清单无此项)。

## Authority Readiness Matrix(摘要·全表见 JSON)

19 门:**PASS 14 · FAIL(judge-alone 层)4[false-upgrade/high-risk-
FU/R3/numeric/regulatory/date 六门中判定单独层=F5-05 同因] ·
INSUFFICIENT_COVERAGE 1(R4)**。

**Authority grantable now = NO**·阻断项:
- **BF-1** flash 判定单独高危 FU=F5-05(元数据日期外知渗漏·全 τ
  持续·管线可拦·main 不渗漏)
- **BF-2** F1-11「所有」泛化 FU 类**不可被现前置拦截**(flash 2/3·
  main 1/1·低危但为真实未阻断升级路径)
- **BF-3** R4 直测覆盖=0

## 零改动审计(§12)

git 生产面=Phase-2 span 三文件(mtime 20:52-21:05·早于本阶段);
本阶段新增=tools×2 + 7 证据 JSON + 报告;无任何生产行为变化;
authority 路径 grep=空。

## 工件

k29c_fix3_phase5_{tau_sensitivity,stability,highrisk_coverage,
false_upgrade_ledger.jsonl,model_diversity,meta_prose,authority_
matrix}.json + replay.jsonl(328·raw 全存)。

## 终态(强制保持)

B/D gray=LIVE · Shadow=LIVE(SHADOW ONLY) · Authority=NOT GRANTED ·
Hybrid=OFF · S2=UNCHANGED · Batch-2=NOT DISTRIBUTED · D-08=SEALED。
