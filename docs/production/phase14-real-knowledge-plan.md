# Phase 14 Real Insurance Knowledge — Architecture & Implementation Plan

Date: 2026-09-19 · Input: phase14-real-knowledge-audit.md (Rev 1,
code-measured) · Status: PLANNING ONLY — no code written.

> **REVISION 2 (2026-09-19) — supersedes the Rev-1 self-built-store
> design.** The governance content (sources, authority, windows, eval)
> survives retargeted; the infrastructure layer is now EXTERNAL.

---

## 0. Architecture Decision

```text
WeKnora            = External Knowledge Infrastructure
                     (parse / chunk / index / hybrid retrieve / relevance)
KnowledgeProvider  = Stable Boundary (the ONLY thing agents see)
Insurance Agent    = Knowledge Governance + Evidence + Provenance
                     + Domain Eval (what may inform an insurance decision)
Insurance Agent DB = DEFERRED (Stage 19 candidate; NOT Stage 14)
```

Hard boundary rules:

1. Agents NEVER see WeKnora SDK/HTTP. They see `KnowledgeProvider`.
2. The runtime-facing Provider is **read-only** (business-capability
   methods only). Ingestion is a separate operator-side port.
3. **Only WeKnora's RETRIEVAL surface is used.** Its LLM "Ask"/ReAct
   answer path is FORBIDDEN as an evidence source — the path
   `Agent → WeKnora Ask → WeKnora LLM answer → recommendation` is
   structurally impossible because the adapter does not expose it.
4. **WeKnora semantic relevance ≠ insurance business validity.** Every
   provider hit is governance-verified (window/authority/license/
   hash) before it can become Evidence.
5. Insurance Agent persistence stays JSON/JSONL + filesystem + R-01
   FileLock. No PostgreSQL/SQLite-new/Redis/queue; no CaseState/
   Harness/Approval/Artifact persistence change; no DB migration.

## 1. Stage 14 goal

> Every knowledge-backed statement in a recommendation/report traces to
> a REAL source, at a KNOWN version, within a KNOWN effective window,
> at a DECLARED authority — retrieved through a swappable external
> infrastructure, governed deterministically in-agent.

## 2. Target architecture

```text
Agent (knowledge_specialist / any stage via evidence loop)
  ↓ (unchanged: knowledge_search tool / evidence.loop)
Knowledge Tool / Evidence Provider seam        [KEEP — knowledge/evidence/*]
  ↓
KnowledgeProvider (Protocol)                   [NEW — the stable boundary]
  ├── MockKnowledgeProvider                    [wraps existing knowledge/rag
  │                                             engine + fixtures KB]
  ├── WeKnoraAdapter                           [POC in 14.2]
  └── future adapters (OpenSearch / pg / …)    [interface only, never built]
        ↓ retrieval-shaped hits
Insurance Knowledge Governance layer           [NEW — agent-side]
  source registry → authority/license/jurisdiction
  version registry → effective window / supersede / activation
  post-verification of every hit (fail-closed)
        ↓ verified citation tuple
Evidence (contract v1.1) → artifact_registry.evidence_refs   [KEEP+EXTEND]
        ↓
Recommendation / Report ← insurance-specific eval (freshness, authority,
                           completeness, provenance integrity, hallucination)
```

Provenance walk (all hops machine-resolvable):

```text
Recommendation → Evidence → KnowledgeHit(chunk) → Version → Source
```

## 3. KnowledgeProvider Contract (design; grounded in the REAL schemas)

The boundary sits exactly where `provider.build_engine()` sits today
(knowledge/evidence/provider.py:47-49): the seam already returns "an
engine with .search()" — the contract formalizes it. Shapes derive from
`contracts/knowledge-query.schema.json` (query/domain/purpose) and
`contracts/knowledge-evidence.schema.json` (status/evidence/conflict),
NOT from database verbs.

```python
class KnowledgeFilters:          # HINTS to the provider, not guarantees
    as_of: str | None            # default: now (ACTIVE versions only)
    allow_history: bool = False  # as_of queries tag results historical
    jurisdiction: str | None     # national | beijing | other_local
    authority_min: str | None    # floor, e.g. "B"
    source_types: list[str] | None
    domains: list[str] | None    # the contract's domain enum

class KnowledgeHit:              # retrieval-shaped + verification anchors
    chunk_id, document_id, version_id
    content, section
    score, retrieval_method      # provider's own relevance (informational)
    source_uri, content_hash     # verify the bytes that came back
    retrieved_at                 # freshness of OUR copy

class KnowledgeSearchResult:
    status        # success | partial_evidence | insufficient_evidence
    hits: list[KnowledgeHit]     # provider order = relevance only
    conflict: bool
    provider: str                # "mock" | "weknora" | …
    metadata: dict               # counts, method, provider diagnostics

class KnowledgeProvider(Protocol):
    name: str
    def search(self, query: str, filters: KnowledgeFilters | None,
               top_k: int = 10) -> KnowledgeSearchResult: ...
    def get_source(self, source_id: str) -> SourceRecord | None: ...
    def get_document(self, document_id: str) -> DocumentRecord | None: ...
    def get_version(self, version_id: str) -> VersionRecord | None: ...
    def resolve_evidence(self, hit: KnowledgeHit) -> EvidenceRecord | None:
        ...   # re-verify hash + window NOW (tamper/staleness check)

# Operator-side, NEVER agent-visible (used only by the 14.3 pipeline):
class KnowledgeIngestionPort(Protocol):
    def upload(self, manifest: IngestionManifest) -> IngestionReport: ...
    def retire(self, document_id: str, reason: str) -> None: ...
```

