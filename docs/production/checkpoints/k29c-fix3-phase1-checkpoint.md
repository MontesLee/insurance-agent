# K.29-C FIX-3 Phase 1 · Offline Validation — Checkpoint

## Phase 1 + 1.5 (2026-10-02)
- status: COMPLETE
- artifacts: tests/golden/k29c_fix3_benchmark_v2.jsonl (82 cases) +
  tools/k29c_gen_v2_corpus.py + tools/k29c_fix3_quality_gate.py
- evidence: tmp/obs/k29c_fix3_benchmark_v2_quality.json =
  **QUALITY_GATE PASS**(issues=[]·F1 21[10 真/6 泛化/5 半真]·F2 12
  [neg 5/dir 3/cond 4 含 value]·F3 10·F4 13[sourced3/unsourced4/
  trap2/range1/unit1/hidden2 含半据]·F5 16[verbatim5/identity2/
  meta-pin1/adversarial8]·F6 10[consistent3/anchor3/version1/
  window1/qualitative2])
- 修正历史:首轮 FAIL(dup-claim×3+f4-no-number×1)→generator 差异化
  F6 同文 claim+gate 规则精确化(norm 保数字·dedupe claim+evidence·
  F4 隐藏前提豁免数字必含)→PASS
- next: Phase 2 两审(Pass-1 确定性首评·Pass-2 LLM 独立二审)→
  frozen.jsonl + BENCHMARK_V2_FROZEN
- blockers: 无

## Phase 2 (2026-10-02)
- status: COMPLETE — **BENCHMARK_V2_FROZEN**
- artifacts: tmp/obs/k29c_fix3_benchmark_v2_review.jsonl (82 逐例) +
  tests/golden/k29c_fix3_benchmark_v2_frozen.jsonl (v1.0) +
  tools/k29c_fix3_review.py
- evidence: Pass-1=确定性生产影子判定;Pass-2=真实 LLM 独立二审
  (glm-5.3-flash·盲标签);**语义一致率 97.6%(80/82)**;真分歧 2:
  F1-11(二审漏检「所有」泛化→按安全向保 REJECT·**LLM judge 范围词
  盲区数据点**)·F4-05(二审正确指出证据是事实描述非「建议」→
  翻转 REJECT·flips=1);pass2_error=0·retries=1(重试纪律内)。
  统计修正:首轮 61「分歧」为字符串口径 bug(REFUSE≠REJECT)·
  语义级重算后如上(frozen meta 已修正)。
- next: Phase 3 四臂模拟(C1/B/D/B+D×5 数据面)
- blockers: 无

## Phase 3 (2026-10-02)
- status: COMPLETE
- artifacts: tools/k29c_fix3_simulation.py +
  tmp/obs/k29c_fix3_simulation.json(四臂×5面全量)
- evidence(核心):
  - 金标 104:四臂 escape 全=1(N4-3 既有)·false_refusal 全=5 →
    **候选零新增逃逸·零新增误拒**;
  - v2 82:**C1 基线自身 13 例逃逸**(F1-13/16 词法假支持·F2-05
    方向翻转盲区·F4×7=F-1 量化·F5-08 产品身份·F5-13 范围扩展·
    F6-08 时点语义);**B=13(零新增·F3 接受 4→6)**;**D=9
    (关闭 4 例 F-1·F4 7→3·残余=前提在证据 05/13+区间单位缺口 08)**;
    BD=B∪D 最优;
  - benchmark 翻转:B/BD=main 2(R2-06/R4-03)·flash 1(R0-01);
    D=0;新过 claim 高危=flash 1 regulatory(R0 泛知识·非 R3/R4);
    R4-03 翻转=纯 guidance 交付(0 数字)·路由级观察(OD-H3 依赖);
  - 硬门判定(候选新增口径):new escape=0·R3/R4 高危=0·F2 新增=0·
    F4 数字新增=0 → **B/D/BD 全过**;
  - 探针 7:P-C3-02(建议3-5倍)C1/B 过·**D/BD 拒**(F-1 闭合实证)·
    P-C4-03 ws 正例四臂全拒(C4 不在臂内·如实);
  - **新硬安全缺口候选(Phase6-Q5 素材)**:①倍/区间不在锚单位表
    (F4-08)②范围扩展重疾→轻症(F5-13)③产品文本vs证据product_id
    (F5-08=N4-3 同型)④时点限定「2023年的」超出 as-of 模型(F6-08)。
- next: Phase 4 语义判定 S0(离线评测器·真实 LLM·~120 调用)
- blockers: 无

## Phase 4 (2026-10-02)
- status: COMPLETE
- artifacts: tools/k29c_semantic_judge_s0.py +
  tmp/obs/k29c_fix3_semantic_judge_s0.json(82 例逐案+稳定性子集)
- evidence(glm-5.3-flash·τ=0.7·122 调用·0 重试):
  决策分布 ALLOW_UPGRADE 23/KEEP_BASELINE 59/UNCERTAIN 0;
  **F2 反转检出 12/12=100%**(确定性层盲区的否定翻转全部捕获);
  **FALSE_UPGRADE=1**(F5-05 硬类日期案=数字+监管——恰证明设计 §1
  硬类前置过滤的必要性:管线级假升=0);F1 真改写解锁 10/10·
  F1 泛化/半真保持 11/11;F4 升级=恰 2 个 gold-ACCEPT;稳定性
  90%(18/20×3);延迟中位 6.5s max 20.7s。
- 限制:语料 82 小·对抗样本与判定协议同源(自洽风险)·单模型·
  τ 未压测(UNCERTAIN 0%)。
- next: Phase 5 矩阵+Phase 6 架构评审+Phase 7 决策包
- blockers: 无

## Phase 5 (2026-10-02)
- 统一矩阵+投影完成(见主报告):B/D 实测(翻转 2/1·0/0·新逃逸 0);
  判定实测(F1 10/10·F2 12/12·FU 1=硬类);组合管线投影 6/5
  (含 R3-03/08=判定将做实际蕴含裁决·硬类过滤依赖 claim 文本标记
  的限制如实)。

## Phase 6-8 (2026-10-02)
- status: **FIX-3 Phase 1 COMPLETE — READY_FOR_OWNER_DECISION**
- artifacts: 主报告 k29c-fix3-phase1-offline-validation.md(§A-F
  含 Phase5 统一矩阵+Phase6 架构评审 Q1-Q5)+ 决策包
  k29c-fix3-owner-decision-v3.md(Option 1-4 证据化·不代决策)。
- Q1=B+D 值得(定位纵深+薄收益·需解封);Q2=判定有条件满足
  (S1' 须完整管线形态:硬类前置必须);Q3=错误集中 F5 硬类/时点;
  Q4=人工二审收窄至硬类/时点/同源再出题/τ 边界;Q5=四类新硬安全
  缺口钉住(区间单位/范围扩展/产品身份/时点限定)。
- 最终态:READY_FOR_OWNER_DECISION·零生产改动·全部红线保持。
- **STOP——等待 Owner 决策。**
