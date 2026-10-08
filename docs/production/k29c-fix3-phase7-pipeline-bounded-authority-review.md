# K.29-C FIX-3 Phase 7 · Pipeline-Bounded Authority Design Review

Date: 2026-10-03 · Mode: **DESIGN/AUDIT ONLY**(零生产改动·零代码·
authority 未授予)·终态:**PIPELINE_AUTHORITY_DESIGN_READY**(≠GRANTED)

---

## 0. 冻结态确认

全部一致::8123 灰度+加固影子 LIVE·commit e1aba0e·生产 mtime 未变·
authority 未授予·Hybrid OFF·S2 未变·Batch-2 未分发·D-08 SEALED。

## 1. 核心问题:Authority 到底授权给谁?

### Candidate A — 裸 Semantic Judge

**`NOT AUTHORITY-SAFE`(结论不模糊)**。Phase-5/6 证据:两个独立高
置信判定错误恰好落在最高危类——F5-05(元数据日期外知渗漏·conf
0.9·3/3)与 BF1-16(区间-点值混同·conf 0.97);BF2-01(全称泛化·
conf 0.8·双模型皆错)与 BF3-01(一般原则→个性化混同·conf 0.8)。
错误为漂移依赖且 **τ 不敏感**——采样与阈值都消不掉。一个以 0.9+
置信度在高危类上犯错的组件不能对这些类持单边权威。

### Candidate B — 纯确定性管线

覆盖:Phase-2 债硬化后高危类确定性拦截(N4-3 关闭·区间/单位/日期/
产品身份·金标 104 = 103/104 同);v2+live 观察零逃逸。**已知盲区**
(如实·非形式证明):E 类假拒(61% 失败=效用缺口)·词法假支持残余
(F1-13/16·F2-05=11 例)·范围扩展(F5-13)·时点限定(F6-08)·
**非数字个性化 REC 过 REC 类型豁免(生产侧缺口→OD-H3)**。「未观察
到逃逸」≠「证明安全」。

### Candidate C — 管线有界语义判定(本阶段定义)

```
Claim → 硬类前置(确定性终局)
      → 确定性 Claim Support(baseline)
      → [仅 baseline=PARTIAL∧cited∧prefilter PASS]
        → Semantic Judge
      → 终局硬安全门(post-gate·对升级后 claim 重扫硬类)
      → 终局决定
```

**C1(判定永不可单独升级的类)**:numeric/product/regulatory/payment/
date-time/contradiction/universal-generalization/personalization(R4)
——全部硬类;任何 UNCERTAIN;evidence-meta prose(watch)。
**C2(必须在判定前确定性拦截)**:Phase-6 加固前置全集(数字·P0xx·
产品名·监管词·赔付承诺·施行/生效·范围词·个性化词)——60 例专项
语料 0 绕过+零 SAFE 损失已验证;**未来任何日期变形无数字(「去年/
月底」)须先扩前置**(设计要求 D-C2.1)。
**C3(升级合取条件)**:baseline=PARTIAL∧cited **AND** 前置 PASS
**AND** 风险边界 PASS **AND** 判定 ALLOW **AND** post-gate PASS。
**逐组件有证据**(Phase-4 live 74 ALLOW 审计=73 SAFE+1 已裁;前置
0 绕过;判定 ALLOW 分布)——**合取整体与 post-gate 组件=NOT
VERIFIED(无集成运行时;Candidate-C 参考实现+重放为下一阶段前置)**。

## 2. 不可协商安全不变量(INV-1..6)

见 `tmp/obs/k29c_fix3_phase7_invariants.json`(每条附 Phase-1..6
证据引证与执行机制):INV-1 高危+硬类不确定性不得因 ALLOW 直升·
INV-2 五硬类必过确定性边界·INV-3 R4 一般证据≠个性化充分证据·
INV-4 子集证据≠全称断言·INV-5 判定任何失败坍缩 KEEP·INV-6 任何
前置绕过=Authority FAIL。

## 3. 权威边界矩阵(12 claim 类)

