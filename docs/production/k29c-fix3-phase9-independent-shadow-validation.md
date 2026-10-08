# K.29-C FIX-3 Phase 9 · Candidate-C Independent Shadow Runtime Validation

Date: 2026-10-03 · Mode: **SHADOW-ONLY RUNTIME VALIDATION**(
独立 post-gate 实现+变异电池+扩展注入+live 影子腿·生产代码零改动)
终态:**PIPELINE_AUTHORITY_EVIDENCE_READY**(≠AUTHORITY_GRANTED)

---

## 0. 冻结态

全部一致后执行(:8123 灰度+影子 LIVE·生产 mtime 未变·authority
未授予·Hybrid OFF·S2 未变·Batch-2 未分发·D-08 SEALED)。

## 1. Independent Post-Gate(`tools/k29c_fix3_independent_postgate.py`)

**独立契约**:仅读 raw claim+raw evidence+risk class+candidate 旗
——不复用判定结果/前置内部决定/前序归一化/同一支持判定。五项
独立重查:PG-1 硬模式(自编译正则)·PG-2 引用闭包([E#]≤证据数)·
PG-3 数字闭包(裸值+单位·边界感知)·PG-4 产品身份(裸名变体)·
PG-5 证据存在。**fail-closed 契约**:异常/缺失元数据→FAIL。

## 2. Independence Tests I1-I4:7/7 PASS

I1 管线上下文无关(硬 claim 仅凭 raw 即 FAIL;软 claim 过)·
I2 判定输出无关(API 无判定参数·三种模拟判定态结果同一)·
I3 归一化独立(空白变体同判)·I4 元数据缺失/损坏/引用越界全
fail-closed。**两项独立否决新增生效**:数字闭包(「等待期90天」
值不在证据→拒)与引用闭包([E3]>证据数→拒)——post-gate 现具有
前置层不存在的独立拦截能力。

## 3. Adversarial Mutation:4 阻断×5 变异=20/20 contained

judge 强制 ALLOW·baseline 扰动·引用元数据变异([E7])·证据重排·
措辞变异——四案全部 KEEP(阻断段稳定:baseline/contradicted/
prefilter-exempt-hardclass)。**Candidate-C 不依赖任何偶然字段或
前序实现细节。**

## 4. Extended Failure Injection:9/9 PASS·fail_open=0

新增 post-gate FAIL/TIMEOUT/MALFORMED/UNAVAILABLE 四注入全部
→ KEEP(**绝无 unavailable→fallback-to-judge-ALLOW**);回归
judge-REJECT/UNCERTAIN 维持。负控:独立 post-gate 全健康链→
**ALLOW_UPGRADE**(非「永远拒绝」·utility 保底)。

## 5-6. Live Shadow Runtime+生产等价(§9-10)

- 部署形态:Candidate-C 影子腿挂 ops 启动器 drain 线程(
  `k29c_fix3_phase9_leg.py`·tools 路径修复一次·前 111 条
  ModuleNotFoundError 记录如实保留后被修复运行取代)。
- **live 窗口 10 轮真实栈流量**(12-87s 真时延):82 条 claim 级
  ledger(`k29c_fix3_phase9_shadow_ledger.jsonl`·含
  run/claim/risk/baseline/judge/candidate_c/post_gate/final_shadow/
  production_final 全字段)。
- **等价统计**:same(both-refuse)=34·c-baseline-pass(prod-refused)
  =48(逐 claim 通过位于整答案被拒内=claim 级 vs 答案级·非矛盾)·
  **upgrade=0·unexpected=0·高危升级=0**;生产答案全部与
  Phase-3/4 栈同模板(逐字)——影子腿零生产影响实证。

## 7. Safety Gates(§11)

九类 FALSE_UPGRADE=0 + POST_GATE_{FAIL_OPEN,TIMEOUT_ALLOW,
MALFORMED_ALLOW,UNAVAILABLE_ALLOW}=0——**全零**。

## 8. Independence Matrix(§12·Phase-9 独立重测·不复制 Phase-8)

| Property | Phase 8 | Phase 9 |
|---|---|---|
| hard prefilter safety | PASS | **PASS**(变异 20/20+live 零升级) |
| risk boundary safety | PASS | **PASS** |
| Judge fail-closed | PASS | **PASS**(重注) |
| **post-gate independence** | NOT_VERIFIED | **PASS**(I1-I4 7/7+两项新独立否决) |
| **post-gate fail-closed** | — | **PASS**(4/4 注入·fail_open=0) |
| known blocker containment | PASS | **PASS**(5 变异/案·更严) |
| negative control | PASS | **PASS**(独立 PG 版) |
| **runtime shadow isolation** | — | **PASS**(live 22 轮生产逐字不变) |
| **production equivalence** | — | **PASS**(82 ledger·upgrade 0·unexpected 0) |
| rollback | PASS/design | **PASS**(腿=启动器行·删除+重启) |

## 9. Batch-2 边界(§14)

Mode A(确定性-only)与 Mode B(Candidate-C/判定权威):独立流量/
指标/批准/回滚——**禁止混合**(本阶段未启动任何模式)。

## 10. Authority Boundary(§13)

**PIPELINE_AUTHORITY_EVIDENCE_READY**——判定层仍 NOT SAFE;含
**独立 post-gate** 的 Candidate-C 完整链的有界安全性已获离线+
live 影子双实证。**≠AUTHORITY_GRANTED。**

## 工件

6 件(postgate_independence/mutation/failure_injection/shadow_
ledger/equivalence/authority_matrix)+ 本报告 + OD v10 + checkpoint;
bug 修复史如实(helper 顺序·tools 路径)。

## 终态(强制)

Semantic Judge=SHADOW ONLY·Authority=NOT GRANTED·Hybrid=OFF·
S2=UNCHANGED·Batch-2=NOT DISTRIBUTED·D-08=SEALED·生产改动=**0**
(ops 腿+隔离件)。
