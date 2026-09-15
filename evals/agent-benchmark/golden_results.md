# Golden Cases (Step 4 · Phase 4/5)

```
==============================================================================
GOLDEN CASES — 9 cases
==============================================================================
OK  G-001   <- bm-complete-001          COMPLETED      checks=10/10
OK  G-002   <- bm-insufficient-002      WAITING_FOR_USER checks=11/11
OK  G-003   <- bm-conflict-001          WAITING_FOR_USER checks=10/10
OK  G-004   <- bm-nocand-001            COMPLETED      checks=10/10
OK  G-005   <- bm-noev-001              NEEDS_REVIEW   checks=10/10
OK  G-006   <- bm-highrisk-001          COMPLETED      checks=6/6
OK  G-007   <- bm-adv-invalid-product   NEEDS_REVIEW   checks=9/9
OK  G-008   <- bm-repair-001            COMPLETED      checks=8/8
OK  G-009   <- bm-complete-006-single-medical COMPLETED      checks=21/21
------------------------------------------------------------------------------
REGRESSION vs baseline.json (spec §14/§15)
metric                           before       after        verdict
task_success_rate                1.0          1.0          UNCHANGED
product_hallucination_rate       0.0          0.0          UNCHANGED
------------------------------------------------------------------------------
GOLDEN: 9/9 passed
RESULT: ALL GREEN
```
