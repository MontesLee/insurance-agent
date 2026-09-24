# Insurance Agent — Evidence-Grounded Agent Runtime

> Language: English | [中文版](README.zh-CN.md)

**An evidence-grounded insurance Agent runtime that separates LLM
reasoning from deterministic governance, provenance, and evaluation.**

```text
Traditional LLM app:    User → LLM → Answer

This runtime:           User → Agent Runtime → Skills → Knowledge
                        → Governance → Evidence → Provenance
                        → Decision → Report
```

| | |
|---|---|
| Runtime tests | 474 PASS |
| Benchmark | 42/42 (unsupported-claim-rate = 0) |
| Adversarial tests | 42/42 |
| Live WeKnora retrieval | PASS (v0.8.0, real HTTP) |
| Full regression | 51 suites, 0 FAIL |
| Mutation tests | 26/26 (evaluator catches injected defects) |

---

## Why I Built This

A single LLM call cannot deliver insurance advice because it cannot:

- **Prove traceability** — which regulation? which version? which source?
- **Enforce governance** — is the source authoritative? licensed? current?
- **Fail closed** — the LLM always answer, even when it shouldn't.
- **Recover** — partial failures cascade; no checkpoint, no retry.
- **Be evaluated** — you can't regression-test a prompt.

This project builds the **execution layer** — the agent *runtime*,
not another prompt. The LLM is a bounded tool-caller inside a governed
stage; deterministic rules decide what evidence may inform a decision.

---

## Architecture

```text
                        User
                         │
                         ▼
                ┌─────────────────┐
                │  Agent Runtime  │  (orchestrator, scheduler,
                └────────┬────────┘   checkpoint, replan, HITL/HOTL)
                         │
                         ▼
                ┌─────────────────┐
                │     Skills      │  (8 stages, schema contracts,
                └────────┬────────┘   data-chain invariant)
                         │
                         ▼
                ┌─────────────────┐
                │ Knowledge Layer │
                └────────┬────────┘
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
      Mock Provider             WeKnora v0.8.0
      (offline tests)       (live HTTP retrieval)
             │                       │
             └───────────┬───────────┘
                         ▼
                ┌─────────────────┐
                │ KnowledgeHit    │  (document_id, chunk_id,
                └────────┬────────┘   content, score, hash)
                         ▼
                ┌─────────────────┐
                │   Governance    │  (9 rules: authority, license,
                └────────┬────────┘   window, jurisdiction, hash…)
                         ▼
                ┌─────────────────┐
                │    Evidence     │  (citation tuple: source, version,
                └────────┬────────┘   window, authority, hash, time)
                         ▼
                ┌─────────────────┐
                │   Provenance    │  (P001–P010: the 4-hop chain
                └────────┬────────┘   from decision to source)
                         ▼
                ┌─────────────────┐
                │    Decision     │  (recommendation, report)
                └────────┬────────┘
                         ▼
                     Report
```

> **WeKnora provides retrieval infrastructure.** The Agent owns
> governance, evidence validation, provenance, and decision constraints.

---

## 3-Minute Demo

```bash
./scripts/portfolio/run_demo.sh
```

Three scenarios, all running the REAL system:

| Demo | What it shows | Result |
|---|---|---|
| **A — Normal Decision** | Full chain: client → requirement → risk → gap → solution → knowledge → governance → evidence → recommendation → report | PASS |
| **B — Evidence Tampering** | Valid evidence → 1-byte hash mutation → provenance DENY (P007) | DENY |
| **C — Insufficient Evidence** | Unrelated query → agent-side abstention → no unsupported claim | ABSTAIN |

For live WeKnora mode:
```bash
export INSURANCE_AGENT_KNOWLEDGE_PROVIDER=weknora
export INSURANCE_AGENT_WEKNORA_URL=http://127.0.0.1:8080
export INSURANCE_AGENT_WEKNORA_API_KEY=<your-key>
export INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID=<kb-id>
./scripts/portfolio/run_demo.sh
```

---

## What's Real vs Demo

| Area | Status |
|---|---|
| Agent Runtime (orchestrator, scheduler, checkpoint) | **Real** |
| Skills (9, with schema contracts) | **Real** |
| Knowledge Governance (9 rules, registry-authoritative) | **Real** |
| Evidence + Provenance (P001–P010, hash-anchored) | **Real** |
| WeKnora retrieval (v0.8.0, live HTTP, Docker) | **Real** |
| Evaluation (6 suites, 300+ cases, mutation testing) | **Real** |
| Security (auth, RBAC, PII, encryption, retention) | **Real** |
| Product catalog | **Demo** (12 fictional products) |
| LLM provider | **Not validated** (R-05 gate BLOCKED) |
| PostgreSQL persistence + knowledge registry | **Real** (strict modes: authoritative, fail-closed) |
| Multi-tenant / public deployment | **Not implemented** |

