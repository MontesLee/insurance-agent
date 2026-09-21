# Interview Q&A — Phase 20

30 questions, interview-spoken format (not audit language).
Adapted from INTERVIEW_ATTACK_SURFACE.md.

---

### Q1: Why not just use LangChain?

我不是反对 LangChain。这个项目真正想解决的问题不是"如何调用
LLM"，而是如何让 Agent 的知识、证据、治理和决策边界可验证。

所以我把 Knowledge Backend 做成 Provider abstraction，把
Governance / Evidence / Provenance 放在 Agent Core。如果未来使用
LangChain，它可以位于 Tool / Model integration 层，而不应该成为
整个系统的治理边界。

---

### Q2: Isn't this just if-else around an LLM?

Yes, exactly. And that's the point. For governance decisions —
"Is this source authoritative? Is this regulation still in force?
Is this license valid?" — deterministic rules are more reliable than
probabilistic LLM judgment. An insurance regulator will not accept
"the LLM thought it was authoritative."

---

### Q3: What if the LLM hallucinates?

Structurally prevented: the LLM only calls tools that produce
schema-validated artifacts. The tool stores engine-retrieved
verbatim chunks as evidence — never LLM-generated text. If retrieval
returns nothing, the tool fails closed. The benchmark proves
unsupported-claim-rate = 0 across 42 test cases.

---

### Q4: How do you know your tests aren't circular?

Three proofs: (1) Mutation testing — I inject defects (delete a
requirement, fabricate a product) and prove the evaluator catches
them (26/26). (2) Production code never imports evaluators (scanned
across runtime/, knowledge/, adapters/). (3) The live WeKnora tests
run against a real external service, not a mock of themselves.

---

### Q5: Why do you need 9 skills instead of one prompt?

Because a single prompt can't enforce the data-chain invariant
(FACT→REQ→RISK→GAP→SOLUTION→PRODUCT). Without enforced boundaries,
a risk analysis could silently embed a product recommendation.
Skills give per-stage contracts, eval boundaries, and structural
non-interference (the contamination invariant).

---

### Q6: Why not let the LLM decide the next step?

Because then I can't prove that a RISK artifact was always produced
from a complete CLIENT PROFILE, or that a PRODUCT was never
recommended before a GAP was computed. Deterministic orchestration +
deterministic eval = the "agent didn't cheat" proof.

---

### Q7: Why do you need Evidence AND Provenance?

Evidence says "this text supports the conclusion." Provenance says
"this text came from THIS source, at THIS version, valid at THIS
time, verified by THIS hash." Without provenance, you can't detect
tampering, check freshness, or audit which regulation version was
used.

---

### Q8: Why WeKnora and not a custom RAG pipeline?

I actually built a custom deterministic BM25 engine first (the Mock
provider). Then I integrated WeKnora to prove the provider
abstraction works with real infrastructure. WeKnora was chosen for:
open-source (MIT), self-hosted, Chinese document support, and a pure
retrieval API that's separate from its LLM-answer path.

---

### Q9: What if WeKnora returns expired regulations?

The governance layer checks effective_from/effective_to against the
query's as_of date. Expired → DENY. This is tested with real dates
and with live WeKnora hits.

---

### Q10: What if WeKnora returns unlicensed sources?

license_status UNKNOWN → DENY (governance rule R7). The registry
is the license truth source, not the backend metadata.

---

### Q11: Why doesn't WeKnora's lack of governance metadata break things?

Because I use a dual-identity model: WeKnora provides document/chunk
identity + content. The Agent Governance Registry provides authority/
license/window/version. The sync script builds a "projection registry"
(agent governance metadata + WeKnora chunk hashes). Governance
re-verifies — never trusts the stamps.

---

### Q12: How do Mock and WeKnora stay interchangeable?

Both implement the KnowledgeProvider protocol (search-only interface).
Both produce canonical KnowledgeHit objects. Both pass through the
same governance→evidence→provenance chain. The live equivalence tests
prove both produce valid hits through the same validators.

---

### Q13: What if a Skill fails?

Eval → Repair (max 2 attempts) → NEEDS_REVIEW (human gate). The task
records failure_reason; the checkpoint preserves state; HITL/HOTL
allows human intervention. This is tested in the failure-injection
suite and the benchmark repair-success metric.

---

### Q14: What if the Agent crashes mid-run?

