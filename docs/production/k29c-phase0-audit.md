# K.29-C · Phase 0 Audit — Claim Support Calibration Study 前置确认

Date: 2026-10-02 · Mode: AUDIT（零改动·研究前置）

## 1. 输入确认

已读:docs/production/k29-owner-decision-package.md ·
docs/production/k29-phase3-b-resolution.md（本线产物·数据源
tmp/obs/k29b/A_fixed_{main,flash}_all.jsonl）。

## 2. Blocker 定位（数字复核·2026-10-02 新鲜计算）

| 层 | 状态 | 证据（A-fixed·40 例×2 模型） |
|---|---|---|
| Retrieval | **非 blocker** | 23/30 QA 例带 qualified 证据到达生成（7 例 pre-LLM 证据不足拒=真实 KB 空白·fail-closed 正确）;WeKnora 17 docs ACTIVE |
| Generation（引用纪律） | **非 blocker（已修复）** | 纯引用纪律拒仅 1/23（main）·3/23（flash）;引用完整度 0.381/0.402;no_citation 35→1/47→3 |
| **Claim evaluation boundary** | **BLOCKER** | 纯 Claim Support 拒 **22/23（main）·20/23（flash）**;违规构成 PARTIAL×78+61（paraphrase 天花板）+UNSUPPORTED×29+51（meta prose/判定缺口/少量真越证） |

**确认:当前 blocker = claim evaluation boundary**（Claim Support 的
词法判定边界），非 retrieval、非 generation。与 Phase 3 Scenario B
结论一致。

## 3. 研究边界（本任务约束重申）

- 冻结:Claim Support authority/Citation Gate/Intent/Router/K.29
  Hybrid OFF/S2 全部不动。
- 手段:纯离线——①对 K.28-II 冻结金标语料
  （tests/golden/claim-evidence-shadow.v1.json·114 例·P40+S10+
  N1-N10 攻击面 62+RV4×2）做候选政策重放（安全测量）;
  ②对 A-fixed benchmark 存储的 claim 级判定做政策翻转模拟
  （收益测量）。
- 候选:C1=现状 · C2=允许 paraphrase（cited∧PARTIAL 过）·
  C3=允许 general guidance（泛化建议/证据缺失叙述豁免）·
  C4=允许 metadata evidence（治理锚元数据+空白归一化入判定域）。
- 安全线:R3/R4 高危面（产品/数字/监管/赔付）必须 0 escape
  （金标语料 N4/N5/N6/N7/N10 + benchmark R3/R4 记录双验证）。

## 4. Go/No-Go

数据齐备（金标语料 114 带标签 + benchmark 80 记录 claim_rows）。
**GO → Phase 1 taxonomy 构造。**
