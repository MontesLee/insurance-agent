# K.29-C FIX-3 · 实施计划(Phase 1.5 / Phase 6)

Date: 2026-10-02 · **无任何 Stage 已授权**——本文件仅为若 Owner 批准
后的最小执行路径。每 Stage 的 approval gate 空=未授权·不得开工。

---

## Stage A — Deterministic B+D implementation(若 OD-FIX3-1 批准)

- **scope**:claim_support.py check() 内两处插入(B 豁免过滤器·D 前提
  重判)+ rules yaml 两个默认 OFF 配置块(护栏正则外置)。零其它文件。
- **files**:`runtime/grounding/claim_support.py`(+~30 行含旗读)·
  `config/qa-grounding-rules.yaml`(+2 块)。
- **tests**:Phase 2 清单 T01-T18 中确定性子集+**OFF 等价测试**
  (双旗关=字节级现行·65-check 逐位)+全电池零新增失败。
- **evidence**:v2 冻结重放——B/D/BD 新增逃逸=0·F4 逃逸 7→3·
  F3 4→6;探针锁;金标 P/R 逐位不变。
- **rollback**:EXEMPTION_V2_ENABLED / PREMISE_SCAN_ENABLED=0(独立)。
- **approval gate**:**OD-FIX3-1+OD-FIX3-4(claim_support+rules 解封)**。
- **STOP condition**:任一硬门(新增逃逸/误拒新增/65-check 变化)
  无法归零→停·升级 Owner。

## Stage B — Baseline debt hardening(若 OD-FIX3-2 批准)

- **scope**:①单位词表补 倍/%/折(+区间右缘锚定——FIX2 同族)
  ②catalog 产品名覆盖扩展(名称解析覆盖 F5-08 形态)。范围扩展/
  时点限定**不在本 Stage**(设计债·另裁)。
- **files**:claim_support.py 锚正则区(①)·产品目录 fixture/映射(②·
  数据面为主)。
- **tests**:T10(区间)/T11(单位)/T12(身份)为验收;金标 N4 5/6→
  预期 6/6;OD12_BASELINE 的 FP=5 若变化→按 OD-12 程序更新基线
  记录(数值不自定·Owner 复核)。
- **evidence**:v2 重放 F4-08 拒·F5-08 拒;全电池。
- **rollback**:单位词表=提交级回退;catalog=数据还原。
- **approval gate**:**OD-FIX3-2(可与 OD-FIX3-1 同批)**。
- **STOP**:任何既有正例(P 族)被新词表误拒→停。

## Stage C — Regression + frozen benchmark validation

- **scope**:零新代码——Stage A/B 产出的验证阶段(v2 只读重放+
  全电池+OFF 等价+定向 R3/R4 面)。
- **files**:tests/runtime/test_fix3_*.py(新增·只读引用冻结件)。
- **tests/evidence**:见 Phase 2 清单;OD-12 Layer A/B/C 执行记录。
- **rollback**:n/a(验证阶段)。
- **approval gate**:作为 Stage A/B DoD 的组成部分(不单独授权)。
- **STOP**:golden 任何标签被提议修改→STOP(corpus-revision 另立)。

## Stage D — Offline Semantic Judge validation 扩展(若 OD-FIX3-3 批准准备)

- **scope**:S0 评测器扩展——τ 扫描(0.5-0.9)·第二模型(main 槽)
  对照·同源对抗样本的**换源再出题**(第二评审人)·硬类前置过滤器
  的离线管线级重放。
- **files**:tools/k29c_semantic_judge_s0.py 扩展或平行工具+新探针
  语料(corpus-revision 惯例)。
- **tests**:Phase 2 之 S0 六项离线测试。
- **evidence**:τ 敏感度曲线·双模型一致率·FU(pipeline)=0 复证。
- **rollback**:n/a(离线)。
- **approval gate**:**OD-FIX3-3 前半(准备)**。
- **STOP**:换源样本上 FU>0 且 τ 无法在不牺牲 F1 恢复下归零→
  如实报告·Owner 裁决。

## Stage E — S1' Shadow(若 OD-FIX3-3+5 批准实施)

- **scope**:loop.py 观测缝(_full_gate 后旁路·零行为)+影子记录器
  (独立 jsonl·预算上限)+硬类前置+B/D 底座上的判定影子。
- **files**:loop.py(仅观测)+新 runtime/grounding/shadow_judge/
  (影子模块·生产不可 import 主链)。
- **tests**:行为逐字节不变性快照;记录器隔离 grep 审计;错误坍缩
  注入;预算上限。
- **evidence**:Phase 4 指标体系全量采集(观察窗=Owner 定)。
- **rollback**:影子开关关闭=停记录;缝保留无害(或一并回退)。
- **approval gate**:**OD-FIX3-3 后半+OD-FIX3-4(loop 解封)+
  OD-FIX3-5(窗/资源)+OD-FIX3-6(HARD STOP 集)**。
- **STOP**:任一 HARD STOP(见 shadow_readiness)触发→停窗·报告。

## Stage F — Owner review

- **scope**:S1' 观察数据→决策包(是否进入任何 authority 讨论)。
- **approval gate**:Owner 全权;无自动续作。

## Stage G — 可能的 authority promotion(远期·占位)

- **scope**:仅当 F 阶段 Owner 明示——判定升级权(env 默认 OFF·
  只升非硬类·新 ADR·OD-12 式门槛·回滚=关旗)。
- **STOP**:任何阶段 R3/R4 escape>0·FU>阈值·行为不变性破坏=
  永久不授予。

---

## 依赖图

```
OD-FIX3-1/2/4 ──> Stage A+B ──> Stage C(DoD) ──┐
                                                ├─> OD-FIX3-3/5/6 ──> Stage D ──> Stage E(S1') ──> F ──> G(远期)
(Stage D 可与 A/B 并行——纯离线)               ┘
```

**再次强调:以上全部 Stage 均未授权。任何代码开工前必须 Owner
批准对应 OD-FIX3-x。**