Design rules:

- **Business-capability interface, not a database interface**: no
  save/update/delete/query_database on the runtime Provider.
- **Filters are hints; governance verifies.** A provider MAY pre-filter
  by metadata (WeKnora supports it) for efficiency, but the agent-side
  layer re-checks window/authority/license on every hit and fails the
  hit closed on any mismatch. This is the structural enforcement of
  rule 4 in §0.
- **resolve_evidence exists so provenance integrity is a first-class
  operation**, not a test-only trick (chunk-hash re-verification).
- KnowledgeQuery/KnowledgeEvidence contracts stay the OUTER language;
  the provider contract is the INNER one. Adapter translates.

## 4. Field placement (every added field justified — nothing "for completeness")

| Field | Lives in | Why production needs it |
|---|---|---|
| `version_id` | KnowledgeHit + Evidence | "which edition of the law" — the audit's broken last hop (G5) |
| `effective_from` / `effective_to` | Evidence (from version registry) | was the content IN FORCE when used; expired knowledge must not ground current recommendations (G3) |
| `authority_level` | Evidence (from source registry) | deterministic S/A/B/C/D citation precedence and ranking |
| `source_uri` | KnowledgeHit | source volatility defense + human audit path (gov pages 404/JS — measured in R-05 probes) |
| `content_hash` | KnowledgeHit (+ stored per chunk) | tamper detection across an EXTERNAL roundtrip; makes "LLM said so" structurally unverifiable |
| `retrieved_at` | KnowledgeHit | staleness of our copy vs the live source |
| `jurisdiction` | Source registry (+ filter) | 医保 rules are jurisdictional; wrong-jurisdiction evidence is business-invalid |
| Provenance envelope (`source_type/source_id/field/confidence`) | unchanged contract | already sufficient; the deep walk resolves through registry records, not more envelope fields |

Rejected (no job): `knowledge_id` (document+version+chunk is a natural
3-level key), per-chunk `license` (belongs to Source), `topics`
(retrieval routing already covered by domain + section).

## 5. WeKnoraAdapter boundary

**Adapter DOES**: translate KnowledgeFilters → WeKnora query/metadata
parameters; call the RETRIEVAL API/MCP surface; normalize hits into
KnowledgeHit; join document/version ids with the agent-side registry;
report provider diagnostics.

**Adapter does NOT**: produce recommendations, risk analysis, product
selection, or any LLM answer; expose WeKnora's Ask/ReAct endpoints;
decide authority or validity; write to agent persistence.

```text
FORBIDDEN:  Agent → WeKnora Ask → WeKnora LLM answer → Recommendation
ACTUAL:     Agent → Provider.search() → WeKnora retrieval → raw hits
            → agent governance (window/authority/license/hash)
            → Evidence → agent reasoning
```

## 6. Effective date / version responsibility split

| Concern | Owner | Mechanism |
|---|---|---|
| Document / chunk / metadata storage & retrieval | WeKnora | its KB, its indexes |
| `effective_from/to`, supersede chain, status (FUTURE/ACTIVE/HISTORICAL/EXPIRED/RETIRED/DRAFT) | **Insurance Agent** | version registry (JSON, version-controlled) |
| as-of filtering | both | provider pre-filter (hint) + agent post-verification (authoritative) |
| authority, jurisdiction, license, production eligibility | **Insurance Agent** | source registry; UNKNOWN license ⇒ not citable |
| current vs historical citation | **Insurance Agent** | default as-of=now ACTIVE only; explicit as_of+allow_history tags `historical=true` |

The 2024-law-replaced-in-2026 scenario: a 2026 default query must not
ground on the 2024 edition — enforced TWICE (provider filter + agent
verification) and asserted by the freshness eval. Unparsable dates ⇒
version not ACTIVE (fail-closed, 宁可 UNKNOWN).

## 7. Authority model

- KEEP the existing deterministic S/A/B/C/D ladder (02-source-policy.md)
  and its rules-file weights — LLM never judges authority (true today,
  stays true).
