# Failure Injection

This document describes the **adversarial failure scenarios** the runtime is explicitly tested
against. These are **runtime reliability tests**, not business scenarios. They are intentionally
hostile inputs designed to prove the agent *fails safely* rather than producing a plausible-looking
wrong answer.

The harness injects each failure, then verifies the chain:

```
Inject failure → Eval FAIL → Repair → Re-evaluate → (PASS | FAIL → retry, max 2) → NEEDS_REVIEW
```

## Scenarios (F1–F6)

| Failure | Injection | Expected Behavior |
| --- | --- | --- |
| **F1 — Schema violation** | malformed / missing-required-field artifact | Eval **FAIL**; stage blocked, never propagates |
| **F2 — Missing evidence** | empty knowledge base | Repair ×2 → **NEEDS_REVIEW** (no fabrication) |
| **F3 — Ineligible product** | impossible eligibility (e.g. age out of range) | candidate marked `ELIGIBILITY_INELIGIBLE` → `NO_CANDIDATES` / not recommended |
| **F4 — Hallucinated product** | unknown / non-catalog product ID | blocked at recommendation + report boundary; `primary = 0`, `unverified_products = []` |
| **F5 — Missing provenance** | invalid / empty `chunk_id` reference | rejected by provenance eval; claim not admitted |
| **F6 — Invalid continuation** | malformed artifact reference / tampered checkpoint | `CHECKPOINT_INVALID` / cross-artifact fail; self-heals or blocks |

## Why these matter

The benchmark's normal cases prove the agent *can* succeed. These cases prove the agent *knows when
it must not*. An agent that only demonstrates success on curated inputs has not demonstrated
reliability — it has demonstrated luck.

Each scenario is covered by:

- explicit negative cases in `evals/agent-benchmark/` (adversarial + insufficient_evidence + no_candidates families),
- guardrail assertions in `tests/workflow/test_step4_phase13_guardrails.py` (`FABRICATED_PRODUCT`, etc.),
- mutation tests in `tests/workflow/test_step3_mutation.py` (tampered artifacts, orphan refs, checkpoint tampering).

## Observed behavior (real runs)

- **F2 (bm-noev-001):** 3 evaluation failures (1 initial + 2 repairs) → `CASE_NEEDS_REVIEW`;
  knowledge-evidence `status = insufficient_evidence`, `evidence = []`; no recommendation artifact.
- **F4 (bm-adv-invalid-product):** recommendation `primary = 0`, `unverified_products = []`, report
  names no product — confirmed independently by `FABRICATED_PRODUCT` guardrails and golden case G-007.
- **F3:** ineligible candidate `C004 (P011)` reported `not_recommended` via `ELIGIBILITY_INELIGIBLE`,
  while eligible `C001 (P001)` is recommended.

> **Design stance:** the agent is not required to always succeed. It is required to **fail safely**.
