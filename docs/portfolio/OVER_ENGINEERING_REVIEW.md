# Over-Engineering Review — Phase 19

Honest analysis: what is essential, what is defensive, what is
portfolio showcase. No code changes — analysis only.

## Classification Framework

- **ESSENTIAL**: without it, the core proposition fails
- **RELIABILITY**: needed for crash/recovery guarantees
- **SECURITY**: needed for the fail-closed posture
- **EVALUATION**: needed to prove the system didn't cheat
- **SHOWCASE**: primarily demonstrates capability, not daily need
- **MVP-REMOVABLE**: a leaner version would skip it
- **PRODUCTION-NEEDED**: only matters at scale

## Component Analysis

| Component | Classification | MVP? | Justification |
|---|---|---|---|
| Skill decomposition (9 skills) | ESSENTIAL | Keep | Without boundaries, no provenance chain |
| Orchestrator (YAML-driven) | ESSENTIAL | Keep | Without it, no ordering/freeze/eval proof |
| Canonical Client State (5-state) | ESSENTIAL | Keep | Solves fact drift — the core problem |
| Deterministic eval engine | ESSENTIAL | Keep | "No cheating" proof |
| Artifact registry + fingerprints | ESSENTIAL | Keep | Tamper detection + lineage |
| Checkpoint recovery | RELIABILITY | Keep | Crash resilience is a claim |
| Bounded parallel scheduler | RELIABILITY | Simplify in MVP | Single-thread is sufficient for demo |
| Dynamic replanning | RELIABILITY | Keep | Real failure mode |
| HITL approval gateway | SECURITY | Keep | Insurance domain requires human gate |
| HOTL control plane | RELIABILITY | **SHOWCASE** | Used in demos, NOT in the business chain |
| Backup/restore/retention | SECURITY | Production-needed | Not needed for MVP demo |
| Knowledge governance (9 rules) | SECURITY + ESSENTIAL | Keep | The core contribution |
| Evidence + citation tuple | ESSENTIAL | Keep | Without it, recommendations aren't traceable |
| Provenance (P001-P010) | ESSENTIAL | Keep | The audit story |
| **Multiple evaluators (6 suites)** | EVALUATION | **Partially SHOWCASE** | 14.6 + 15 are essential; 16 quality + 17 security could be merged |
| Multiple runtime modes (DEMO/PILOT/PRODUCTION) | SECURITY | Keep | Fail-closed posture requires mode distinction |
| Knowledge provider abstraction | ESSENTIAL | Keep | Mock↔WeKnora swap IS the architecture |
| WeKnora integration | ESSENTIAL | Keep | Proves the abstraction works with real infra |
| **Domain pack dual-corpus** (fixtures vs domain) | — | **REMOVE** | Accidental complexity; one corpus suffices |
| **Wiki/Graph KB capabilities** | — | Not used | WeKnora capabilities declined by governance |

## What Would I Cut for an MVP?

1. **HOTL control plane** — impressive but not exercised in the
   business chain; the HITL approval gateway covers the human-gate
   need for insurance.
2. **Domain pack dual-corpus** — the fixtures KB and the domain/insurance
   KB serve overlapping purposes; the split was organic growth, not
   design.
3. **Phase 16 quality evaluator** — overlaps significantly with
   Phase 15 business evaluator; a merged "business quality" suite
   would be leaner.
4. **Parallel scheduler** — for a single-case demo, sequential
   execution is sufficient; the parallel DAG adds complexity that
   only matters at scale.
5. **6 evaluator suites** — could be 3 (knowledge, business, security)
   with quality dimensions folded into business.

## What is NOT Over-Engineered (would be wrong to cut)

1. **The governance registry** — this is THE differentiator. Without
   it, the agent can't prove its knowledge is authoritative.
2. **The provenance validators** — without them, the "no cheating"
   claim is empty.
3. **The provider abstraction** — without it, WeKnora integration
   would have required rewriting the agent core.
4. **The fail-closed posture** — this is insurance; "I don't know"
   is always better than a wrong answer.
5. **The mutation testing** — without it, "the tests aren't testing
   themselves" is unproven.

## Quantitative Honesty

```text
Lines of runtime code:     ~12,800
Lines of test code:        ~25,000+ (est. from 80 files)
Test-to-code ratio:        ~2:1
Evaluator suites:          6
Total eval cases:          300+ (across all suites)
Mutation tests:            26+ (M01-M08, M-AUTH 10, M-OBS 8, + eval mutations)
Total negative tests:      100+ (across all suites)
```

The test-to-code ratio is high — deliberate. In a domain where wrong
answers have regulatory consequences, the proof matters more than the
feature.
