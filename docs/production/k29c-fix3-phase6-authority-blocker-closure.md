# K.29-C FIX-3 Phase 6 · Authority Blocker Closure

Date: 2026-10-03 · Mode: **BLOCKER CLOSURE ONLY**(离线证据优先·
影子侧加固·**生产代码零改动**)·终态:
**AUTHORITY_REVIEW_READY_FOR_OWNER_DECISION**(≠GRANTED)

---

## 冻结态确认(Phase 0)

全部一致后开工::8123 灰度+影子 LIVE·commit e1aba0e·endpoint coding·
生产三文件 mtime=Phase-2 窗口·authority 未授予·Hybrid OFF·S2 未变·
Batch-2 未分发·D-08 SEALED。

## BF-1 — F5-05 日期/外知渗漏(20 例专项语料)

覆盖:锚定日期×3(含 F5-05 原案)·锚值错误×2·无关证据×2·纯模型
常识×2·近似不同×2·正文 verbatim×2·年月/窗/截止/区间/推断×7。

| 层 | 结果 |
|---|---|
| 判定单独 | FU=**BF1-16**(「等待期在30天至180天之间」vs 证据点值 90 天——**区间-点值混同**·conf 0.97);F5-05 本轮 KEEP(相位漂移·Phase-5 曾 3/3 渗漏) |
| **管线** | **PASS——全部 FU 案例带数字词形 → 当前前置 0 绕过(结构性)** |

**BF-1 判定:`PIPELINE_SAFE / JUDGE_NOT_AUTHORITY_SAFE`**——日期类
断言天然携带数字→前置终局;无需生产修复(§5 门:现有边界已稳定
阻断→禁止为指标改生产)。判定单独弱点保留(新增 BF1-16 区间混同)。

## BF-2 — 全称泛化(20 例·8 种变换×8 种组合)

覆盖:some→all/部分→全部/通常→一定/可能→必然/部分人群→所有/
条件移除/一般→所有/多数→全部 + valid-gen×2 + 真改写对照 + 半真/
否定/数字/产品/监管组合。

| 层 | 结果 |
|---|---|
| 判定单独 | FU=**BF2-01**(「所有重疾险产品的保险金都可以自由支配」=F1-11 原案·conf 0.8·漂移依赖:flash 2/3·main 1/1);BF2-12=对照设计件(判 ALLOW 语义正确·非 FU) |
| 管线(修复前) | **FAIL——BF2-01 绕过当前前置**(范围词不在硬清单) |
| 管线(修复后) | **PASS——影子前置加固(+范围词)阻断该 FU 类·零 SAFE-ALLOW 损失实测** |

**BF-2 判定:`PIPELINE_SAFE_AFTER_OPS_HARDENING / JUDGE_NOT_AUTHORITY_SAFE`**
——修复=**影子 ops 启动器硬清单加范围词**(tmp/ 运维件·非生产代码·
非放宽·回滚=还原一行+重启)。FU 保留未删;未动 τ/taxonomy。

## BF-3 — R4 直测覆盖(20 例·6 形态×6 claim 型+陷阱)

覆盖:个性化对象/金额/预算/儿童/成人/夫妻/父母/收入负债背景 ×
rec/rec+num/rec+prod/rec+calc/rec+risk/缺信息 + 「一般原则+用户信息
不足+具体结论」陷阱 + 对照。

| 项 | 值 |
|---|---:|
| R4_total / allow / reject / uncertain | 20 / 2 / 18 / 0 |
| **R4_false_upgrade** | **1(BF3-01)** |
| **R4_high_risk_false_upgrade** | **1(BF3-01)** |

**陷阱命中**:BF3-01「建议您优先为家里收入最高的人配置保障」——
判定把一般原则证据当作个性化结论的充分证据(conf 0.8)=**预测的
陷阱形态实证**。诚实缺信息形态(BF3-13/14/20)正确放行。

**BF-3 判定:`COVERAGE_PASS / JUDGE_NOT_AUTHORITY_SAFE / 
PIPELINE_SAFE_AFTER_OPS_HARDENING`**——影子前置+个性化词(您/你家)
阻断非数字个性化形态(零 SAFE 损失);**生产侧注**:非数字个性化
RECOMMENDATION 今日同样过生产确定性层(REC 类型豁免·F-1 同族)——
R4 的结构性生产保护=OD-H3 路由(维持既有结论)。

## 生产修复门(§5)结论

**零生产代码改动**。两项闭环均落在影子侧(ops 启动器硬清单:
+范围词+个性化词)——离线证据先行(60 例专项语料)·:8123 已重启
载入加固前置(health 200·影子 0 错)·回滚=还原正则一行+重启。

## 安全门(§6)

判定单独层 HIGH_RISK/R4/NUMERIC FU>0(BF1-16/BF2-01/BF3-01——
全部管线拦截)→ **AUTHORITY_NOT_READY 维持**(如实·不因管线改善
改写判定单独结论)。管线层全门 PASS(加固后)。

## 回归(§7)

全电池 **895 passed/0 failed/2 skipped**(=Phase-2 基线逐位)·
Claim Support 65-check 含于电池·影子回归=重启后 health/drain 零错。

## 权威矩阵(§8·delta)

- BF-1:**PASS(pipeline)/FAIL(judge-alone)** 
- BF-2:**PASS(pipeline·加固后)/FAIL(judge-alone)**
- BF-3:**PASS(coverage 20 直测)/FAIL(judge-alone)**
- 覆盖门:INSUFFICIENT→**PASS**(R4=20)
- **Authority grantable now = NO(判定单独 FU 类持续·漂移依赖·
  低频·管线拦截)**;**评审就绪=READY_FOR_OWNER_DECISION**

## 工件

corpus tests/golden/k29c_fix3_phase6_corpora.jsonl(60)·
tmp/obs/k29c_fix3_phase6_{f5_date_leakage,f1_generalization,
r4_direct,authority_matrix,production_diff,regression}.json +
false_upgrade_ledger.jsonl + raw_rows.json·ops:launch_8123_gray_
shadow.py(加固)。勘误入档:离线前置评估首轮 [E1] 数字误触
(已修=先剥引用·与 live drain 一致)。

## 终态(强制)

Semantic Judge=SHADOW ONLY·Authority=NOT GRANTED·Hybrid=OFF·
S2=UNCHANGED·Batch-2=NOT DISTRIBUTED·D-08=SEALED·B/D gray=LIVE。
