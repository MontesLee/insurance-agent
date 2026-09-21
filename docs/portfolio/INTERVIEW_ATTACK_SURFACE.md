# Interview Attack Surface — Phase 19

30 questions a senior interviewer would ask. Each answered from
CODE + TEST EVIDENCE, with honest remaining limitations.

Format: Q / Current Answer / Evidence / Code / Test / Limitation / Risk.

---

## Architecture

### Q1. Why Skills instead of one big Prompt?

**Answer**: A single prompt cannot enforce the data-chain invariant
(FACT→REQ→RISK→GAP→SOLUTION→PRODUCT), cannot checkpoint per-stage,
cannot repair one stage without redoing the rest, and cannot prove
boundary violations didn't happen. Skills give per-stage contracts
(schema-validated artifacts), eval boundaries, and structural
non-interference (the contamination invariant).

**Evidence**: `AGENTS.md` §2 skill table; `runtime/insurance-analysis.yaml`
(8 stages, each with produces/consumes/contract); eval `contamination`
invariant (upstream must not leak product ids).

**Code**: `.trae/skills/*/SKILL.md` + `contracts/*.schema.json`

**Test**: `test_p15_business_e2e.py` I-invariants; eval_engine
contamination check.

**Limitation**: Dialogue-driven stages (intake/requirement/risk) are
`executor: provided` — their derivation quality isn't deterministically
re-testable (F-14).

**Risk**: LOW — the boundary reasoning is architectural, not code-detail.

---

### Q2. Why an Orchestrator?

**Answer**: The orchestrator enforces stage ordering, artifact-freeze,
preconditions, and the eval boundary. Without it, an LLM calling skills
freely could produce an artifact graph that violates the data chain,
skip eval, or overwrite frozen upstream artifacts.

**Evidence**: `runtime/orchestrator.py` — `_execute_stage` enforces
consumes/produces; `transitions.py` enforces ordering; `checkpoint.py`
validates recovery.

**Code**: `runtime/orchestrator.py:423` (_execute_stage);
`runtime/state/transitions.py` (artifact freeze)

**Test**: `test_cross_process_recovery.py`, `test_harness.py`,
harness idempotency suites.

**Limitation**: The orchestrator is tightly coupled to the insurance
workflow YAML — a second domain needs a second YAML (the SE workflow
proves generality).

**Risk**: LOW.

---

### Q3. Why not let the LLM decide the next step?

**Answer**: Because the system must be provable. If the LLM decides,
you cannot prove that a RISK artifact was always produced from a
complete CLIENT PROFILE, or that a PRODUCT was never recommended
before a GAP was computed. Deterministic orchestration + deterministic
eval = the "agent didn't cheat" proof (§Q25).

**Evidence**: The scheduler is bounded DAG, not LLM-driven; replanning
is deterministic-trigger, not LLM-whim.

**Code**: `runtime/harness/harness.py` bounded scheduler;
`runtime/planner/` deterministic graph.

**Test**: Phase 11 benchmark 42/42 (unsupported-claim-rate = 0);
false-pass injection suite.

**Limitation**: LLM reasoning DOES happen inside specialist agents
(via tools) — it's bounded to tool-calling within a stage, not
cross-stage routing.

**Risk**: MEDIUM — interviewer may push on "so the LLM is just a
tool-caller?" (answer: yes, by design, that's the point).

---

### Q4. Why separate deterministic logic from LLM reasoning?

**Answer**: Deterministic rules (scoring, gating, governance) are
reproducible, testable, and auditable. LLM reasoning is probabilistic.
Mixing them means you cannot regression-test the deterministic parts,
and you cannot prove the governance decisions weren't LLM-overridden.
AGENTS.md §5: "脚本只消费不算" — scripts consume rules, never compute.

**Evidence**: All governance/eval/score logic reads from externalized
`resources/config/*.rules.json`; the engine is deterministic.

**Code**: `knowledge/rag/engine.py` (reranker reads rules);
`knowledge/governance/governance.py` (9 rules, no LLM);
`evals/` (all deterministic, no LLM judge).

**Test**: 14.3 governance 74/74; 14.6 eval 50/50; 16 quality 30/30 —
all deterministic.

**Risk**: LOW.

---

### Q5. What does Canonical Client State solve?

