# Resume Project Description — Phase 20

Three versions: one-line, three-bullet, and interview-expanded.
All numbers are backed by code/test evidence.

---

## Version A — One Line

```
Evidence-grounded insurance Agent runtime with real WeKnora
integration, deterministic governance, and hash-anchored provenance
(456 tests, 42/42 benchmark, 42 adversarial attacks).
```

---

## Version B — Three Bullets

```
• Built an evidence-grounded insurance Agent runtime that separates
  LLM reasoning from deterministic governance: 9 schema-contracted
  skills, 9 governance rules, and a 4-hop provenance chain
  (decision → evidence → chunk → source), backed by 456 runtime
  tests and a 42/42 benchmark with unsupported-claim-rate = 0.

• Integrated WeKnora v0.8.0 as a swappable retrieval backend behind
  a provider abstraction — Mock and WeKnora are interchangeable below
  the KnowledgeHit boundary, with governance/evidence/provenance
  behavior unchanged (verified by 48 live integration checks and
  26 mutation tests proving the evaluator catches injected defects).

• Implemented fail-closed security: API-key authentication with
  OWNER/REVIEWER/OPERATOR RBAC, field-based PII redaction, Fernet
  encryption at rest, backup/restore with sha256 verification,
  retention with erasure audit — validated by a 98-case security
  evaluation with 10 authentication mutation tests.
```

---

## Version C — Interview Expanded

```
Project: Insurance Agent — Evidence-Grounded Agent Runtime

Problem:
A single LLM call cannot deliver insurance advice because it cannot
prove traceability (which regulation, which version), enforce
governance (is the source authoritative, licensed, current?), fail
closed (the LLM always answers), or recover from partial failure.
In a regulated domain, these are liability problems, not UX problems.

Architecture:
I built the execution layer — not another prompt. The system has 9
skills in a one-way data chain (FACT→REQ→RISK→GAP→SOLUTION→PRODUCT),
each producing a schema-validated artifact. A YAML-driven orchestrator
enforces ordering, artifact-freeze, and per-stage evaluation. A
bounded parallel DAG scheduler with checkpoint-based crash recovery
handles long-running workflows.

The knowledge layer uses a provider abstraction: Mock (deterministic
BM25 engine) for offline testing, WeKnora v0.8.0 (real HTTP retrieval
via Docker) for live integration. Both are interchangeable below the
KnowledgeHit boundary — governance, evidence, and provenance behavior
is identical regardless of backend.

Governance has 9 deterministic rules (authority S/A/B/C/D, license
ALLOWED/RESTRICTED/UNKNOWN, effective window, jurisdiction, version,
content hash, registry consistency, lifecycle, content). The
agent-side registry is the truth source — never the backend metadata.
UNKNOWN license never becomes ALLOWED; expired knowledge never grounds
current decisions.

Provenance has 10 rules (P001–P010) forming a hash-anchored 4-hop
chain: decision → evidence → knowledge chunk → document → version →
source. Tampering any byte in the content causes a hash mismatch
(P007) and the evidence is rejected — provably, not heuristically.

Evaluation:
456 runtime tests, 12 portfolio tests, 42/42 benchmark
(unsupported-claim-rate = 0), 42/42 adversarial attacks (knowledge,
agent, security, evaluation), 26/26 mutation tests proving the
evaluator catches injected defects, 98/98 security evaluation
(authentication, authorization, project isolation, PII redaction,
encryption, approval forging, provider policy, CORS), 48/48 live
WeKnora integration checks, and a 51-suite full regression.

Key design decisions:
• Skills, not one prompt: per-stage contracts enable structural
  non-interference (contamination invariant).
• Deterministic rules, no LLM judge: reproducible, testable,
  auditable — externalized *.rules.json.
• Provider abstraction: backend swap without agent-core changes.
• Fail-closed everywhere: "I don't know" > wrong answer in insurance.
• WeKnora = retrieval infrastructure, NOT the agent brain: the LLM
  answer path is structurally unreachable.

Honest limitations:
The product catalog is demo (12 fictional products). No production
database (JSON/JSONL). No real customer deployment. No production-
scale benchmark. LLM cost not measured (deterministic path: 0 LLM
calls). 7 P2 and 4 P3 findings documented, none blocking.
```