→ Full audit: [docs/portfolio/REAL_VS_DEMO.md](docs/portfolio/REAL_VS_DEMO.md)

---

## Key Design Decisions

| Decision | Why |
|---|---|
| **Skills, not one prompt** | Data-chain invariant (FACT→REQ→RISK→GAP→SOL→PRODUCT); per-stage contracts, eval, and repair |
| **Deterministic rules, no LLM judge** | Reproducible, testable, auditable; externalized `*.rules.json`; AGENTS.md §5 |
| **Provider abstraction** | Mock ↔ WeKnora swap below the KnowledgeHit boundary; governance/evidence/provenance unchanged |
| **Governance registry** | The Agent, not the backend, owns authority/license/window/jurisdiction |
| **Evidence ≠ LLM answer** | Only engine-retrieved verbatim chunks become evidence; LLM text never enters the chain |
| **Provenance (P001–P010)** | Hash-anchored 4-hop chain: decision → evidence → chunk → source |
| **Fail-closed everywhere** | Insurance domain: "I don't know" > wrong answer |
| **WeKnora ≠ Agent brain** | WeKnora finds documents; the Agent decides what may inform a recommendation |

→ Full reasoning: [docs/portfolio/ARCHITECTURE_DECISIONS.md](docs/portfolio/ARCHITECTURE_DECISIONS.md)

---

## Evaluation

```text
Test Pyramid:
Unit → Contract → Integration → Business E2E → Mutation → Security → Live WeKnora

Runtime tests:           474 PASS
Benchmark:              42/42 (unsupported-claim-rate = 0)
Adversarial:            42/42 (knowledge + agent + security + eval attacks)
Phase 14–18 regression: PASS (all suites, mock + live modes)
Mutation testing:       26/26 (evaluator catches injected defects)
Security evaluation:    98/98 (auth, RBAC, PII, approval, provider)
Live WeKnora:           48/48 (retrieval, governance, provenance, failures)
```

> These are project-level validation results, not production SLA or
> industry benchmark results.

→ Details: [docs/portfolio/EVALUATION.md](docs/portfolio/EVALUATION.md)

### Human Review Layer — Risk-based Reviewer Validation v2

人工审核不再阅读全量产物,而是审核一张风险分级的 Review Card
(Human reviewers read one risk-ranked card instead of the full
artifact pile). For every finished run, an offline generator aggregates
the existing eval records + case state into `human_review_card.json`
and assigns a review level:

```text
AUTO_PASS        4 automatic checks PASS + no HIGH/MEDIUM flags + not sampled
SUMMARY_REVIEW   MEDIUM flag or audit-sampling hit — read the card only (<3 min)
DEEP_REVIEW      validation FAIL or HIGH flag — open the full evidence chain
```

- Four automatic dimensions (`schema / trace / evidence / logic`) are
  pure projections of the eval engine's own checks — no new validators.
- Fail-closed honesty: a dimension with zero underlying checks reports
  FAIL, never a silent PASS; UNKNOWN customer fields render as null,
  never a guess (inherited from the eval engine §19 rules).
- Deterministic audit sampling (`sha1(case:run)` mod, default 10%) —
  reproducible, no runtime randomness.
- Zero runtime coupling: lives in `evaluation/human-review/`, imports
  nothing from `runtime/`, touches no state.

→ `evaluation/human-review/` — card schema, `risk-rules.yaml`,
  generator, [reviewer guide](evaluation/human-review/reviewer-guide.md)
  (人工审核操作规范)
→ Tests: `tests/eval/test_review_card.py` (9/9; verified against all 6
  real pilot runs)

---

## Provenance Chain

Every recommendation traces to a real source:

```text
Decision
  → Evidence (evidence_id)
    → KnowledgeHit (chunk_id, content_hash)
      → WeKnora Chunk (live retrieval)
        → Document (document_id)
          → Version (source_id@version, effective window)
            → Source (authority, license, jurisdiction, canonical_uri)
```

Tamper any byte → hash mismatch → DENY. Expired regulation → window
check → DENY. Unknown license → DENY. Wrong jurisdiction → DENY.