**Answer**: Fact drift between skills. Without it, each skill could
re-interpret the client's words differently. The canonical state is a
single fact source with per-field status (KNOWN/UNKNOWN/ESTIMATED/
ASSUMED/INFERRED) — every downstream skill references `client_state.*`
not `client-intake.*`.

**Evidence**: `AGENTS.md` §3 canonical client state diagram + 5-state
status model; upstream-immutability principle (§4).

**Code**: `contracts/client-profile.schema.json` (5-state fields).

**Test**: P15 I1 invariant (missing facts never asserted KNOWN
downstream); P16 contradiction cases.

**Risk**: LOW.

---

### Q6. How does the Agent prevent fact drift between Skills?

**Answer**: Three mechanisms: (1) canonical state is the only fact
source; (2) artifact freeze — completed upstream artifacts cannot be
rewritten; (3) the contamination invariant — upstream analysis
artifacts are scanned for product leakage.

**Evidence**: P15 I1 (no fabricated facts); contamination eval check.

**Code**: `runtime/state/transitions.py` (freeze);
`runtime/eval_engine.py` contamination check.

**Test**: `test_p15_business_e2e.py` structural checks.

**Risk**: LOW.

---

### Q7. Why Evidence?

**Answer**: Recommendations must be traceable to knowledge, not to
LLM assertions. Without evidence, you cannot prove the agent's
conclusion came from a real source rather than hallucination. Evidence
is the bridge between retrieval and decision.

**Evidence**: 14.5 provenance closure — validate_provenance P001-P010.

**Code**: `knowledge/governance/governance.py` build_evidence_item.

**Test**: 14.5 provenance 44/44; 15 business eval evidence grounding.

**Risk**: LOW.

---

### Q8. Why does Evidence also need Provenance?

**Answer**: Evidence says "this text supports the conclusion";
provenance says "this text came from THIS source, at THIS version,
valid at THIS time, verified by THIS hash". Without provenance, you
cannot detect tampering, cannot check freshness, and cannot audit
which regulation version was relied upon.

**Evidence**: The 4-hop chain: decision→evidence→chunk→document→
version→source; validate_provenance with 10 rules.

**Code**: `knowledge/governance/provenance.py`.

**Test**: 14.5 P001-P010; 18 live provenance chain verified.

**Risk**: LOW.

---

### Q9. Why can't Recommendation read the Knowledge Base directly?

**Answer**: Because that would bypass the evidence chain and the
governance gate. The recommendation must reference evidence_refs that
resolve to governed knowledge-evidence artifacts — the eval invariant
`provenance_recommendation_evidence` enforces this.

**Evidence**: P15 I5/I7; eval invariant dangles→FAIL.

**Code**: `runtime/eval_engine.py` provenance check.

**Test**: P15 HG-B06/B07; P16 RQ4.

**Risk**: LOW.

---

### Q10. Why fail-closed everywhere?

**Answer**: Insurance is a regulated domain. An agent that
hallucinates a coverage term or uses an expired regulation is worse
than one that says "I cannot answer". Fail-closed = the safe default
when information is missing, providers are down, or evidence is
insufficient.

**Evidence**: Abstention discipline (14.1); R-05 provider gate;
14.3 governance UNKNOWN→DENY.

**Test**: 14.6 abstention 5/5; 18 live G4 (7 provider-failure modes).

**Risk**: LOW.

---

## RAG / Knowledge

### Q11. Why WeKnora?

**Answer**: The project needed a real, open-source, self-hostable
knowledge infrastructure that provides document parsing, chunking,
hybrid retrieval, and reranking — so the agent doesn't reimplement
those. WeKnora is the retrieval backend, NOT the agent brain.

**Evidence**: Phase 18 report §02-03; WeKnoraLiveProvider only calls
POST /api/v1/knowledge-search.

**Risk**: MEDIUM — "why not [LangChain/LlamaIndex/custom]?" — answer:
the provider abstraction makes the backend swappable; WeKnora was
chosen for its Chinese document support + self-hosted deployment +
pure retrieval API separate from LLM answers.

---

### Q12. What does WeKnora vs the Agent each own?

**Answer**: WeKnora owns "find what" (parse, chunk, index, hybrid
retrieve, relevance-rank). The Agent owns "what evidence may inform
an insurance decision" (governance, authority, license, effective
window, provenance, evidence construction, domain eval).

