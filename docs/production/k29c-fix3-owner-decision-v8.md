# K.29-C FIX-3 · Owner Decision Package v8

Date: 2026-10-03 · 输入:Phase 7 管线有界权威设计评审(零生产改动)。
详报:k29c-fix3-phase7-pipeline-bounded-authority-review.md;证据:
tmp/obs/k29c_fix3_phase7_*.json(5 件)。**只提交证据·不代决策·
本包任何内容 ≠ AUTHORITY_GRANTED。**

---

## 三候选对象终局

| 候选 | 判定 | 依据 |
|---|---|---|
| **A 裸 Semantic Judge** | **NOT AUTHORITY-SAFE** | F5-05(conf 0.9·3/3)+BF1-16(0.97)高危类高置信错误·BF2-01/BF3-01 双盲区·漂移依赖·τ 不敏感 |
| **B 纯确定性管线** | 安全面观察充分·**非形式证明**;已知盲区=E 类假拒(效用)+11 例词法残余+范围扩展+时点+**非数字个性化 REC(→OD-H3)** | Phase-2..6 全链 |
| **C 管线有界判定** | **可审议形态**(本阶段定义):C1 八硬类永不可升·C2 加固前置终局(0 绕过)·C3 五重合取——合取运行时+post-gate=NOT VERIFIED(实现阶段前置) | Phase-4/5/6 组件级证据 |

三治理规则明文化:语义正确≠权威安全;管线安全不蕴含判定安全;
**Authority 只授予完整决策链·不授予组件。**

## Owner Decisions

**OD-FIX3-25 是否承认:裸 Semantic Judge = NOT AUTHORITY CANDIDATE?**
证据:四例独立判定错误(两高危高置信·双模型盲区·漂移依赖·阈值
不敏感)。承认=未来任何 authority 议题只在 Candidate-C 形态内讨论。

**OD-FIX3-26 是否允许进入 Pipeline-Bounded Authority Design?**
(=状态机 SHADOW_ONLY→PIPELINE_AUTHORITY_CANDIDATE 迁移)
前提:Candidate-C 参考实现(离线)→C3 合取重放(v2+Phase-6 语料
合取 FU=0)→post-gate 实现验证→真实措辞证据(或 Owner 豁免)→
全回归+OFF 逐字节等价。**实现仍需独立授权。**

**OD-FIX3-27 Universal/generalization 是否纳入永久 hard safety
boundary?**
证据支持纳入(双模型皆错·语义盲区形·加固零损失);taxonomy 变更
Owner 门控——未自动升级;现行=影子前置已含范围词。

**OD-FIX3-28 R4 是否保持独立 deterministic/planning 边界?**
证据:「一般原则→个性化结论」传播已实证(BF3-01);判定永不可升
R4 类。附带生产侧发现:非数字个性化 REC 今日过确定性层(REC 豁免)
——与判定无关的 OD-H3 既有议程。

**OD-FIX3-29 是否允许 Batch-2 进入 deterministic-only 受控观察?**
(**≠判定权威·独立决策**)Mode A 证据充分(确定性栈稳定·零不安全
交付·回滚实证);Mode B(带权威)证据不充分——两模式不得互推。

**OD-FIX3-30 是否继续保持 D-08 SEALED?**
Phase1-7 全工件在案;续封=独立 Owner 动作(材料齐备)。

## 强制终态

Semantic Judge=SHADOW ONLY · Authority=NOT GRANTED · Hybrid=OFF ·
S2=UNCHANGED · Batch-2=NOT DISTRIBUTED · D-08=SEALED ·
生产代码改动=**0**。
