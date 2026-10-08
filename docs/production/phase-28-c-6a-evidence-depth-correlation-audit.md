# Phase 28.C-6A · Evidence Depth / Citation Failure Correlation Audit

Date: 2026-09-28 · READ-ONLY（仅既有真实数据：c4_violations.json +
c4a_shadow.json·零新实验·零生产改动·零因果声明）。

## Status

**ASSOCIATION_WEAK**（方向在聚合层存在、问题级被方差淹没——n=5 不足
以支持稳定关联判断；如实降级，不拔高）。

## 1. Question-Level Evidence（C-4·2 attempts 合并·真实数据）

| Question | ev | violations | passing | pass% | gate |
|---|---:|---:|---:|---:|---|
| 医疗vs重疾区别 | 0 | 36 | 8 | 18% | refused |
| 免赔额/续保 | 1 | 39 | 12 | 24% | refused |
| 意外vs医疗 | 1 | 42 | 15 | 26% | refused |
| 等待期 | **3** | **46** | 10 | **18%** | refused |
| 现金价值 | 2 | 34 | 18 | **35%** | refused |

## 2. Evidence-Depth Comparison（EV 粗粒度如实保留·不虚构 E0/E1 精度）

| Evidence 组 | 问题数 | 违规模式 | 拒答 |
|---|---:|---|---:|
| EV_LOW（ev≤1） | 3 | viol 36-42·pass 18-26% | 3/3 |
| EV_HIGH（ev≥2） | 2 | viol 34-46·pass 18-35% | 2/2 |

**关键反例**：ev=3（等待期）违规最多（46）且通过率最低（18%）——
**深度单调性在问题级不成立**；ev=2（现金价值）通过率最高（35%）。
方向线索：EV_LOW 三问全部处于低通过带；EV_HIGH 内部方差更大。

## 3. C-4A Consistency（§五检查）

| Question | ev | Arm A viol/gate | Arm B viol/gate | Δ |
|---|---:|---|---|---:|
| 免赔额/续保 | 1 | 40 / **grounded** | 54 / refused | +14 |
| 医疗vs重疾 | 0 | 30 / refused | 42 / refused | +12 |
| 意外vs医疗 | 1 | 32 / refused | 35 / refused | +3 |
| 等待期 | 3 | 28 / refused | 35 / refused | +7 |
| 现金价值 | 2 | 28 / refused | 38 / refused | +10 |

**Evidence pattern preserved: INSUFFICIENT_DATA（方向部分一致）**：
B 臂uniform 恶化（5/5 问 Δ>0）且最低 ev 问在两臂均居最差带——但
①唯一 grounded 出现在 ev=1（A 臂）②ev=3 在 C-4 轮最差、在 C-4A 轮
最好——跨轮方差 >> ev 效应。可支持的表述仅："prompt 变更未消除
低通过模式，且均匀恶化全部问题"。

## 4. C-5A Structural Correction（§六确认）

**C-5A safe structural exemption = 26/197 = 13.2%**（命题级判定）——
本审计所有表格与结论均不再引用 C-4 的 63%（表面结构模式统计）作为
"可豁免比例"。

## 5. Interpretation Boundary（§四纪律）

- 支持：聚合层方向线索（EV_LOW 全员低通过）+ 跨臂一致性方向
- **不支持**：单调深度→失败关系（ev=3 反例）；evidence depth *causes*
  failure；增加 evidence 将降低拒答 X%；KB ingest 将修复 QA
- 混杂因子未控：evidence **相关性**（ev=3 的法规块与概念题的语义距离）
  vs 数量；问题难度；模型采样方差（同问同证据跨轮 grounded↔refused）
- **Causal Claim: NOT ESTABLISHED**

## 6. 结论与含义

现有数据（C-4 n=5 + C-4A n=5×2）足以排除"证据深度单调决定引用失败"
的强假设，不足以确立稳定关联。**相关性质量（relevance）可能比数量
（depth）更关键**——这把 C-3 的预期从"补语料=修复"校准为"补对题
语料才可能修复"，且需 C-3R 解封后的受控 BEFORE/AFTER（同一 10 问
probe）才能升级为 ASSOCIATION_SUPPORTED。

## 7. Production Safety / Tests

Gate/Prompt/Model/Runtime/KB/.env/ADR-022：**unchanged**。
git diff --check clean；无新实验（纯数据重读）。
