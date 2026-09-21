# Evaluation Showcase — Phase 20

## Test Pyramid

```text
                    ┌─────────────┐
                    │ Live WeKnora│  ← real HTTP, real governance,
                    │   (48/48)   │     real provenance on live hits
                    ├─────────────┤
                    │  Security   │  ← auth, RBAC, PII, approval,
                    │  (98/98)    │     provider policy, CORS
                    ├─────────────┤
                    │  Mutation   │  ← inject defects → evaluator
                    │  (26/26)    │     must catch (teeth proof)
                    ├─────────────┤
                    │ Business E2E│  ← 15 client cases from seed
                    │  (15/15)    │     to report through the REAL
                    ├─────────────┤     orchestrator
                    │  Integration│  ← cross-process recovery,
                    │  (51 suites)│     checkpoint, harness
                    ├─────────────┤
                    │  Contract   │  ← 11 schema files validated
                    │  (52/52)    │     on every artifact
                    ├─────────────┤
                    │    Unit     │  ← 456 pytest tests across
                    │  (456 pass) │     runtime, knowledge, adapters
                    └─────────────┘
```

## Key Metrics

| Metric | Value | What it means |
|---|---|---|
| Runtime tests | 456 PASS | All deterministic components tested |
| Portfolio tests | 12 PASS | Generalization to non-insurance domain |
| Benchmark | 42/42 | Unsupported-claim-rate = 0; repair success; hallucination detection |
| Adversarial | 42/42 | 16 knowledge + 12 agent + 8 security + 6 eval attacks |
| Mutation detection | 26/26 | Evaluator catches every injected defect |
| Security evaluation | 98/98 | Auth 9, authz 33, approval 13, PII 12, provider 6, isolation 5, retention 2, error 3, audit 2, encryption 3, auth-mutation 10 |
| Live WeKnora | 48/48 | Real retrieval + governance + provenance + failure modes |
| Full regression | 51 PASS / 0 FAIL / 1 pre-existing | 52 suites across the entire codebase |

## What the Mutation Tests Prove

The evaluator is NOT "testing itself":

```text
M01: Delete a requirement     → HG-B02 fires (evaluator catches)
M02: Fabricate a requirement  → HG-B02 fires
M03: Delete a risk            → HG-B03 fires
M04: Modify a gap             → HG-B04 fires
M05: Phantom solution         → HG-B04 fires
M06: Inject fake product      → HG-B05 fires
M07: Delete evidence refs     → HG-B06 fires
M08: Tamper the report        → HG-B12 fires
M-AUTH 01-10: Auth attacks    → all blocked (identity, rank, injection)
M-OBS 01-08: Trace attacks    → all detected (delete/forge fields)
```

If the evaluator were circular (just re-asserting what the code
produced), these mutations would PASS. They all FAIL — proving the
evaluator independently checks correctness.

## Evaluation Independence

Three structural guarantees (scanned, not just claimed):

1. Production code never imports evaluators (scanned across
   `runtime/`, `knowledge/`, `adapters/`)
2. Evaluators import production code (to test it), never the reverse
3. Live WeKnora tests hit a REAL external service (not a mock of
   themselves)

## Caveat

> These are project-level validation results, not production SLA
> or industry benchmark results. The system has not been deployed
> to real customers at scale. Token cost is NOT_MEASURABLE
> (the deterministic path makes 0 LLM calls). Production latency
> has not been measured under realistic load.