**Evidence**: Phase 18 architecture diagram; governance registry is
the agent-side truth source.

**Risk**: LOW.

---

### Q13. Why not use WeKnora's Ask/ReAct?

**Answer**: Because that would put LLM-generated answers into the
evidence chain. The agent needs verbatim source passages it can
hash-verify and provenance-trace — not an LLM's summary of them.
WeKnora's Ask path is structurally unreachable from the provider.

**Evidence**: 14.1 C07; 18 G7 structural isolation tests.

**Risk**: LOW — this is a clear architectural boundary.

---

### Q14. What if WeKnora returns wrong results?

**Answer**: Three layers of defense: (1) the agent-side reranker
(SparseRetriever + DefaultReranker with the same externalized rules)
re-scores and filters by min_relevance; (2) governance validates every
hit against the agent registry; (3) eval catches unsupported claims.

**Evidence**: 18 G1 (agent-side rescoring); 14.6 contamination.

**Risk**: MEDIUM — "what if the RELEVANCE is wrong but passes
threshold?" — honest answer: that's a retrieval-quality gap, not a
governance gap; the eval dimensions measure it.

---

### Q15. What if WeKnora returns expired regulations?

**Answer**: The agent governance layer checks the effective window
(effective_from/effective_to vs as_of). Expired → DENY. This is tested
with real dates in the 14.3 suite and with live WeKnora in 18 G2.

**Evidence**: Governance R5 (window check); 14.3 GOV-003.

**Risk**: LOW.

---

### Q16. What if WeKnora returns unlicensed sources?

**Answer**: license_status UNKNOWN → DENY (governance R7). The
registry is the license truth source, not the backend metadata.

**Evidence**: 14.3 GOV-011/012; 18 G2 UNKNOWN-license live test.

**Risk**: LOW.

---

### Q17. Why does it work even though WeKnora lacks governance metadata?

**Answer**: The dual-identity model: WeKnora provides document/chunk
identity + content; the Agent Governance Registry provides authority/
license/window/version. The sync script builds a "projection registry"
(agent governance metadata + WeKnora chunk hashes). The provider
stamps governance fields from the registry (data projection, same
mechanism as the mock). Governance re-verifies — never trusts the
stamps.

**Evidence**: `sync_weknora_registry.py`; 18 G2 mutations all DENY.

**Risk**: MEDIUM — "what if the projection is stale?" — finding: the
sync must be re-run after WeKnora re-chunking (documented limitation).

---

### Q18. How do Mock and WeKnora backends stay interchangeable?

**Answer**: Both implement the KnowledgeProvider contract (search-only
interface); both produce canonical KnowledgeHit objects; both pass
through the same governance→evidence→provenance chain. The 18 G5
equivalence tests prove both produce valid hits through the same
validators.

**Evidence**: 14.1 C11; 18 G5 live equivalence.

**Limitation**: Chunk identity differs (mock uses sequential ids,
WeKnora uses UUIDs) — the registry is backend-specific (by design:
KB↔registry pairing).

**Risk**: LOW.

---

## Agent Engineering

### Q19. What if a Skill fails?

**Answer**: Eval→Repair (max 2 attempts)→NEEDS_REVIEW (human gate).
The task records failure_reason; the checkpoint preserves state; the
HITL/HOTL control planes allow human intervention.

**Evidence**: Phase 11 benchmark false-pass injection; repair logic.

**Test**: `test_failure_injection.py`; benchmark repair_success_rate.

**Risk**: LOW.

---

### Q20. What if the Agent crashes mid-run?

**Answer**: Checkpoint-based recovery. Artifacts + eval results +
task state are persisted per-stage; on restart, the checkpoint
validator (fingerprints) resumes from the last valid state.

**Evidence**: `runtime/checkpoint.py`; cross-process recovery suites.

**Test**: `test_cross_process_recovery.py`.

**Risk**: LOW.

---

### Q21. What if the user modifies a critical fact?

**Answer**: Contradictions are recorded in client-profile.conflicts[];
the run stops at the client-intake human-review gate (WAITING_FOR_USER)
— never silently picks a value.

**Evidence**: P16 contradiction cases (5/5 stop correctly);
orchestrator conflict handler.

