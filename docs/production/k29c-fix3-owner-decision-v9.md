# K.29-C FIX-3 · Owner Decision Package v9

Date: 2026-10-03 · 输入:Phase 8 Candidate-C 离线运行时验证(隔离
参考实现·零生产改动·0 新 LLM 调用)。详报:k29c-fix3-phase8-
candidate-c-runtime-validation.md;证据:tmp/obs/k29c_fix3_phase8_*
(7 件)。**只提交证据·不代决策·任何内容 ≠ AUTHORITY_GRANTED。**

---

## 证据核心

- **246 例全风险面重放(v2 82+Phase-6 60+金标 104):九类
  FALSE_UPGRADE 全部=0**;六段 trace 逐条落盘。
- **四已知判定错误(F5-05/BF1-16/BF2-01/BF3-01)在 judge 被强制
  ALLOW 下全部被管线阻断**(BF3-01 由 Phase-8 新规则「类型豁免不得
  绕过硬类」拦截)。
- **13 行失败注入矩阵全过**+反证行(非永拒:全健康链放行 ✓·硬探针
  软孪生升级 ✓);P1-P6 全 PASS。
- 关键区分维持:判定层 NOT SAFE 不变;Candidate-C=完整合取链的
  **有界安全离线实证**。
- 效用如实:严格 C3 下 v2 升级=0(E 类 UNSUPPORTED 不可升)——效用
  扩张=C3 修订=Owner 设计决策。

## Owner Decisions

**OD-FIX3-31 Candidate-C 是否通过离线安全验证?**
证据:是——零逃逸+全阻断+全注入过+隔离零生产影响(上述)。

**OD-FIX3-32 是否批准进入 isolated shadow runtime validation?**
(=状态机 CANDIDATE→OWNER_REVIEW 前的影子运行时验证:把隔离实现
接入 S1' 影子旁路·对真实流量只记录 Candidate-C 决策·仍零生产
权威)。前置已含:真实措辞分布(影子流量或 Owner 豁免)+post-gate
独立组件强化(交付证据重查)+kill-switch 演练。

**OD-FIX3-33 是否继续保持裸 Semantic Judge = NOT AUTHORITY-SAFE?**
证据:维持——Phase-8 未重测判定层·Phase-5/6 四例错误仍在案;
本阶段全部安全归因于管线边界·非判定层。

**OD-FIX3-34 是否允许 Batch-2 Mode A 与 Candidate-C 独立推进?**
两轨道独立(Phase-7 已声明);Mode A 证据维持充分;Candidate-C
进度不改变 Mode A 风险面。

**OD-FIX3-35 是否保持 D-08 SEALED?**
Phase1-8 工件齐备;续封=独立 Owner 动作。

## 强制终态

Semantic Judge=SHADOW ONLY · Authority=NOT GRANTED · Hybrid=OFF ·
S2=UNCHANGED · Batch-2=NOT DISTRIBUTED · D-08=SEALED ·
生产代码改动=**0**(隔离实现于 tools/·零 runtime import)。