→ 3 manually-verified chains: [docs/portfolio/PROVENANCE_WALKTHROUGH.md](docs/portfolio/PROVENANCE_WALKTHROUGH.md)

---

## Honest Limitations

- Product catalog is **demo** (12 fictional products)
- No real customer deployment
- No production-scale database deployment (PostgreSQL layer implemented
  and verified; single-node dev instance only)
- No production-scale benchmark (single dev box)
- LLM cost not measured (deterministic path: 0 LLM calls)
- WeKnora lacks governance metadata → agent-side registry required
- Event log lacks cryptographic chaining (P2 technical debt)
- R-05 provider-policy still BLOCKED (operator verification pending)
- 3 P2 + 3 P3 findings documented, none blocking
  (F-16 and F-24 closed in Phase 24)

→ Full list: [docs/portfolio/LIMITATIONS.md](docs/portfolio/LIMITATIONS.md)

---

## Portfolio Package

| Document | Purpose |
|---|---|
| [PORTFOLIO_STORY.md](docs/portfolio/PORTFOLIO_STORY.md) | 10-minute narrative |
| [ARCHITECTURE_DECISIONS.md](docs/portfolio/ARCHITECTURE_DECISIONS.md) | 8 key "why" answers |
| [PROVENANCE_WALKTHROUGH.md](docs/portfolio/PROVENANCE_WALKTHROUGH.md) | 3 real chains (valid/tampered/abstain) |
| [EVALUATION.md](docs/portfolio/EVALUATION.md) | Test pyramid + metrics |
| [REAL_VS_DEMO.md](docs/portfolio/REAL_VS_DEMO.md) | Capability classification |
| [LIMITATIONS.md](docs/portfolio/LIMITATIONS.md) | All P2/P3 findings |
| [INTERVIEW_SCRIPT_10MIN.md](docs/portfolio/INTERVIEW_SCRIPT_10MIN.md) | Timed presentation script |
| [INTERVIEW_QA.md](docs/portfolio/INTERVIEW_QA.md) | 30 interview Q&A |
| [INTERVIEW_ATTACK_SURFACE.md](docs/portfolio/INTERVIEW_ATTACK_SURFACE.md) | 30 attack questions |
| [ADVERSARIAL_FINDINGS.md](docs/portfolio/ADVERSARIAL_FINDINGS.md) | 42 attacks, all PASS |
| [OVER_ENGINEERING_REVIEW.md](docs/portfolio/OVER_ENGINEERING_REVIEW.md) | What's essential vs showcase |
| [PROJECT_FACT_BASELINE.md](docs/portfolio/PROJECT_FACT_BASELINE.md) | REAL/MOCK/DEMO classification |
| [PHASE_19_FINAL_AUDIT.md](docs/portfolio/PHASE_19_FINAL_AUDIT.md) | Independent audit report |

---

## Quick Start

```bash
# Run the demo (offline mode — no WeKnora needed)
python demo/portfolio_demo/run_all.py

# Run the full test battery
python -m pytest tests/runtime -q
python -m pytest tests/portfolio -q

# Run the benchmark
python tests/runtime/test_benchmark.py

# Full regression (52 suites)
python tmp/run_regression.py
```

---

## Repository Structure

```text
insurance-agent/
├── README.md                  ← this file
├── AGENTS.md                  ← project conventions (deterministic-first)
├── runtime/                   ← agent runtime (orchestrator, harness, tools)
├── knowledge/                 ← knowledge layer (provider, governance,
│                                  evidence, provenance, pilot corpus)
├── adapters/                  ← canonical artifact adapters
├── contracts/                 ← 11 schema files (skill contracts)
├── .trae/skills/              ← 9 skill definitions
├── catalog/                   ← demo product catalog
├── evals/                     ← 6 evaluator suites
├── evaluation/human-review/   ← risk-based human review layer (Review Card)
├── tests/                     ← 97 test files
├── demos/                     ← 10 demo scripts
├── demo/portfolio_demo/       ← 3-scenario portfolio demo
├── scripts/portfolio/         ← demo runner
├── docs/
│   ├── architecture/          ← architecture docs
│   ├── production/            ← 38 phase reports
│   └── portfolio/             ← 19 portfolio documents
└── tmp/                       ← runtime artifacts (gitignored)
```

---

## My Contribution

The architecture and semantics: skill boundaries, canonical client
state, provider abstraction, governance rules, provenance validators,
evaluation strategy, HITL/HOTL control design, checkpoint/recovery,
benchmark & red-team design, WeKnora integration.

AI coding tools were used as development tooling; the system design
and its proofs are the point.
