# Phase 19 — Final Audit Report

Date: 2026-09-21 · Independent, adversarial, interview-oriented.

## Executive Summary

The project delivers what it claims: a governed, evidence-traceable,
fail-closed insurance agent runtime with real WeKnora integration,
backed by 456 tests and 6 evaluator suites. Every capability maps to
code, tests, and reproducible evidence. The REAL/MOCK/DEMO boundaries
are explicit and honest. No P0/P1 findings remain.

## 1. Current Project State

```text
Commits:          20+ across phases 1–18
Runtime code:     ~12,800 lines (92 Python files)
Test code:        ~25,000+ lines (80 test files)
Docs:             38 production docs + 8 portfolio docs
Evaluators:       6 suites, 300+ cases
Current battery:  456 runtime + 12 portfolio + 51-suite regression
                  + 42/42 benchmark + all phase suites green
Live WeKnora:     48/48 live checks + P15/16/17 under WeKnora green
```

## 2. What Has Actually Been Proven

1. **Full business chain**: client → requirement → risk → gap →
   solution → knowledge → candidate → recommendation → report (P15).
2. **Real WeKnora integration**: live HTTP retrieval, governed,
   provenance-traceable, in both mock and live modes (P18).
3. **Governance correctness**: 9 rules, registry-authoritative,
   fail-closed on every mutation class (P14.3, P18 G2).
4. **Provenance integrity**: 4-hop chain, hash-anchored, tamper-
   detected (P14.5, P18 G5, 3 manually-verified chains).
5. **Security posture**: auth/RBAC/isolation/PII/encryption/
   approval/provider-policy all tested with negative cases (P17).
6. **Evaluation independence**: mutation tests prove evaluators
   catch defects; production never imports evaluators (P14.4/16/17).
7. **Lifecycle resilience**: backup/restore/retention/erasure (P13).
8. **Fail-closed discipline**: 7 provider-failure modes, abstention,
   insufficient-info, contradiction — all safe (P18 G4/G6, P16).

## 3. What Has Not Been Proven

1. Production-scale performance (single dev box)
2. Real customer safety (no real PII used)
3. Real LLM cost (deterministic path has 0 calls)
4. Multi-tenant isolation (single-node)
5. Production deployment (loopback only)
6. Regulatory compliance of the real documents (license_status is
   our assessment, not legal review)

## 4. Real vs Mock vs Demo

See REAL_VS_DEMO.md. Summary:
- **Real**: WeKnora v0.8.0, governance, evidence, provenance,
  evaluation, security, backup/restore/retention, all 8 business
  skills (deterministic engines)
- **Mock**: MockKnowledgeProvider, fixtures KB, seam tests
- **Demo**: product catalog (12 fictional), dialogue-driven stages
  (intake/requirement/risk), all demo scripts
- **Not implemented**: production database, deployment, real catalog,
  verified LLM provider, multi-tenant, public exposure

No documentation-claim > actual-capability instances found.

## 5. Architecture Review

**Strengths**: Clean separation (orchestrator/skills/knowledge/
governance); provider abstraction proven by Mock↔WeKnora swap;
deterministic-first (no LLM in any governance/eval/scoring path);
contract-driven (11 schema files, all validated).

**Weaknesses**: Dialogue stages are `executor: provided` — their
derivation quality isn't deterministically re-testable (F-14). The
domain-pack dual-corpus is accidental complexity.

## 6. Agent Engineering Review

**Strengths**: State management is rigorous (5-state canonical client
state); replanning is bounded and deterministic; HITL/HOTL provide
human control; crash recovery via checkpoints is tested cross-process.

**Weaknesses**: No solution direction for life/R4 (F-16); conflicts
in the stored artifact aren't retained (F-17, P3 — the escalation
hand-off carries them but the artifact itself drops the detail).

## 7. Knowledge / RAG Review

**Strengths**: The dual-identity model (WeKnora = retrieval; Agent =
governance) is architecturally clean and proven live. Abstention
works (agent-side policy drops zero-overlap candidates even when
WeKnora returns keyword hits). Hash anchoring detects tampering.

**Weaknesses**: The projection registry must be manually re-synced
after WeKnora re-chunking (operational burden). Multi-chunk documents
show hash mismatch between WeKnora's search response and chunks API
(sub-chunk vs parent-chunk content difference — finding F-24, P3).

## 8. Security Review

**Strengths**: Comprehensive threat model (T01-T15); auth/RBAC
fail-closed; PII redaction (field-based, 26 fields); encryption at
rest in strict modes; approval forging detected; retention lifecycle
audited.

**Weaknesses**: Event log lacks cryptographic chaining (F-18, P2);
credential-shaped values in free-text survive field-based redaction
(F-20, P3).

## 9. Evaluation Review

**Strengths**: 6 evaluator suites cover correctness, quality,
security, observability; mutation testing throughout; adversarial
testing (42 attacks, 42 PASS); regression discipline (never weakened).

**Weaknesses**: Some overlap between Phase 15 and 16 evaluators
(could be merged); NOT_MEASURABLE metrics are honestly declared but
limit the quantitative story.

## 10. Adversarial Findings

