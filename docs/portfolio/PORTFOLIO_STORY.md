# Portfolio Story — 10-Minute Presentation

## 1. Problem — 1 min

Insurance advice can't be a single LLM call:

```text
User: "我家孩子刚出生,需要什么保险?"
LLM:  "建议购买XX重疾险,保额50万..."
```

Three failures:
- **No traceability**: which regulation? which version? which source?
- **No governance**: is the source authoritative? licensed? current?
- **No fail-closed**: the LLM always answers, even when it shouldn't.

A regulated domain needs an **execution layer** — not a better prompt.

## 2. Architecture — 2 min

```text
Client Intake → Canonical Client State (5-state: KNOWN/UNKNOWN/
  ESTIMATED/ASSUMED/INFERRED)
→ Requirement Analysis (boundary: requirement_only — no products)
→ Risk Analysis (R1–R5, no products)
→ Coverage Gap (deterministic; gap_level CRITICAL/HIGH/MEDIUM)
→ Solution (product-NEUTRAL strategy)
→ Knowledge Search (WeKnora → KnowledgeHit → Governance → Evidence)
→ Product Candidates (catalog + eligibility + evidence gating)
→ Recommendation (grounded; evidence_refs must resolve)
→ Report (10 sections; client-facing; honest about gaps)
```

Key decisions:
- **Skills with contracts** — each stage produces a schema-validated
  artifact; the data chain (FACT→REQ→RISK→GAP→SOLUTION→PRODUCT) is
  one-way.
- **Deterministic orchestration** — the LLM doesn't route; it reasons
  within a stage via tool-calling. The orchestrator proves ordering.
- **Provider abstraction** — Mock and WeKnora are interchangeable
  below the KnowledgeHit boundary; above it, one governance/evidence/
  provenance path.

## 3. Reliability — 2 min

- **Deterministic rules**: scoring, gating, governance — all from
  externalized JSON rules files. No LLM judges.
- **State**: checkpoint per stage; fingerprints detect tampering.
- **Retry**: eval→repair (max 2)→NEEDS_REVIEW (human gate).
- **Replan**: deterministic triggers; bounded; id-based merge.
- **HITL**: approval gateway (REQUESTED→WAITING_HUMAN→APPROVED).
  Only "human" can resolve — agents cannot self-approve.
- **HOTL**: pause/resume/cancel via control commands.
- **Fail-closed**: insufficient evidence → abstain. Provider down →
  error, no fallback. UNKNOWN license → deny.

**Proof**: 456 runtime tests, 42/42 benchmark (unsupported-claim-rate
= 0), 26 mutation tests proving the evaluator catches injected defects.

## 4. Knowledge — 1.5 min

```text
WeKnora (real v0.8.0, Docker, local)
   ↓ POST /api/v1/knowledge-search (PURE retrieval — NOT Ask/ReAct)
KnowledgeProvider (the ONLY thing agents see)
   ↓ normalize + validate
KnowledgeHit (document_id, chunk_id, content, score, hash)
   ↓ registry lookup (Agent-side governance registry)
Governance (9 rules: authority, license, window, jurisdiction,
   version, hash, registry, lifecycle, content)
   ↓ ALLOW / DENY
Evidence (citation tuple: source, version, window, authority,
   license, jurisdiction, hash, retrieved_at)
   ↓
Provenance (P001-P010: the 4-hop chain from decision to source)
```

**The key insight**: WeKnora owns "find what" (parse, chunk, hybrid
retrieve). The Agent owns "what evidence may inform an insurance
decision". WeKnora's LLM answer path is structurally unreachable.

**Live proof**: 48/48 live checks; Phase 15/16/17 evaluations re-run
under the WeKnora backend with zero regressions.

## 5. Evaluation — 1.5 min

| Layer | What it proves | Result |
|---|---|---|
| 14.6 Knowledge eval | Retrieval/governance/provenance correctness | 50/50 |
| 15 Business E2E | Full chain from client to report | 15/15 + I1-I8 |
| 16 Agent quality | Decision quality, abstention, contradiction | 30/30 + 8/8 mutations |
| 17 Security | Auth/RBAC/PII/approval/provider/fail-closed | 98/98 + 18 mutations |
| Benchmark | Unsupported claims, hallucination, repair | 42/42 |
| Full regression | 52-suite end-to-end | 51/0/1 |

**Anti-self-testing**: production never imports evaluators (scanned);
mutation tests inject defects and prove the evaluator catches them;
live WeKnora tests run against a REAL external service.

## 6. Honest Limitations — 1 min

- Product catalog is **demo** (12 fictional products; is_demo: true)
- No real customer deployment; no production database
- No production-scale benchmark (single dev box)
- LLM cost not measured (deterministic path has 0 LLM calls)
- WeKnora lacks governance metadata → agent-side registry required
- Event log lacks cryptographic chaining (P2 technical debt)
- No solution direction for life/R4 in the current model
- R-05 provider-policy still BLOCKED (operator verification pending)
- 7 P2/P3 findings documented, none blocking

---

## What Makes This Different

1. **Every claim is testable** — 456 tests + 6 evaluators + 300+ cases
2. **Real external integration** — WeKnora v0.8.0, not a mock
3. **Governance is the architecture** — not a bolt-on filter
4. **Fail-closed is the default** — not an error-handling afterthought
5. **The evaluator has teeth** — mutation tests prove it catches cheats
