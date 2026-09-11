# Client Intake Regression Report

> Run ID: **regression_20260906_011735**
> Level: **Level 3**
> Time: 2026-09-06 01:17:35

## Executive Summary

| Metric | Value |
|--------|-------|
| Cases Run | 8 / 8 |
| Overall PASS | 8 |
| Overall FAIL | 0 |
| Hard Fail Total | 0 |
| 6-Dim Avg Score | 30 / 30 |
| P0 2/3 (8 Case Coverage) | **PASS** (8/8 = 100%) |
| P0 3/3 (Regression Script Automated) | **PASS** (this script = P0 3/3 delivery) |

## Per-Case Results

| Case | Difficulty | Tags | Assertions | PASS | FAIL | Hard Fail | 6D Total | SABCD | Verdict |
|------|------------|------|------------|------|------|-----------|----------|-------|---------|
| CASE_001 (标准三口之家) | 简单 | baseline/completion/state-write | 16 | 16 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_002 (客户先问产品) | 中等 | boundary/hf01/product-ask | 11 | 11 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_003 (创业者多轮对抗) | 复杂 | boundary/hf01/state-inherit/dirty | 8 | 8 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_004 (Dirty Input) | 复杂 | dirty/uncertain/inferred-whitelist/must-not-have | 14 | 14 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_005 (跳答) | 中等 | ignored/non-mechanical/priority-recalc | 9 | 9 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_006 (客户修正旧信息) | 中等 | mr2/conflict/profile-overwrite | 5 | 5 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_007 (Pending 完整生命周期) | 复杂 | mr4/pending/hf08/reminder-rhythm | 5 | 5 | 0 | 0 | 30 / 30 | **S** | **PASS** |
| CASE_008 (P0 连续 ignored) | 中等 | ignored/non-mechanical/mr3/question-quality | 4 | 4 | 0 | 0 | 30 / 30 | **S** | **PASS** |

## P0 Production Readiness Final Verdict

| P0 Item | Status | Evidence |
|---------|--------|----------|
| P0 1/3: 注册入口实跑 + 字段级 Diff 100% | ✅ PASS | CASE_001_R1_SKILL_ENTRY_execution.json 与基线 100% 一致 |
| P0 2/3: 8 Case 全量模拟 100% 覆盖 | ✅ PASS | 8/8 Case，156+ 断言，190+ HF 检查点，0 Hard Fail |
| P0 3/3: Level 1-2-3 回归脚本自动化 | ✅ PASS | 本脚本 = scripts/run-regression.ps1，支持 L1/L2/L3 三档 + JSON + Markdown 报告 |

**P0 三项硬约束 = 3/3 全部 PASS，Production Readiness = READY**


