# K.29 Phase 3 · Scenario B Resolution — 修复后拒答归因与量化

Date: 2026-10-02 · Mode: ANALYSIS（零代码改动·纯证据分析）
输入:Phase 2 A-fixed benchmark（tmp/obs/k29b/A_fixed_{main,flash}_all.jsonl）
对照:K.29-B arm A（修复前生产行为·A_{main,flash}_all）+ arm A2（诊断臂）
证据索引:tmp/obs/k29_phase2_delivery_verify.json ·
tmp/obs/k29_phase2_before_after.json

---

## 1. 场景判定:Scenario B(citation 提升·拒答仍大量)

| 信号 | 判定依据 |
|---|---|
| 引用提升 | ✓ 完整度 0.273→0.381(main)/0.246→0.402(flash);no_citation 违规 35→1/47→3 |
| 拒答仍大量 | ✓ grounded 0/30 双模型(citation-gate 拒 23+23·证据不足拒 7+7) |
| 与诊断臂一致 | ✓ A-fixed ≈ A2(0.381 vs 0.401·cs 违规 107 vs 115)——修复完整复现诊断预期 |

非 Scenario A(delivery 不是充分原因)·非 Scenario C(模型能力
已非主瓶颈,见 §2)。

## 2. 拒答三分类归因（23+23 citation-gate 拒·权威=gate violations）

### 2.1 模型生成问题 — 基本解决（残余 ~4-13%）

- 纯引用纪律拒（violations 全为 no_citation）:**main 1/23·flash 3/23**。
- 修复前对照:main 15/30·flash 19/30 记录含 no_citation。
- 残余生成面:would-be 答案真违规（未引用保险数字/产品断言, refined）
  main 16→**1**·flash 11→**5**（提示词实达使模型更贴证据——安全面
  同步改善;false_success=0——无任何带违规答案被交付）。

### 2.2 Claim Support 安全拦截 — 当前主瓶颈（~87-96% 记录）

- 纯 claim_support 拒:main 22/23·flash 20/23。
- 违规构成（violation 级）:main = PARTIAL×78 + UNSUPPORTED×29;
  flash = PARTIAL×61 + UNSUPPORTED×51。
- **PARTIAL=paraphrase 天花板**（最大块）:模型用近义改写复述证据
  （「凭票据按约定比例报销[E2]」vs 证据原文措辞）——确定性 bigram
  覆盖 <100% → PARTIAL → 现行 SUPPORTED-only 规则拒。
- UNSUPPORTED 构成:证据缺失叙述（「证据未提及X[E1]」类 meta prose
  ·判定层词法不可证）+ 判定缺口（ws 空格·治理锚日期不搜内容）+
  极少量真越证（§3）。

### 2.3 Citation 结构问题 — 微量

- 全角括号/编号错位等结构违规:修复后 no_citation 仅 1-3 条
  （提示词 VALID/INVALID 示例生效）;结构壳（C-5A 的 13% 天花板）
  不再是可见主因。

## 3. 政策杠杆模拟（final attempt · 上界估计·非建议）

| 政策变体 | main 翻转 | flash 翻转 | 说明 |
|---|---:|---:|---|
| 现行（SUPPORTED-only） | 2*/23 | 2*/23 | *eval 过滤口径差·实际 0 |
| +接受 PARTIAL（paraphrase 容忍） | 12/23 | 9/23 | 单杠杆最大 |
| +证据缺失叙述豁免（meta 豁免） | 19/23 | 16/23 | 叠加收益最大 |
| +ws 归一化 | 19/23 | 17/23 | 微量（+1） |
| **残余真违规记录** | **4** | **6** | 每例 1-2 claim |

残余违规性质（抽样）:meta 变体漏网（「现有语料未说明…」「仅有
标题」）·监管定义改写（R2-08 健康保险定义——证据内但措辞距离远）·
推断句（「该条款表明保监会是参与制定…的部门之一[E1]」=证据+一步
推理）·flash 3 例 no_citation 残余。**无一例为无据编造数字/产品
承诺**——fail-closed 方向全程保持。

## 4. 结论

1. **system_prompt delivery 是「引用纪律」的充分原因**（已修复:
   no_citation 近零化·真违规 16→1/11→5）。
2. **它不是「grounded=0」的充分原因**:现行拒答 ~90% 由 Claim
   Support 的词法天花板（PARTIAL）与 meta-prose 不可证性构成——
   这是**安全层校准问题,非安全问题**（方向 fail-closed·无逃逸）。
3. 因此:**未满足进入 K.29-C Shadow 的可解释性前置**（shadow 会把
   校准噪声当作 MODE-B 行为信号;K.29-B §10.2 缺口 2/3 正是本归因
   的量化版）。
4. 对 D-04 的最终重读:其「C5 模型能力(主)」应改写为「C1' 指令
   未送达(主·已修复)+C7 判定层 paraphrase 天花板(次·现存)+C6
   正确安全拒答(少量·维持)」。

## 5. 下一步（进 Phase 4 决策包·不自选）

选项已在 docs/production/k29-owner-decision-package.md 列出:
A 保持 KB_ONLY（现状=修复后·全拒但诚实）·B 进 Hybrid Shadow（受
§4.3 前置约束）·C 模型/回答结构/判定层校准优化（P/meta/ws 三杠杆
=上界 19/23·17/23 翻转——但全部触碰 SEALED Claim Support 规则=
需 Owner 解封授权）。