42 attacks executed, 42 PASS, 0 FAIL. See ADVERSARIAL_FINDINGS.md.
All attack surfaces were pre-covered by the phase 14–18 suites —
the adversarial posture is a design property, not a post-hoc audit.

## 11. Production Gaps

Ranked by severity:
1. Production database (JSON/JSONL → PostgreSQL)
2. Real insurance product catalog
3. Verified LLM provider (R-05 operator verification)
4. Multi-tenant deployment with OIDC/SSO
5. Production-scale benchmark
6. Distributed locking (FileLock → distributed lock)
7. Message queue for async processing

## 12. Technical Debt

| ID | Severity | Description |
|---|---|---|
| F-02 | P2 (closed) | Strict-mode provider enforcement — CLOSED in Phase 18 |
| F-08 | P2 (deferred) | Engine reconstruction overhead (perf) |
| F-09 | P2 (deferred) | Risk/gap/solution evidence_refs convention |
| F-14 | P3 | Dialogue-stage derivation not deterministically testable |
| F-16 | P2 | No solution direction for life/R4 |
| F-17 | P3 | Conflicts dropped from stored artifact |
| F-18 | P2 | Event log lacks cryptographic chaining |
| F-20 | P3 | Value-pattern credential redaction |
| F-22 | P3 | WeKnora server-side no-abstention |
| F-23 | P3 | WeKnora lacks governance metadata (by design) |
| F-24 | P3 (NEW) | Multi-chunk hash mismatch (search vs chunks API) |

## 13. Portfolio Risks

1. **"Too academic"** — no real customer deployment → mitigated by
   the honest limitations narrative + real WeKnora integration.
2. **"Over-engineered"** — 12,800 lines for a demo → mitigated by
   the over-engineering review showing what's essential vs showcase.
3. **"Not enough LLM"** — the LLM is a bounded tool-caller → this
   IS the design; frame it as "the LLM doesn't route, it reasons
   within a governed stage."
4. **"Demo catalog"** — all products are fictional → honest; the
   contribution is the runtime, not the catalog.

## 14. Interview Attack Points (Top 10)

1. "Why not just use LangChain?" → Provider abstraction + governance
   is the contribution; LangChain doesn't do regulated-domain evidence.
2. "What if the LLM hallucinates?" → Structural: LLM text never
   enters evidence; only engine chunks do; benchmark 42/42.
3. "How do you know tests aren't circular?" → Mutation testing +
   live external service + production-never-imports-evals scan.
4. "What breaks at 100K cases/day?" → JSON persistence, in-memory
   BM25, single-process locks, no queue.
5. "Why WeKnora and not [X]?" → Open-source, self-hosted, Chinese
   doc support, pure retrieval API separate from LLM answers.
6. "Isn't this just if-else?" → The deterministic parts ARE if-else,
   and that's the point: provable > probabilistic for governance.
7. "Show me a real provenance chain" → 3 manually-verified chains
   in the walkthrough.
8. "What would you simplify?" → HOTL, dual-corpus, merge P15/P16
   evaluators, drop parallel scheduler for MVP.
9. "How fresh is your knowledge?" → Effective-window governance +
   as_of queries + freshness eval dimension.
10. "Is this production-ready?" → No, and here's exactly what's
    missing (7 production gaps listed).

## 15. Recommended Demo Flow

```text
1. (30s)  Show the architecture diagram (README)
2. (2m)   Run demo_portfolio.py — full chain + evidence + report
3. (2m)   Show the provenance walkthrough (3 chains)
4. (1m)   Show live WeKnora retrieval (test_p18_live_weknora.py)
5. (1m)   Show a governance DENY (tamper a hash → P007)
6. (1m)   Show the security evaluator (98/98 + 10/10 mutations)
7. (1m)   Show honest limitations (PORTFOLIO_STORY.md §6)
8. (30s)  Q&A — the attack surface is the strongest asset
```

## 16. Final Freeze Decision

```text
PORTFOLIO_FREEZE_READY
```

### Gate Verification

| Gate | Status |
|---|---|
| HG19-01 No new business capability | ✓ |
| HG19-02 No Orchestrator rewrite | ✓ |
| HG19-03 No Knowledge architecture rewrite | ✓ |
| HG19-04 No evaluator gaming | ✓ |
| HG19-05 All claims trace to code/test | ✓ (REAL_VS_DEMO audit) |
| HG19-06 REAL/MOCK/DEMO boundaries explicit | ✓ (PROJECT_FACT_BASELINE) |
| HG19-07 3 real WeKnora provenance chains | ✓ (PROVENANCE_WALKTHROUGH) |
| HG19-08 10+ adversarial attacks | ✓ (42 attacks, ADVERSARIAL_FINDINGS) |
| HG19-09 All P0/P1 closed | ✓ (0 P0/P1 remaining) |
| HG19-10 P2/P3 documented | ✓ (11 findings in §12) |
| HG19-11 Phase 14-18 regression green | ✓ (456 + 51/0/1 + all suites) |
| HG19-12 No silent Mock fallback | ✓ (18 G4 live proof) |
| HG19-13 No Ask/ReAct in integration | ✓ (14.1 C07 + 18 G7) |
| HG19-14 No unsupported production claims | ✓ (README audit clean) |
| HG19-15 10-minute portfolio story | ✓ (PORTFOLIO_STORY.md) |