- **Metadata location decision: agent-side registry is CANONICAL;
  WeKnora-side metadata is a PROJECTION** (source_id/version_id +
  copied attributes for pre-filter efficiency). Rationale: business
  validity must not live inside external infrastructure (lock-in,
  drift, no audit trail); pure agent-side kills pre-filtering
  performance. Adapter re-joins by id and DISTUSTS WeKnora-side
  attributes on conflict → hit dropped + warning (fail-closed, fixes
  audit G9).

## 8. Knowledge vs Product Catalog — separation preserved

WeKnora Knowledge holds 法律/法规/监管/医保/医疗/保险基础/行业知识/
条款解释资料. The Product Catalog (specific products: 保额/等待期/
免赔额/保障期限/续保/除外责任/健康告知/职业限制/投保年龄/有效期)
STAYS the structured JSON catalog + R-03 governance. **The catalog must
NOT be flattened into WeKnora documents** — product terms are
structured, versioned, eligibility-checked data, not prose to be
semi-retrieved; R-03's per-field governance and the
`catalog_exists`/`contamination` invariants depend on structure.

## 9. Real-source governance (production Evidence necessary conditions)

A hit may ground production output ONLY IF ALL hold (machine-checked):

1. source registered (publisher, source_type, jurisdiction, base_uri);
2. `license_status = VERIFIED_ALLOWED` — UNKNOWN never inferred as
   ALLOWED; FORBIDDEN never ingested;
3. version ACTIVE in window at generation time (as-of verified);
4. authority_level inherited from the registry (ingest-time
   contradiction with the registry fails closed);
5. content_hash verifies; retrieved_at recorded;
6. human activation action logged (append-only knowledge audit log —
   the erasure.log pattern; agents cannot activate, structurally).

## 10. R-05 — unchanged

`INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED` gate stands BLOCKED for real
client data (data_policy.py:55). Stage 14 adds an external knowledge
service but sends NO client data to it: queries are template-generated
(domain, purpose) or agent-composed KNOWLEDGE questions; evidence
rounds are read-only. WeKnora deployment is operator infrastructure —
its own trust posture is an operator review item in 14.2 POC, same
discipline as provider-policy-verification.md.

## 11. Deferred Infrastructure (explicitly NOT Stage 14)

```text
PostgreSQL / any Insurance Agent database migration   → Stage 19 candidate
Redis                                                 → not planned
Message queue                                         → not planned
Vector DB owned by the Insurance Agent                → replaced by WeKnora
Object storage                                        → not planned
Multi-node persistence / distributed scheduler        → not planned
Embedding/rerank self-hosting                         → cancelled (WeKnora)
```

WeKnora may internally use PostgreSQL/Redis/vector infrastructure —
that is ITS implementation detail behind the KnowledgeProvider
boundary and does NOT constitute an Insurance Agent persistence
migration. The agent talks to it through the adapter only.

## 12. Phased plan (each phase: Goal/Scope/Non-goals/Implementation/
## Tests/Exit/Risks/Rollback)

Sequencing: 14.1 → 14.2 strictly ordered; 14.3 → 14.4 ordered
(registry before enforcement); 14.5 after 14.4; 14.6 before 14.7.

### 14.1 KnowledgeProvider Contract

- **Goal**: the stable boundary exists; upper layers are backend-blind.
- **Scope**: KnowledgeProvider Protocol + record types;
  MockKnowledgeProvider (wraps the EXISTING knowledge/rag engine +
  fixtures/domain-pack KBs); contract tests; WeKnoraAdapter INTERFACE
  (empty impl). One seam change: the evidence provider/tool acquire
  the engine THROUGH the Provider (build_engine swap).
- **Non-goals**: no WeKnora code, no DB, no runtime rework, no real
  knowledge, no schema changes yet.
- **Tests**: existing knowledge-contract suites run unchanged against
  the mock; a swap test proves the seam (mock ↔ stub) with zero
  upper-layer test change; structural test that agents import
  Provider only.
- **Exit**: `Agent → KnowledgeProvider → Mock` passes ALL existing
  knowledge contract tests; battery unchanged (397/12/51-0-1/42).
- **Risks**: seam regression in provider.py — mitigated by the
  contract-test fleet. **Rollback**: revert the single seam; delete
  the new module.

### 14.2 WeKnora Adapter POC (only after 14.1 passes)

- **Goal**: prove the path
  `Provider → WeKnoraAdapter → WeKnora → hybrid search → normalized
  hits → existing eval`, on a TINY test KB.
- **Scope**: standalone WeKnora deployment (operator, docker);
  ≤10 synthetic test documents; adapter retrieval-surface
  implementation (NO Ask/ReAct); id/metadata round-trip verification;
  latency/offline characterization; integration tests marked
  INFRA-gated (a missing WeKnora = skip/INFRA, never FAIL — the GBK
  INFRA_ERROR precedent).