Checkpoint-based recovery. Artifacts + eval results + task state are
persisted per-stage with fingerprints. On restart, the checkpoint
validator resumes from the last valid state. Tested cross-process.

---

### Q15: What if the user contradicts themselves?

Contradictions are recorded in client-profile.conflicts[]. The run
stops at the client-intake human-review gate (WAITING_FOR_USER) —
never silently picks a value. Tested with 5 contradiction cases.

---

### Q16: What if two knowledge sources conflict?

The retrieval engine sets conflict=true and returns BOTH sides —
never auto-merges. The agent's decision layer sees the conflict
flag; governance doesn't resolve it — it surfaces it.

---

### Q17: What if Evidence is insufficient?

The recommendation goes NEEDS_REVIEW or INCOMPLETE_EVIDENCE — never
a forced pick. The abstention discipline is tested live: a
zero-overlap query produces ZERO evidence even though WeKnora returns
keyword matches.

---

### Q18: How do you handle prompt injection?

The deterministic pipeline never executes retrieved text as
instructions. The LLM tool-calling surface is bounded (schemas.py
validates inputs). Retrieved content enters the evidence chain as
data, never as instructions.

---

### Q19: How do you prove the Agent didn't bypass Governance?

Structural tests (not just behavioral): the provider package imports
no runtime modules; the governance package imports no provider
implementation; no runtime module constructs a retrieval engine.
Mutation tests prove the evaluator catches bypasses.

---

### Q20: What's missing for real Production?

(1) Production database, (2) real insurance product catalog,
(3) verified LLM provider with real cost measurement, (4) multi-tenant
deployment, (5) production-scale benchmark, (6) R-05 provider-policy
operator verification, (7) event log cryptographic chaining.

---

### Q21: What breaks first at 100K cases/day?

(1) JSON-file persistence (no indexing, whole-file rewrites),
(2) in-memory BM25 index (rebuilt per provider instance), (3)
single-process FileLock (no distributed locking), (4) no message
queue.

---

### Q22: What's over-engineered?

Honestly: HOTL (impressive but not used in the business chain),
the domain-pack dual-corpus (accidental complexity), the overlap
between Phase 15 and 16 evaluators, and the parallel scheduler
(only matters at scale).

---

### Q23: What would you do differently?

Start with the governance registry schema FIRST. Use SQLite for the
agent-side chunk index from day one. Collapse 14.3/14.4/14.5 into
one milestone. The dual-corpus split was organic growth, not design.

---

### Q24: Why do you need Canonical Client State?

To prevent fact drift between skills. Without it, each skill could
re-interpret the client's words differently. The canonical state is
a single fact source with per-field status (KNOWN/UNKNOWN/ESTIMATED/
ASSUMED/INFERRED).

---

### Q25: Why can't Recommendation read the Knowledge Base directly?

Because that would bypass the evidence chain and the governance gate.
The recommendation must reference evidence_refs that resolve to
governed knowledge-evidence artifacts — the eval invariant enforces
this (dangling refs → FAIL).

---

### Q26: Why fail-closed everywhere?

In a regulated domain, a wrong answer is worse than no answer. An
agent that hallucinates a coverage term or uses an expired regulation
creates liability. "I don't know" is always better than a wrong
answer in insurance.

---

### Q27: How do you handle PII?

Field-based deny-list redaction on every event/log append (26
sensitive field names: name, phone, email, id_number, income, health,
bank_card, etc.). Tested with 12 PII cases. F-20: value-pattern
scanning is a known limitation.

---

### Q28: How does HITL work?

Approval gateway: REQUESTED → WAITING_HUMAN → APPROVED/REJECTED.
Only "human" actors can resolve — agents cannot self-approve.
Forged actors get ACTOR_NOT_AUTHORIZED. Tested with 13 approval
security cases.

---

### Q29: Show me a real provenance chain.

Three manually-verified chains in PROVENANCE_WALKTHROUGH.md: Case A
(valid evidence with hash match), Case B (1-byte tamper → P007 DENY),
Case C (zero-overlap query → abstention). Each walks from decision
to source with hash verification.

---

### Q30: Is this production-ready?

No. And here's exactly what's missing: 7 production gaps (database,
catalog, provider, multi-tenant, benchmark, operator verification,
event chaining). But the architecture — governance, evidence chain,
provenance — is designed for production and tested against real
infrastructure.
