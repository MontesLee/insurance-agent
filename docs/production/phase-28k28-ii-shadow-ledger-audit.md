# 28.K.28-II-SHADOW-LEDGER-AUDIT · 影子实验账本审计

Date: 2026-09-29 · Mode: **AUDIT ONLY**（零生产/影子逻辑/语料修改；
唯一改动=§10.6 所述 Case A 报告笔误更正）·
**Audit Status: PASS_WITH_REPORT_CORRECTION**

## 1. Audit Method

Raw Evidence → Recalculate → Compare Report（不反向）：
`tmp/obs/k28iish_results.json`（终版评测输出）·`tmp/obs/k28iish_llm.json`
（30×2 对照 rows）·`tests/golden/claim-evidence-shadow.v1.json`（冻结
语料）为唯一事实源；全部指标独立重算（脚本级，非读取存储汇总）。

## 2. Ledger Reconciliation

| Metric | Report | Recalculated | Match |
|---|---:|---:|---|
| Shadow n | 103 | 103 | ✅ |
| Deterministic exact | 83.5% | 83.50%（86/103） | ✅ |
| Typing | 94.2% | 94.17% | ✅ |
| C-FACT P / R | 0.80/0.80 | 0.8000/0.8000（TP20 FP5 FN5 TN58·n=88） | ✅ |
| FSR（of judged-S） | 20.0% | 20.00%（5/25） | ✅ |
| FSR（of actual-unsup） | 7.94% | 7.94%（5/63） | ✅ |
| Escape numerator | 15（现门）/0（影子） | 15 / 0 | ✅ |
| Escape denominator | 17 | 17 | ✅ |
| LLM n | 30 | 30（应答 30） | ✅ |
| LLM exact | 76.7% | 76.67%（23/30） | ✅ |
| Agreement | 76.7% | 76.67%（23/30·同分母 30） | ✅ |
| LLM stability | 30/30 | 30/30 | ✅ |
| RV4-A | 0 qualified | c2_qualified_count=0·pass=True | ✅ |
| RV4-B | 捕获 | PARTIAL 期望→UNSUPPORTED 判定（policy-equivalent 不投递） | ✅ |

分母一致性专项：prf 集（claim_type=C-FACT）=88=103−15 豁免类 ✓；
agreement 分母=LLM 子集 30（与 det 子集同 30）✓；escape 分母=
current_gate=passes 的 17（N1×7+N9×4+N10×6）✓。

## 3. FS-01~FS-10 终版账本（逐条）

| FS | Case | Claim | Evidence | Expected | Det | LLM | Escape |
|---|---|---|---|---|---|---|---|
| FS-06 | N3-3 | 保额100万且含身故责任 | 保额100万（fixture） | PARTIAL | **SUPPORTED** | UNSUPPORTED | 现门逃逸/影子拦 |
| FS-06 | N3-6 | P001保费400元且无免赔额 | catalog 400元 | PARTIAL | **SUPPORTED** | UNSUPPORTED | 同上 |
| FS-06 | N3-7 | 赔付比例100%并覆盖进口药 | 比例100% | PARTIAL | **SUPPORTED** | — | 同上 |
| FS-06 | N3-8 | 续保20年且费率不变 | 续保20年 | PARTIAL | **SUPPORTED** | — | 同上 |
| FS-04 | N4-3 | 这款百万医疗险A等待期90天 | P004 绑定证据 | UNSUPPORTED | **SUPPORTED** | **SUPPORTED**（LLM 亦假支持） | 同上 |
| FS-01 | — | 无（N1 7/7 全拦） | | | | | |
| FS-02 | — | 无（终版数据零例·见 §6） | | | | | |
| FS-03 | — | 无 | | | | | |
| FS-05 | — | 无（N6 6/6） | | | | | |
| FS-07..FS-10 | — | 无 | | | | | |

