# K.29-C FIX-3 Phase 8 — Candidate-C Runtime Validation · Checkpoint

## COMPLETE (2026-10-03·ISOLATED·零生产改动·0 新 LLM 调用)
- 隔离参考实现 tools/k29c_fix3_candidate_c.py(严格 C3 合取+Phase-8
  新规则:类型豁免不得绕过硬类);运行器 tools/k29c_fix3_phase8_run.py。
- 246 例重放(v2 82+p6 60+金标 104):九类 FU **全部 0**;六段 trace
  全落盘;唯一 ALLOW=BF2-12 对照件(设计内正确)。
- 四已知错误(judge 强制 ALLOW)全阻断:F5-05@baseline·BF1-16@
  contradicted·BF2-01@baseline·BF3-01@prefilter-exempt-hardclass。
- 13 行失败注入矩阵全过+反证行(control/soft-twin);P1-P6 全 PASS;
  19 项就绪矩阵全 PASS(post-gate 独立性注记)。
- 关键区分维持:判定层 NOT SAFE 不变;Candidate-C=合取链有界安全
  离线实证。效用如实:严格 C3 下 v2 升级 0(E 类不可升=C3 修订议题)。
- 调试修正史(留痕):trace jsonl/array 混读×2·BF3-01 baseline-pass
  发现→新规则·FU 对照语义修正。
- 回归 895+2 零失败;生产改动=0(grep 零 runtime import)。
- 报告 phase8-candidate-c-runtime-validation.md + OD v9
  (OD-FIX3-31..35)。
- **终态:CANDIDATE_C_EVIDENCE_READY(≠GRANTED)。STOP。**
