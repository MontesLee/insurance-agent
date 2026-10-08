# K.29-C FIX-3 · S1' Shadow Activation Readiness（Phase 8·未启动）

Date: 2026-10-02 · OD-FIX3-3 GATE:本文件仅为就绪声明——**真实 Shadow
未启动**（启动需 Phase 2 全过后另获 Owner 批准+OD-FIX3-5 资源）。

## Activation Prerequisites（逐项状态)

| # | 前置 | 状态 | 证据 |
|---|---|---|---|
| 1 | B+D regression PASS | **DONE** | test_fix3_bd.py 25/25;全电池 895+2 |
| 2 | Frozen Benchmark PASS | **DONE** | k29c_fix3_phase5_validation.json:三臂 HARD_GATE=PASS(候选新增逃逸=0·D 关闭 5) |
| 3 | HIGH_RISK_FALSE_UPGRADE=0 | **DONE(离线)** | S0:judge 单独 1 例=硬类日期→管线级(前置过滤)0;生产判定层不产生 upgrade(B/D 皆确定性) |
| 4 | R3 escape=0 | **DONE(离线)** | v2 F5 面 0 新增+T17+四臂 benchmark 重放 0 高危新增 |
| 5 | R4 escape=0 | **DONE(离线)** | T18:金额面 C1/B 基线 F-1 由 D 关闭;路由面=OD-H3 依赖(注明) |
| 6 | numeric escape=0 | **DONE** | 验证 JSON gates.numeric_escape=0(三臂) |
| 7 | contradiction escape=0 | **DONE** | gates.contradiction_escape=0 |
| 8 | product identity escape=0 | **DONE** | F5-08/N4-3 关闭(金标唯一 delta=该修复) |
| 9 | date/time escape=0 | **DONE** | F6-08 关闭+日期整串感知(T13) |
| 10 | production owner authorization | **PENDING** | 本文件待 Owner 批准 |
| 11 | resource/budget approval | **PENDING** | OD-FIX3-5 未批(模型槽位/窗口/成本) |

## Shadow Metrics Schema（已实现于 runtime/grounding/shadow_judge.py）

- **SAFETY**: high_risk_false_upgrade / r3_r4 / numeric / contradiction /
  product / date_time（OD-FIX3-6 五项=HARD STOP 零阈值）
- **QUALITY**: true_paraphrase_recovery / false_refusal_reduction /
  partial_truth / generalization
- **JUDGE**: ALLOW_UPGRADE / KEEP_BASELINE / UNCERTAIN 分布
- **OPS**: p50/p95 latency / timeout / malformed / model_error /
  cost_per_1k / stability

## 观测缝状态

loop.py `shadow_observer=None`(默认无操作·test_fix3_bd seam 测试证明
双恒定:观察者异常不改答案·None 时零路径);`SemanticJudgeClient`
错误坍缩全类→KEEP_BASELINE(test 锁定);shadow_judge 模块不被 loop
或任何生产门 import(结构性隔离)。

## 启动时将需要的后续 Owner 决策

①OD-FIX3-5:judge 模型槽位(建议候选:qa 槽 glm-5.3-flash——S0 即
此档)·观察窗时长·每 run 候选预算·成本上限;②S1' 观察记录的存放
与审计访问;③若窗口数据全绿,是否进入 S2 门槛讨论(另立决策)。
