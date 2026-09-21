# Architecture Decisions — Phase 20

8 key "why" answers, interview-ready. Each: Problem / Decision /
Alternative / Why rejected / Trade-off / Evidence.

---

## 1. Why Skills?

**Problem**: A single LLM prompt cannot enforce the data-chain
invariant (FACT→REQ→RISK→GAP→SOLUTION→PRODUCT). Without enforced
boundaries, a "risk analysis" could silently embed a product
recommendation, and you'd have no structural way to detect it.

**Decision**: 9 skills, each with a schema-validated contract. The
orchestrator enforces ordering and artifact-freeze. The contamination
invariant scans upstream artifacts for product leakage.

**Alternative**: One large prompt with chain-of-thought instructions.

**Why rejected**: No structural boundary enforcement; no per-stage
eval; no partial repair; no way to prove a skill didn't exceed its
scope.

**Trade-off**: More moving parts vs. provable non-interference.

**Evidence**: 11 `contracts/*.schema.json`; eval contamination check;
P15 I1-I8 invariants.

---

## 2. Why deterministic rules?

**Problem**: LLM-as-judge is non-reproducible. Governance decisions
(authority, license, effective window) must be the same every time —
an insurance regulator will not accept "the LLM thought it was
authoritative".

**Decision**: All governance/scoring/gating logic reads from
externalized `*.rules.json` files; the engine is pure Python,
deterministic, offline. No LLM in any governance/eval/scoring path.

**Alternative**: LLM-as-judge for governance decisions.

**Why rejected**: Non-reproducible; untestable; unauditable; AGENTS.md
§5: "脚本只消费不算" (scripts consume rules, never compute).

**Trade-off**: Less flexible than LLM judgment, but provable.

**Evidence**: 14.3 governance 74/74; 14.6 eval 50/50; all rules
files under `resources/config/`.

---

## 3. Why KnowledgeProvider abstraction?

**Problem**: Locking the agent to a specific retrieval backend means
either (a) the agent core must change when the backend changes, or
(b) you're stuck with a backend that may not fit.

**Decision**: `KnowledgeProvider` protocol (search-only interface);
Mock and WeKnora both implement it; the agent core never sees a
backend-specific API.

**Alternative**: Direct WeKnora SDK calls in the agent.

**Why rejected**: Agent core would need rewriting for every backend
change; testing would require a live service.

**Trade-off**: One more abstraction layer vs. backend freedom (proven
by the live Mock↔WeKnora swap).

**Evidence**: 14.1 C11; 18 G5 live equivalence; zero agent-core
changes during Phase 18 integration.

---

## 4. Why Governance?

**Problem**: A retrieval backend returns documents by relevance. But
relevance ≠ validity. An expired regulation can be highly relevant to
a query about a topic it used to govern. An unlicensed source can
contain accurate-sounding text. The LLM cannot judge authority.

**Decision**: A deterministic governance layer with 9 rules
(authority, license, effective window, jurisdiction, version, hash,
registry, lifecycle, content). The Agent-side registry is the truth
source — never the backend metadata.

**Alternative**: Trust the backend's metadata or the LLM's judgment.

**Why rejected**: Backends optimize for retrieval, not regulatory
compliance; LLMs hallucinate authority assessments.

**Trade-off**: More infrastructure vs. provable evidence eligibility.

**Evidence**: 14.3 governance 74/74; 18 G2 live (all mutation
classes DENY).

---

## 5. Why Evidence?

**Problem**: Recommendations must be traceable to knowledge, not to
LLM assertions. Without a structured evidence layer, you cannot prove
the agent's conclusion came from a real source.

**Decision**: Evidence items carry a citation tuple (source_id,
version_id, effective window, authority, license, jurisdiction,
content hash, retrieved_at). Only governance-approved hits become
evidence.

**Alternative**: Put the retrieved text directly in the recommendation.

**Why rejected**: No traceability; no tamper detection; no freshness
check; no audit trail.

**Trade-off**: More data per recommendation vs. full auditability.

**Evidence**: 14.5 provenance 44/44; P15 evidence grounding 15/15.

---

## 6. Why Provenance?

**Problem**: Evidence says "this text supports the conclusion";
provenance says "this text came from THIS source, at THIS version,
valid at THIS time, verified by THIS hash". Without provenance,
you cannot detect tampering or check freshness.

**Decision**: 10 provenance rules (P001-P010) forming a 4-hop chain:
decision → evidence → chunk → document → version → source. Every hop
is hash-anchored and independently verifiable.

**Alternative**: Trust the evidence content without verification.

**Why rejected**: Any tampering (in transit, in storage, or in the
evidence pipeline) would be undetectable.

**Trade-off**: Computational cost of hash verification vs. audit
integrity.

**Evidence**: 14.5 P001-P010; 18 G5 live chain; 3 manually-verified
chains in PROVENANCE_WALKTHROUGH.md.

---

## 7. Why fail-closed?

**Problem**: In a regulated domain, a wrong answer is worse than no
answer. An agent that hallucinates a coverage term or uses an expired
regulation creates liability.

**Decision**: Every failure mode defaults to DENY/ERROR/ABSTAIN:
insufficient evidence → abstain; provider down → error (no fallback);
UNKNOWN license → deny; missing critical info → STOP and ask.

**Alternative**: Best-effort with graceful degradation.

**Why rejected**: "Graceful degradation" in insurance means silently
wrong recommendations.

**Trade-off**: Sometimes the agent says "I can't answer" when a
human might have guessed. That's the point.

**Evidence**: 14.6 abstention 5/5; 18 G4 (7 provider-failure modes);
18 G6 (zero-overlap → abstain).

---

## 8. Why WeKnora instead of letting the LLM answer directly?

**Problem**: WeKnora offers both a pure retrieval API and an
Ask/ReAct LLM-answer API. Using the LLM-answer path would put
WeKnora's LLM-generated summary into the evidence chain — exactly
what the architecture is designed to prevent.

**Decision**: Use ONLY `POST /api/v1/knowledge-search` (pure
retrieval, no LLM summarization). The LLM answer path is structurally
unreachable from the provider. WeKnora owns "find what"; the Agent
owns "what evidence may inform a decision".

**Alternative**: Use WeKnora's Ask endpoint for faster answers.

**Why rejected**: LLM-generated text cannot be hash-verified or
provenance-traced; it would break the entire evidence chain.

**Trade-off**: More work to normalize retrieval results vs.
verifiable evidence.

**Evidence**: 14.1 C07; 18 G7 structural isolation tests; live
provenance chains verified.
