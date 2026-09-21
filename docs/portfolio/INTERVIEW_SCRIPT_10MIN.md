# 10-Minute Interview Script — Phase 20

Timed presentation. What to say, what to show, what NOT to say,
and the likely follow-up question.

---

## 0:00–1:00 — Problem

**Say**:
"Insurance advice can't be a single LLM call. An LLM can't prove
which regulation version it cited, can't verify the source is
licensed, can't detect that the knowledge is expired, and always
answers even when it shouldn't. In a regulated domain, that's not
a UX problem — it's a liability problem.

So I built the execution layer: an agent runtime that separates
LLM reasoning from deterministic governance, provenance, and
evaluation. The LLM is a bounded tool-caller inside a governed
stage. Deterministic rules decide what evidence may inform a
decision."

**Show**: The architecture diagram (README).

**Don't say**: "AI insurance bot", "revolutionary", "replaces human
advisors".

**Likely question**: "Isn't this just if-else around an LLM?"
→ "Yes, exactly. That's the point: provable > probabilistic for
governance."

---

## 1:00–3:00 — Architecture

**Say**:
"The system has 9 skills in a one-way data chain: intake →
requirement → risk → gap → solution → knowledge → candidate →
recommendation → report. Each produces a schema-validated artifact.

The orchestrator enforces ordering, artifact-freeze, and per-stage
eval. The scheduler is a bounded parallel DAG. Checkpoints use
per-stage fingerprints for crash recovery.

For knowledge: I use a provider abstraction. Mock for offline
testing, WeKnora for live retrieval. Both are interchangeable below
the KnowledgeHit boundary. Above it, one governance-evidence-
provenance path."

**Show**: The knowledge layer diagram (ARCHITECTURE.md Diagram 1).

**Don't say**: Too much detail about the scheduler internals.

**Likely question**: "Why not let the LLM decide the next step?"
→ "Because then I can't prove that a RISK artifact was produced
from a complete CLIENT PROFILE."

---

## 3:00–5:00 — Live Demo

**Say**: "Let me show you three scenarios."

**Show**: Run `./scripts/portfolio/run_demo.sh`

**Demo A** (60s): Full chain — client profile through recommendation
to report. Show the evidence chain: document_id, source_id,
version_id, authority, license, hash. "Every recommendation traces
to a real source."

**Demo B** (60s): "Now I tamper ONE BYTE in the evidence hash."
Show: DENY with P007 hash_mismatch. "The provenance validator
catches any content tampering — in transit, in storage, or in the
pipeline itself."

**Demo C** (60s): "Now I ask about Bundesliga standings." Show:
INSUFFICIENT_EVIDENCE. "The agent abstains. This is the agent's
policy layer, not the backend — the backend returned keyword
matches, but the agent's relevance threshold dropped them."

**Don't say**: "This is production-ready."

**Likely question**: "What if the LLM hallucinates?"
→ "Structurally: LLM text never enters evidence. Only engine-
retrieved verbatim chunks become evidence."

---

## 5:00–6:30 — Knowledge + Governance + Provenance

**Say**:
"The key insight is the dual-identity model: WeKnora owns 'find
what' — parsing, chunking, hybrid retrieval. The Agent owns 'what
evidence may inform an insurance decision' — authority, license,
effective window, jurisdiction, version, hash.

Governance has 9 deterministic rules. The registry is the truth
source — never the backend metadata. WeKnora's LLM answer path is
structurally unreachable.

Provenance has 10 rules forming a 4-hop chain from decision to
source. Every hop is hash-anchored. I have 3 manually-verified
provenance chains you can inspect."

**Show**: PROVENANCE_WALKTHROUGH.md — the 3 chains.

**Don't say**: "WeKnora does governance" (it doesn't).

**Likely question**: "Why not use WeKnora's Ask API?"
→ "Because LLM-generated text can't be hash-verified or provenance-
traced. It would break the entire evidence chain."

---

## 6:30–8:00 — Evaluation + Security

**Say**:
"Evaluation is where I spent the most effort. 456 runtime tests,
42/42 benchmark with unsupported-claim-rate = 0, 42 adversarial
attacks, 26 mutation tests proving the evaluator catches injected
defects.

The mutation tests are the key: I inject defects (delete a
requirement, fabricate a product, tamper the report) and prove the
evaluator catches them. This proves the tests aren't circular.

For security: 98 checks covering authentication, RBAC, project
isolation, PII redaction, encryption, approval forging, and
provider-policy fail-closed."

**Show**: EVALUATION.md — the test pyramid.

**Don't say**: "99.99% reliability" (no evidence for that number).

**Likely question**: "How do you know tests aren't testing
themselves?" → "Mutation testing + production never imports
evaluators + live WeKnora tests hit a real external service."

---

## 8:00–9:00 — What I Would Simplify

**Say**:
"Honestly? The HOTL control plane is showcase — impressive but not
used in the business chain. The domain-pack dual-corpus was
accidental complexity. The Phase 15 and 16 evaluators overlap
significantly. And the parallel scheduler only matters at scale.

What I would NOT cut: the governance registry, the provenance
validators, the provider abstraction, the fail-closed posture, and
the mutation testing. Those are the differentiators."

**Show**: OVER_ENGINEERING_REVIEW.md.

**Don't say**: "Everything is essential."

**Likely question**: "What's over-engineered?" → Give the honest
list. Self-awareness is valued.

---

## 9:00–10:00 — Limitations + Production Roadmap

**Say**:
"To be clear about what this is NOT: the product catalog is demo
(12 fictional products). There's no production database — it's
JSON files. No real customer deployment. No production-scale
benchmark. The LLM cost isn't measured because the deterministic
path makes zero LLM calls.

For production, I'd need: a real database, a real product catalog,
a verified LLM provider, multi-tenant deployment, distributed
locking, and a message queue.

But the architecture — the governance, the evidence chain, the
provenance — that's designed for production and tested against
real infrastructure."

**Show**: LIMITATIONS.md.

**Don't say**: "This is ready for production" (it isn't).

**Likely question**: "What breaks at 100K cases/day?"
→ "JSON persistence, in-memory BM25, single-process locks, no
queue. The architecture handles it; the infrastructure doesn't."
