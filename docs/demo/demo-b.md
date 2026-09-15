# Demo B — Safe Failure Path (`bm-noev-001`)

**Purpose:** Show the agent **failing safely** instead of fabricating evidence when its knowledge
base cannot support a recommendation.

```bash
python demo.py demo-b
```

## Setup

This case is seeded with an **empty Knowledge Base**. There is no document corpus to retrieve
evidence from. The upstream client/requirement/risk stages are seeded as in Demo A; the failure is
injected at the evidence boundary.

## What the runtime does

```
Empty Knowledge Base
   → Knowledge Search returns insufficient_evidence (evidence = [])
   → product-candidate-provider Eval FAIL
   → Repair #1 (RERUN_FROM_UPSTREAM)
   → Eval FAIL (still no evidence)
   → Repair #2 (RERUN_FROM_UPSTREAM)
   → Eval FAIL (still no evidence)
   → Repair budget exhausted (max 2 repairs)
   → CASE_NEEDS_REVIEW
```

## Verified results (from the real run artifacts)

- `knowledge-evidence` artifact: `status = "insufficient_evidence"`, `evidence = []`.
- `product-candidate-provider` failed evaluation **3 times** (1 initial + 2 repairs) with the
  same root cause:
  ```
  EVIDENCE_EVAL_FAIL[EVAL-006]: required_non_empty(empty: payload.evidence);
  provenance_evidence_document_chunk(no nodes at payload.evidence[])
  ```
- Each failure triggered `REPAIR_STARTED` → `REPAIR_COMPLETED` (`action=RERUN_FROM_UPSTREAM`),
  which re-ran the upstream evidence fetch. With no corpus, the re-run could not help — and the
  system did **not** invent evidence to escape the loop.
- After the 2nd repair, the orchestrator emitted `CASE_NEEDS_REVIEW`
  (`repair_exhausted: product-candidate-provider`).
- `case_state.status = "NEEDS_REVIEW"`; **no `product-recommendation` artifact was created**,
  and therefore **no product appears in the report**.

### Excerpt from the execution trace (`trace.jsonl`)

```
SKILL_COMPLETED  coverage-gap-analysis   eval_status=PASS
SKILL_COMPLETED  solution                eval_status=PASS
TASK_FAILED      product-candidate-provider  EVAL-006 required_non_empty(empty: payload.evidence)
REPAIR_STARTED   product-candidate-provider  action=RERUN_FROM_UPSTREAM
TASK_FAILED      product-candidate-provider  EVAL-007 required_non_empty(empty: payload.evidence)
REPAIR_STARTED   product-candidate-provider  action=RERUN_FROM_UPSTREAM
TASK_FAILED      product-candidate-provider  EVAL-008 required_non_empty(empty: payload.evidence)
CASE_NEEDS_REVIEW repair_exhausted: product-candidate-provider
```

## Why this is the important demo

> The interesting behavior is **not** that the agent failed.
> The interesting behavior is that it **stopped safely** instead of fabricating a product to fill
> the gap.

A system that always "succeeds" is not reliable. A system that fails *predictably, explainably,
and without hallucination* is what an Agent Systems engineer is actually selling.
