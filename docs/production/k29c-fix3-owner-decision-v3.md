# K.29-C FIX-3 · Owner Decision Package v3

Date: 2026-10-02 · 输入:Phase 1 离线验证全套证据(零生产改动完成)
详细数据:docs/production/k29c-fix3-phase1-offline-validation.md

---

## A. Benchmark v2

- **82 例·六族全覆盖·BENCHMARK_V2_FROZEN(v1.0)**
- 质量门 PASS(修正 4 项后);两审(确定性 Pass-1 + 盲标签 LLM
  Pass-2)语义一致率 **97.6%**(80/82);分歧 2 例按安全向解决
  (1 翻转 REJECT·1 保留);pass2 错误 0·重试 1。

## B. B+D(确定性候选)

| | B | D | BD |
|---|---|---|---|
| 安全(新增逃逸) | **0** | **0** | **0** |
| R3/R4 高危逃逸 | 0 | 0 | 0 |
| F4(F-1)逃逸 | 7(=基线) | **7→3** | **3** |
| 翻转(main/flash) | 2/1 | 0/0 | 2/1 |
| F3 建议接受 | 6/10 | 4/10 | 6/10 |
| 误拒(金标) | 5(=基线) | 5 | 5 |
| **硬门** | **PASS** | **PASS** | **PASS** |

定位:B=薄收益(诚实叙述解锁)·D=纵深闭合(F-1 7→3·探针实证)·
组合=安全底座。**实施=解封 claim_support(SEALED)+OD-12 三层
Gate+默认 OFF 灰度**。

## C. Semantic Judge S0(glm-5.3-flash·τ=0.7·122 调用)

| 指标 | 值 |
|---|---|
| F2 否定反转检出 | **12/12(100%)** |
| FALSE_UPGRADE(judge 单独/管线级) | 1 / **0**(硬类前置拦截) |
| HIGH_RISK_FALSE_UPGRADE(管线级) | **0** |
| F1 真改写解锁 / 泛化半真保持 | 10/10 / 11/11 |
| 不确定率 / 稳定性 | 0% / 90%(×3) |
| 延迟 / 成本 | 中位 6.5s·max 20.7s·~1.5 调用/例 |
| 组合管线投影翻转 | main 6/23·flash 5/23(上界·含 R3 两例待真实流量验证) |

限制:语料 82 小·样本与协议同源·单模型·τ 未压测。

## D. Recommendation（证据化选项·不代决策）

**Option 1 — FIX-3-IMPL(B+D 最小包生产实施)**
证据支持:零新增逃逸·F-1 7→3·探针闭合;证据反对:单独翻转仅
2/1(可用性几乎不变)。前置:解封授权+金标回归+默认 OFF。
适合:把「安全底座+纵深」先落地,为判定层铺路。

**Option 2 — S1' Semantic Shadow(完整管线形态:硬类前置+B/D
底座+判定影子·零 authority·行为逐字节不变)**
证据支持:F2 100%/F1 100%/管线假升 0·E 类是唯一 61% 主体的
解锁路径;证据反对:小语料同源·τ 未压测·R3 投影面未验·
flash 单模型。前置:观察窗与阈值冻结(OD-12 式)+影子记录
基建(loop 观测缝授权)。可与 Option 1 并行(同一解封批次)。

**Option 3 — 先补基线债(不动 B/D/C)**
证据支持:v2 暴露 13 例基线逃逸中 4 类硬安全缺口(区间单位/
范围扩展/产品身份/时点限定)——①区间单位是 FIX 级小修;
证据反对:不解锁任何可用性。适合:作为 Option 1 的附加范围
(同一 FIX-3-IMPL 内处理①·②③④另裁)。

**Option 4 — 维持现状(A)**
零成本;QA grounded 持续 0/30·Hybrid 停摆;F-1 与 13 例基线债
保持。适合:Batch-2 UAT 优先、暂缓全部判定层工作。

## E. 状态

**READY_FOR_OWNER_DECISION**
（硬门全过·BENCHMARK_V2_FROZEN·零生产改动·全部证据在
tmp/obs/k29c_fix3_*.json|jsonl·无 CANDIDATE_SAFETY_FAILURE）