**Test**: `test_p16_agent_quality.py` Q-CON cases.

**Risk**: LOW.

---

### Q22. What if two sources conflict?

**Answer**: The knowledge engine sets conflict=true and returns BOTH
sides (never auto-merges). The agent's decision layer sees the
conflict flag; governance doesn't resolve it — it surfaces it.

**Evidence**: 14.1 engine conflict detection (等待期 30 vs 90 天).

**Test**: 14.6 conflict detection case.

**Risk**: LOW.

---

### Q23. What if Evidence is insufficient?

**Answer**: The recommendation goes NEEDS_REVIEW or
INCOMPLETE_EVIDENCE — never a forced pick. The abstention discipline
is tested in 14.1 (insufficient_evidence status) and in the live
18 G6 (zero-overlap query → zero evidence).

**Evidence**: 14.1 C08; 15 R6; 18 G6.

**Risk**: LOW.

---

### Q24. How is LLM hallucination handled?

**Answer**: Structurally: the LLM only calls tools that produce
schema-validated artifacts; the tool stores engine chunks verbatim
(never LLM-generated text as evidence); empty retrieval fails closed.
The eval engine checks unsupported claims (benchmark 42/42 with
unsupported-claim-rate = 0).

**Evidence**: benchmark false-pass suite; tool fail-closed.

**Risk**: MEDIUM — "what about prompt injection?" — answer: the
deterministic pipeline never executes retrieved text as instructions;
the LLM tool-calling surface is bounded (schemas.py validates inputs).

---

### Q25. How do you prove the Agent didn't bypass Governance?

**Answer**: Structural tests (not just behavioral): the provider
package imports no runtime modules; the governance package imports no
provider implementation; no runtime module constructs a retrieval
engine. Mutation tests prove the evaluator catches bypasses.

**Evidence**: 14.4 bypass scan; 14.1 boundary scans; 17 evaluator-
independence scans.

**Test**: `test_p14_governance_runtime.py` bypass scan;
`test_p18_weknora.py` W1 seam audit.

**Risk**: LOW.

---

### Q26. How do you prove tests aren't "testing themselves"?

**Answer**: (1) The evaluators import production code but production
code never imports evaluators (scanned). (2) Mutation tests inject
defects and prove the evaluator catches them (M01-M08 in 16, M-AUTH
10/10 in 17, M-OBS 8/8 in 17). (3) The live WeKnora suite runs against
a REAL external service (not a mock of itself).

**Evidence**: 14.6 mutation detection; 16 mutations 8/8; 17 M-AUTH
10/10; 18 live suite 48/48.

**Risk**: LOW — this is a strong answer.

---

## Production

### Q27. What's missing for real Production?

**Answer**: (1) Production database (currently JSON/JSONL); (2) real
insurance product catalog; (3) verified LLM provider with real cost
measurement; (4) multi-tenant deployment; (5) production-scale
benchmark; (6) R-05 provider-policy operator verification; (7) event
log cryptographic chaining; (8) value-pattern credential redaction.

**Risk**: LOW — honest limitations are a strength in interviews.

---

### Q28. What breaks first at 100K cases/day?

**Answer**: (1) JSON-file persistence (no indexing, whole-file
rewrites under lock); (2) in-memory BM25 index (rebuilt per provider
instance); (3) single-process FileLock (no distributed locking);
(4) no message queue (synchronous processing).

**Risk**: LOW — knowing the bottleneck is the point.

---

### Q29. What is over-engineered?

**Answer**: See OVER_ENGINEERING_REVIEW.md. Short list: HOTL
ack-hysteresis (used in demos but not in the business chain);
Wiki/Graph KB capabilities (declined by the governance policy);
the domain-pack dual-corpus path (fixtures vs domain KBs).

**Risk**: MEDIUM — "would you simplify?" needs a confident answer.

---

### Q30. What would you do differently?

**Answer**: (1) Start with the governance registry schema FIRST, then
build retrieval around it; (2) use SQLite for the agent-side chunk
index from day one (WeKnora already does this internally); (3) collapse
the 14.3/14.4/14.5 phases into one "knowledge governance" milestone;
(4) the dual-corpus split (fixtures vs domain pack) was accidental
complexity.

**Risk**: LOW — self-awareness is valued.