（LLM 列空白=该例不在 30 例对照子集。非 FS 的 17 失败另账：
MISS-partial ×5=P02/P03/P16/P21/P22·OTHER ×7=P04/U03/D02/D03/
N8-2/N8-5/RV4-B——与存储计数器逐位一致。）

## 4. Escape 17 条逐条账本

N1-1..N1-7（7 条 citation-only：现门全逃逸→影子全拦）·N9-1/N9-4
（期望 N/A·**不计逃逸**·两门皆不放行——勘误 E2 后口径正确）·
N9-2/N9-3（RV4 形态：逃逸→拦）·N10-1..6（stuffing：逃逸→拦）。
**现门 15/17=88.2%·影子 0/17·降幅 100%** ✅。

## 5. RV4 双层

- **RV4-A（Evidence Qualification·C2 层）**：真实
  `_qualified_evidence`（RV4 原文 query × 农业保险条例）→
  **0 qualified**——C2 问题域，与 Phase 2 无关，seal 实证 ✅。
- **RV4-B（Claim Support·Phase 2 层）**：健康险法规（对 重疾/医疗
  族 query **通过 C2**——Qualified）×「该重疾险的等待期为90天」→
  影子 UNSUPPORTED（证据仅言参数由合同约定）→ 不投递。
  **Qualified ≠ Supportive 成立**，为本审计确认的 Phase 2 核心证据 ✅
  （标签 PARTIAL vs UNSUPPORTED 粒度差=policy-equivalent，两态均
  不投递——已在报告 §10 如实披露）。

## 6. Discrepancy 裁定（§10.6 指定问题）

**问**：报告 §8 写「5 例逐条」却列 FS-06×4+FS-04×1+FS-02×1=6 项？
**证据**：终版 `fs_classification` 计数器与逐条重算均为
`{MISS-partial:5, OTHER:7, FS-06:4, FS-04:1}`——**无 FS-02**；
judged-SUPPORTED 失配集=**5 例**（N3-3/6/7/8+N4-3，全 C-FACT），
与 FP=5→P=20/25→FSR=20% 链条**逐位自洽**。「FS-02×1」系撰写报告时
误引**组合规则修正前的中间运行**统计（该轮确有 FS-02×1，修正后
消没）——**Case A：报告统计笔误**，非重复计数/分母错误/fixture
统计错误。处置：已按允许范围仅更正报告 §8（附更正标注），实验
数据、判定逻辑、语料零改动。

## 7. 附带核对

- 攻击面重算：N1 7/7·N2 8/8·N5 5/5·N6 6/6·N7 6/6·N9 4/4·N10 6/6
  （报告"100% 类"✓）·N3 4/8·N4 5/6·N8 4/6（报告 50%/83%/67% ✓）。
- 流式：S1 7/10·S3≡S1（10/10 s3_same）✓；K.26 零触碰。
- LLM comparator 独立性：deterministic 结果文件先于 LLM 运行生成且
  未被触碰；judge 输出仅入 llm.json；无任何回写路径 ✅。
- 安全：shadow 包生产 import=0（10 处 shadow 命中均为既有
  INTENT-shadow 层）·gate/loop/classifier/rules 自 e306118 零变更
  （git diff 空）·零 DB/EventBus/SSE/Consumer 面 ✅。

## 8. 结论

核心指标全部可由原始数据复算、分子分母一致、FS/Escape/RV4 账本
一致、LLM 仍 shadow-only、零生产行为/authority 变更；唯一问题=
Case A 报告笔误（已更正留痕）→
**K.28-II-SHADOW-LEDGER-AUDIT: PASS_WITH_REPORT_CORRECTION**

```
Production authority: OFF
LLM authority: OFF
Intent: SEALED  ·  C1: SEALED  ·  C2: SEALED  ·  K.26: SEALED
Phase 2 IMPL: NOT STARTED
READY FOR OWNER AUTHORIZATION → K.28-II-IMPL
```