见 `tmp/obs/k29c_fix3_phase7_authority_boundary_matrix.json`。
摘要:唯一可升级类=**factual paraphrase(仅 C3 合取内)**;其余 11
类=deterministic-only / deterministic+判定否决(矛盾)/deterministic
豁免(程序建议)。NOT_VERIFIED 单列:C3 合取运行时·post-gate 组件·
真实用户措辞分布(Batch-2 依赖)。

## 4. 三阻断项终局回答(不模糊)

- **BF-1**:**是——F5-05/BF1-16 证明裸判定不应成为 Authority**
  (双独立高置信错误于高危类·漂移依赖·τ 不敏感)。残余:无数字
  日期变形须先扩前置。
- **BF-2**:证据支持「所有」类**升级为永久 hard class**(双模型皆
  错·语义盲区形·加固零损失)——但 taxonomy 变更 Owner 门控→
  **仅提交 OD-FIX3-27·未自动升级**;在此之前影子前置已含范围词。
- **BF-3**:**是——R4 必须保持 deterministic/planning 边界**:
  「一般原则→个性化结论」传播路径已被实证命中(BF3-01·conf 0.8);
  语义层无用户模型证据可接地此类推断·判定永不可升级 R4 类。
  生产侧:非数字个性化 REC 今日过确定性层(REC 豁免)=OD-H3 议程。

## 5. Batch-2 边界(Mode A ≠ Mode B)

**两个独立决策·不得互推**:Mode A(确定性-only Batch-2)证据
**充分**(确定性栈稳定·79 live 轮零不安全交付·回滚实证·拒答=安全
正确先例);Mode B(带判定权威的 Batch-2)证据**不充分**(依赖
CONTROLLED_AUTHORITY 整链)。A 不因 B 不过而 unsafe;A 安全不推 B
安全。

## 6. 权威状态机

`SHADOW_ONLY → PIPELINE_AUTHORITY_CANDIDATE → OWNER_REVIEW →
CONTROLLED_AUTHORITY → FULL_AUTHORITY`(全表+每迁移前置/证据/硬停/
回滚/Owner 批准见 state_machine.json)。**SHADOW_ONLY→AUTHORITY
直接迁移不存在(构造性禁止)**——裸判定 FU 证据即其原因。

## 7. 回滚设计

七失败模式(判定失败/前置失败·绕过/post-gate 失败/端点失败/超时/
畸形/意外高危 ALLOW/预算超限)全部坍缩 KEEP_BASELINE(claim 级)与
确定性基线(系统级);权威旗 OFF=逐字节基线(Phase-3 A/B 先例)。
已验证 vs 设计待验证分列(rollback_matrix.json)——同步权威路径
超时坍缩·post-gate·前置构造级 fail-closed·授权下 kill-switch 演练
= Candidate-C 实现阶段前置。

## 8. 治理规则(写入·对历史 sealed 文档只审计不修改)

1. **判定层的语义正确性 ≠ 生产权威安全性。**
2. **管线级安全不蕴含判定级安全。**(Phase-6 已按此执行:管线 PASS
   未改写判定单独 FAIL。)
3. **Authority 只能授予经安全边界约束的完整决策链·绝不授予单个
   模型组件。**

审计:历史文档无相反表述(D-04/K.29 报告始终以 fail-closed 与
分层为前提);本阶段首次明文化。

## 9. 工件与零改动

5 JSON(invariants/boundary_matrix/blocker_mapping/state_machine/
rollback_matrix)+ 本报告 + OD v8 + checkpoint。**生产代码改动=0**
(仅 docs/tmp 产出;:8123 栈未触碰)。

## 10. 终态

**PIPELINE_AUTHORITY_DESIGN_READY**——存在一个可被 Owner 审议的
Pipeline-Bounded Authority 形态(Candidate C·C1/C2/C3 全定义·
INV-1..6 冻结·状态机含构造性禁止直接授权);其实现与验证=
后续独立阶段(见状态机迁移前置)。**绝不表示 AUTHORITY_GRANTED。**
