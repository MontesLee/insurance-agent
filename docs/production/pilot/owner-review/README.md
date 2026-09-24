# Owner Review Workbench — Phase 27 Round 1 (C01–C12)

Generated 2026-09-23 by tools/build_owner_review.py from raw pilot
evidence (tmp/pilot27 artifacts + traces + machine-results JSON).
Baseline phase26c-productionization-v1.0 (c7ed9c6), unchanged.

# Owner Review Instructions

This document set contains MACHINE-OBSERVED EVIDENCE ONLY.

The Owner must independently review each case (C01.md … C12.md).

Do NOT infer business correctness from: Runtime PASS · Eval PASS ·
Benchmark PASS · Recommendation status · Machine summaries.

For each case, review in order:
1. Requirement — 客户真正想解决的问题是否被正确识别?
2. Risk — 主要家庭风险是否遗漏?
3. Coverage Gap — 保障缺口是否与风险对应?
4. Solution — 解决方案是否合理?
5. Product — 产品是否真的符合方案?(是否解决前面的 Gap?)
6. Evidence — 推荐结论是否有可靠 evidence?
7. Recommendation — 与 Requirement/Risk/Gap/Solution/Evidence 一致?
   primary=NONE 时:判断"证据不足不给推荐"是否符合业务预期。
8. Report — 是否准确、易懂、无遗漏、与推荐一致、无误导表述?

Record per section: judgment + reason + required change.

## Simple judgment scale

- CORRECT — 可以继续使用
- MINOR_ISSUE — 小问题,不影响继续使用
- MAJOR_ISSUE — 需明显修改后才能使用
- REJECT — 不能使用
- UNKNOWN — 现有信息不足以判断
(Product/Recommendation/Report additionally: NOT_PRODUCED)

## Review time protocol

开始一个 Case 记 review_start,结束记 review_end,差值即
review_duration_seconds;无法精确记录就写 UNKNOWN,不要估算。

## Reviewer changes

不直接修改 Agent 产物。在 Case 文件 §12 记录:
Change Type: REQUIREMENT/RISK/GAP/SOLUTION/PRODUCT/EVIDENCE/
RECOMMENDATION/REPORT/OTHER + Change Description。

## Status grid (updated only by Owner)

| Case | Requirement | Risk | Gap | Solution | Product | Evidence | Recommendation | Report | Overall |
|------|-------------|------|-----|----------|---------|----------|----------------|--------|---------|
| C01  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C02  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C03  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C04  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C05  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C06  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C07  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C08  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C09  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C10  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C11  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| C12  | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

All aggregate metrics (approval rate, review time mean/median,
change rate …) remain UNKNOWN until the Owner fills these in.
Do NOT treat unfilled entries as pass or as zero.

## Cross-case context (facts, not judgments)

- F27-01: C08 (WAITING_FOR_USER) and C11 (NEEDS_REVIEW) settled as
  Task/Run SUCCEEDED with no human gate — see
  ../f27-01-root-cause.md. Judge the OUTCOMES in §10 yourself.
- F27-02: every produced recommendation on the demo catalog is
  INCOMPLETE_EVIDENCE; primary exists on C02/C03 only; diagnostic
  A/B shows the logic produces/blocks primaries as designed — see
  ../f27-02-root-cause.md. Business adequacy is yours to judge.
- F27-03: C12 ran the full chain on an EMPTY requirement set.
- F27-04: knowledge source = fixture KB (mock), not live WeKnora.

## Owner Finding registry (OF-xx) — add rows as you review

| ID | Case | Area | Observation | Expected | Actual | Impact | Severity (Owner to confirm) |
|----|------|------|-------------|----------|--------|--------|------------------------------|
| — | — | — | — | — | — | — | — |

(New business observations go here as OF-01…; do NOT edit the
F27-* engineering findings — merging decisions come later.)

## Evidence hygiene

- EH-01: C08 has no persisted artifacts/case_state (its
  WAITING_FOR_USER payload lived only on the cleaned task row).
  Machine-results JSON + runner definition remain. Runner
  unchanged by design this round (fix belongs to round-2 tooling).