- **Non-goals**: no real insurance knowledge, no client data, no
  production deployment decision, no agent changes.
- **Exit**: normalized hits validate against the provider contract;
  existing retrieval evals pass over WeKnora results; Ask-path
  non-exposure proven structurally; POC report with go/no-go inputs.
- **Risks**: API/version drift; Chinese retrieval quality unknown at
  our term-precision — measured here on purpose.
- **Rollback**: delete adapter impl; mock remains the default.

### 14.3 Real Knowledge Ingestion (governance-first)

- **Goal**: operator-curated REAL documents enter through governance.
- **Scope**: source registry format + license verification records +
  UNKNOWN-default enforcement; IngestionPort manifest pipeline
  (validate → hash → chunk-hash → registry version DRAFT → operator
  activation → adapter upload); append-only activation audit log.
- **Non-goals**: crawling, bulk import, scheduling, LLM activation.
- **Exit**: license-UNKNOWN source cannot reach ACTIVE (negative
  test); tampered file fails ingest; activation is operator-only
  (structural); DRAFT not retrievable by default.
- **Risks**: license misjudgment — human verification records
  required. **Rollback**: registry/manifests are additive files.

### 14.4 Insurance Knowledge Governance

- **Goal**: the validity layer — filters verified, not trusted.
- **Scope**: version registry + status machine + supersede chain;
  as-of/jurisdiction/authority post-verification of every provider
  hit; deterministic governance post-rank (S/A/B/C/D weights from the
  existing rules files); registry↔WeKnora metadata consistency check
  (mismatch → hit dropped, warning logged).
- **Exit**: the 2024/2026 replacement scenario test (default query
  returns only the new edition; as_of=2025 returns the old, tagged
  historical); unparsable date ⇒ not ACTIVE; authority mismatch
  fails closed.
- **Risks**: split-brain metadata (double enforcement + consistency
  eval). **Rollback**: governance layer is additive; provider falls
  back to raw hits only in MOCK mode (never production).

### 14.5 Evidence / Provenance Integration

- **Goal**: close the last hop.
- **Scope**: knowledge-evidence contract v1.1 (§4 fields; OPTIONAL
  ids become REQUIRED); producers/adapters updated; resolve_evidence
  wired into provenance invariants; artifact records the as-of window
  used (replayable check).
- **Exit**: dangling version/hash → eval FAIL (negative tests);
  4-hop walk machine-resolvable end to end; traceability suite
  generalized.
- **Risks**: contract break for producers — adapter-level change,
  contract fleet as net. **Rollback**: v1.0 contract restored; new
  fields optional again.

### 14.6 Knowledge Evaluation

- **Goal**: the five governance dimensions, machine-checkable.
- **Scope**: freshness / authority / evidence-completeness /
  provenance-integrity / hallucination (§12 of Rev-1 plan, unchanged
  content) + negative self-checks + threshold re-baselining with
  recorded before/after; provider-agnostic where possible (run
  against mock; WeKnora integration evals INFRA-gated).
- **Exit**: all dimensions green; injected-staleness and
  removed-fact round-trip go red then green.

### 14.7 Real Knowledge Pilot

- **Goal**: end-to-end with REAL sources.
- **Scope**: ≤10 verified documents (national law + regulator public
  file + 医保 document), human license verification, activation,
  one full run whose report provenance walks Recommendation →
  Evidence → Version → Source with hashes verifying; R-05 STILL
  BLOCKED (asserted unchanged).
- **Exit**: pilot report; zero client data leaves the agent;
  governance audit complete.

## 13. Top-5 technical risks (revised for the WeKnora decision)

1. **External-infra dependency** — regression cannot require a live
   WeKnora: mock-first contract tests; integration tests INFRA-gated;
   adapter version-pinned.
2. **Validity leakage** — trusting WeKnora relevance/metadata as
   business validity: post-verification of every hit + registry
   canonical (§7) + consistency eval.
3. **Metadata split-brain** (registry vs WeKnora projection): both-side
   enforcement; mismatch drops the hit fail-closed.
4. **Ask-path misuse** (LLM answer smuggled in as evidence):
   structurally unexposed + hash-verification makes prose unverifiable
   as a chunk.
5. **License/copyright** (unchanged): UNKNOWN default, human
   verification gate before any ACTIVE.

## 14. Recommendation

```text
READY TO PLAN-APPROVE Stage 14 Rev 2: 14.1 → 14.7 as above.
```

The retrieval infrastructure is bought, not built; every remaining
phase is governance, evidence, or evaluation — the parts that make
knowledge SAFE for insurance decisions, and the parts this codebase
already knows how to build deterministically.
