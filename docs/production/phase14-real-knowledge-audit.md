# Phase 14 Real Insurance Knowledge — Audit (read-only, 2026-09-19)

> **REVISION 1 (2026-09-19, same day — WeKnora architecture decision).**
> After the initial audit below, the project decided NOT to keep
> building self-hosted RAG/knowledge infrastructure, and to adopt
> **Tencent WeKnora as the EXTERNAL knowledge infrastructure**. §12
> (appended) maps every self-built capability to KEEP /
> REPLACE_BY_WEKNORA / WRAP / DEFER. Findings G1–G10 remain valid —
> what changes is the RESPONSE: governance over an external retrieval
> surface instead of building our own storage/retrieval stack. WeKnora
> facts verified from its public materials on 2026-09-19: open-source
> (23.7k+ stars), multi-format document parsing (PDF/Word/image,
> Feishu/Notion sources), semantic + hybrid retrieval, rerank,
> citation-traced Q&A, ReAct agent mode, MCP support, private
> deployment. Note it offers BOTH a retrieval surface AND an LLM "Ask"
> surface — Stage 14 must use ONLY the retrieval surface (plan §9).

Baseline at audit time: Stage 1 frozen @ 87eda85; runtime 397 / portfolio
12 / regression 51-0-1 / benchmark 42-42 / compileall PASS; git working
tree CLEAN. Every claim below carries a code citation — this audit was
performed against CODE, not against documentation.

---

## 1. Current Knowledge Architecture (as measured)

Three layers exist today, plus a workflow-level integration contract:

```text
┌─ Skill layer ──────────────────────────────────────────────────────┐
│ .trae/skills/knowledge-search/  (SKILL.md + 3 references +         │
│   resources/config/{retrieval,ranking}.rules.json + schemas +      │
│   evals/eval-policy.md + scripts/invoke-knowledge-search.py)       │
└────────────────────────────────────────────────────────────────────┘
┌─ Engine layer ─────────────────────────────────────────────────────┐
│ knowledge/rag/    models.py(80) store.py(131) engine.py(306)      │
│ knowledge/evidence/ provider.py(request/response seam, contracts)  │
│                    request.py(template KnowledgeQuery)             │
│                    loop.py(read-only evidence round)               │
│                    attribute_grounding.py(attribute-level verdicts)│
└────────────────────────────────────────────────────────────────────┘
┌─ Runtime integration ──────────────────────────────────────────────┐
│ runtime/insurance-analysis.yaml:142-152 — knowledge-search is a    │
│   shared SERVICE (kind: evidence-provider), deliberately NOT a     │
│   stage; "Evidence != Recommendation" is a stated principle        │
│ runtime/orchestrator.py:189-249 — _run_stage_services runs the     │
│   loop for the product-candidate-provider stage (SOLUTION_         │
│   VALIDATION), evals the evidence artifact, FAIL blocks the stage  │
│ runtime/agent/tools.py:325-409 — knowledge_search TOOL for the     │
│   LLM agent (intent-routed GENERAL_KNOWLEDGE → tool, prompts.py:   │
│   14-37); fail-closed on empty RAG ("cannot fabricate knowledge")  │
│ runtime/agents/registry.py:50-71 — knowledge_specialist agent:     │
│   ONLY task knowledge_search, ONLY tool knowledge_search           │
└────────────────────────────────────────────────────────────────────┘
```

## 2. What Knowledge Search actually IS (Audit 1)

**Input** — canonical KnowledgeQuery (`contracts/knowledge-query.schema.json`):
`query` + `domain`(enum 6) + `purpose`(enum 7), built by TEMPLATE from
(domain, purpose) via `evidence-request.rules.json` — no free-text
injection (knowledge/evidence/request.py:46-52). The LLM-agent path
passes a raw `query` string (max 200 chars, tools.py:507 +
agent/schemas.py:161-171).

**Output** — canonical KnowledgeEvidence artifact
(`contracts/knowledge-evidence.schema.json`): payload
`{status, query, evidence[], conflict}` where status ∈
success/partial_evidence/insufficient_evidence/retrieval_error;
evidence items carry `evidence_id/content/source/relevance/confidence`
(REQUIRED) and `document_id/chunk_id/section/source_level/...`
(OPTIONAL — see gap G5).

**Pipeline (knowledge/rag/engine.py)**:

```text
Query → normalize (filler strip + trigram)          engine.py:24-27
      → SparseRetriever (trigram-BM25, pure Python, engine.py:30-77)
      → [DenseRetriever — INTERFACE ONLY, dense_enabled=false]  :80-104
      → RRF fusion (hook ready, engine.py:107-116)
      → DefaultReranker — deterministic weighted:                :170-210
          keyword .35 / source .25 / domain .20 / semantic .10 /
          specificity .10; source_level → quality S1.0/A.85/B.65/C.45/D.2
      → evidence filter (min_relevance 0.55, partial 0.70)
      → status + conflict (regex on conflict_keys: 等待期/免赔额/赔付比例)
```

Verdict on the checklist questions:

| Question | Answer |
|---|---|
| Truly RAG? | **Half**: retrieval + deterministic rerank, **no generation** — by design (evidence, not answers). Embedding: NO (interface stub only). Vector store: NO. |
| Data source | 6 synthetic markdown fixtures (below) |
| Metadata filtering | YES — exact-match AND filters (`store.filtered_chunks`, store.py:114-124; SparseRetriever honors `filters`, engine.py:48-52) |
| version | field EXISTS on Chunk (models.py:19, store schema :76) but **never populated by ingest and never read by retrieval** |
| effective_from / effective_to | `effective_date` EXISTS, same fate; **`effective_to` does not exist at all** |
| jurisdiction | **absent** |
| source authority | `source_level` S/A/B/C/D EXISTS, feeds rerank weight 0.25 deterministically — but is an unchecked ingest argument (G9) |
| evidence citation | chunk_id + document_id + section (citation to a TEST fixture) — no hash, no URL, no version |

**Current data flow:**

```text
Query ──► normalize ──► BM25 over 6 synthetic docs (in-memory SQLite)
      ──► deterministic rerank (source_level weighted)
      ──► threshold filter ──► Evidence {chunk_id, document_id, section,
                                       content, scores}
      ──► canonical artifact ──► CaseState + artifact_registry
      ──► consumed by solution / product-recommendation stages
```

## 3. Knowledge vs Product Catalog boundary (Audit 2)

**Genuinely separated, by construction:**

| | Knowledge | Product Catalog |
|---|---|---|
| Store | `.trae/skills/knowledge-search/evals/fixtures/kb/*.md` (+ domain pack, below) | `catalog/product-catalog.v0.1.json` |
| Content | concept/regulation/claims knowledge chunks | 12 fictional products with `product_version`, per-product `effective_from`, `is_demo:true` (catalog README: all fictional) |
| Access path | knowledge_search tool / evidence-provider service | product-candidate-provider skill + check_catalog_product tool; membership enforced by eval invariant `catalog_exists` + R-03 |
| Question fit | "什么是百万医疗险/等待期/既往症" → KB answers | "P001 的免赔额/投保年龄/续保" → catalog answers |

The `contamination` eval invariant (eval.rules.json:30-35) actively
enforces the boundary in the OTHER direction: upstream analysis
artifacts must not leak catalog product ids/names/companies.
**Verdict: Knowledge ≠ Product Catalog is REAL — but BOTH sides are
synthetic.**

## 4. Evidence / Provenance state (Audit 7)

What exists and works (all test-proven):

- **Artifact fingerprints**: sha256 of canonical JSON
  (runtime/state/transitions.py:23-28); `artifact_registry.verify()`
  re-hashes content vs fingerprint (artifact_registry.py:118-136) —
  tamper detection at the artifact level.
- **Lineage**: artifact→artifact via `input_artifacts` (DFS walk,
  artifact_registry.py:97-110); artifact→knowledge via `evidence_refs`
  collected recursively from payloads (:30-43).
- **Eval invariants** (runtime/resources/config/eval.rules.json):
  `provenance_evidence_document_chunk` (every evidence item carries
  evidence_id/document_id/chunk_id — chunk fields are enforced HERE,
  compensating for the contract's optional fields),
  `provenance_recommendation_evidence` (recommendation evidence_refs
  must resolve inside the stored knowledge-evidence artifact — dangling
  refs FAIL), `required_non_empty` (empty evidence FAILs, not passes).
- **Attribute grounding** (knowledge/evidence/attribute_grounding.py):
  Product-attribute → evidence-chunk → SUPPORTED/UNSUPPORTED/CONFLICT
  with NOT_CHECKABLE as an independent third state; deterministic,
  rules-externalized.
- **LLM-fact separation**: the tool stores engine chunks verbatim;
  prompts forbid invention; empty RAG fails closed; the honesty rule
  (eval_engine.py:15-18) makes un-evaluable checks FAIL, never PASS.
  "LLM said it → became Evidence" has no code path TODAY.

The chain as it stands:

```text
Recommendation ─(evidence_refs)─► Evidence artifact ─(chunk_id)─► Chunk
      ✓ resolvable            ✓ fingerprint-verified      ✓ in-store
                                                          ✗ no version
                                                          ✗ no effective window
                                                          ✗ no source URL / publisher
                                                          ✗ no content hash at chunk level
                                                          ✗ chunk resolves into a TEST FIXTURE
```

**The chain breaks at the last hop**: Evidence cannot answer "which
VERSION of WHICH source, effective WHEN, obtained WHERE, verifiable by
WHAT hash". Those attributes do not exist in the data model (G2/G5).

## 5. Current gaps (numbered, evidence-backed)

- **G1 — No real knowledge.** Runtime default KB =
  `.trae/skills/knowledge-search/evals/fixtures/kb/` — 6 files, **87
  lines total**, self-labelled "本文件为单元测试用最小知识库". The
  richer `domain/insurance/references/` pack (7 docs) is also
  project-authored fiction ("权威生产语料" is a role label, not a real
  source).
- **G2 — No Document/Version entities.** Chunks are flat rows; no
  document lifecycle, no version chain, no supersede link. Chunk model
  HAS `created_at/effective_date/version` columns
  (models.py:17-19) that default ingest leaves EMPTY (store.py:89-104).
- **G3 — Retrieval is time-blind.** `engine.search()` never reads
  effective_date/version. The source POLICY says "优先 effective_date
  较新…无时效信息时不因此降权" (references/02-source-policy.md) —
  **a policy-implementation gap**: documented, unimplemented. An
  expired regulation outranks a current one purely by trigram overlap.
- **G4 — Two KBs, two ingestion paths, wrong default.** Runtime
  (agent tool + provider) defaults to the FIXTURES KB; the domain-pack
  engine (with front-matter metadata) is used only by domain scripts
  and one contract test. Real knowledge dropped into the domain pack
  would NOT reach the runtime agent.
- **G5 — Thin provenance contract.** `knowledge-evidence.schema.json`:
  document_id/chunk_id/source_level are OPTIONAL on evidence items;
  provenance entries require only source_type/source_id/confidence. No
  version, no effective window, no URI, no hash. (A regression of
  exactly this kind — adapter dropping ids — already happened once;
  test_knowledge_evidence_traceability.py exists as the guard.)
- **G6 — No ingestion/activation governance.** Ingestion is a manual
  `ingest_dir()` call; there is no ACTIVE state, no operator gate, no
  diff step. Nothing answers "who let this version into production".
- **G7 — No source governance.** No source registry, no license
  recording, no crawl-policy audit, no UNKNOWN-by-default rule.
- **G8 — Knowledge eval lacks governance dimensions.** Existing 7
  dimensions (recall/precision/ranking/source-priority/abstention/
  conflict/metadata-filter, evals/eval-policy.md) cover retrieval
  quality; MISSING: freshness, authority-completeness, evidence
  completeness per conclusion, provenance-integrity (version resolves
  + hash verifies), hallucination (downstream cites non-existent
  knowledge).
- **G9 — Authority labels are unverifiable.** source_level is an
  ingest-time argument with no registry behind it; a mislabeled "S"
  gets a 1.0 source weight and citation precedence.
- **G10 — Conflict detection is narrow.** Regex over three numeric
  keys (等待期/免赔额/赔付比例, engine.py:294-306) — adequate for the
  fixtures, not for regulation-level conflicts.

## 6. Real-knowledge source state

**Zero real sources ingested.** Everything retrievable today is
project-authored. No URL, publisher, license, or retrieval date
survives into evidence. The metadata PATTERN already exists in the
domain pack front-matter
(`<!-- domain-pack: version=1.0 effective_date=2026-09-14
source_level=B code=medical -->`, parsed by
domain/insurance/scripts/build_domain_engine.py:34-65, validated by
validate_pack.py) — the pattern is reusable; the content behind it is
not real yet.

## 7. R-05 provider-policy gate state

Unchanged and fail-closed: `runtime/agent/data_policy.py:55` —
real client data without
`INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1` returns
`PROVIDER_POLICY_UNVERIFIED: real client data is BLOCKED`. Stage 14
planning does not touch this gate; the 451 server-side gate
(server.py, P0 round) also stands. **No bypass introduced by the
knowledge work** (the RAG engine is local, deterministic, and offline).

## 8. Risks of introducing real insurance data

1. **Copyright / compilation rights** — PRC statutes and regulations
   are themselves not copyright-protected, but COMPILATIONS, official
   databases, re-typeset texts, and commercial digests may be; site
   terms and robots policies vary. Per the audit rules: every source's
   license status starts **UNKNOWN**, never assumed ALLOWED.
2. **Version/regime confusion** — a superseded regulation still
   retrievable as current directly corrupts client recommendations
   (highest-severity correctness risk; G3).
3. **Authority mislabeling** — an "S" stamp on a secondary source
   distorts ranking AND citation trust (G9).
4. **Source volatility** — government pages move/JS-render (already
   measured for R-05 probes: 404/SPA); `retrieved_at` + content hash
   are the only defense.
5. **Over-trust in small corpora** — a 6-doc KB with confident
   abstention thresholds tuned on it will either over-abstain or
   over-answer on a real corpus; thresholds must be re-baselined.

## 9. Capabilities that ALREADY exist (reuse list)

- Deterministic retrieval skeleton: BM25-sparse + RRF hook +
  rules-externalized rerank (no LLM anywhere in the path).
- Abstention discipline (insufficient_evidence, fail-closed tool,
  empty-KB benchmark mode at test-cases/e2e/full-agent/kb-empty).
- Canonical contracts + jsonschema validation on BOTH request and
  response (knowledge/evidence/provider.py:58-100).
- Attribute-level grounding with an independent NOT_CHECKABLE state.
- Artifact fingerprints + lineage + evidence_refs + the
  provenance eval invariants (incl. dangling-ref FAIL).
- R-03 catalog_governance as a GOVERNANCE PATTERN to mirror:
  mode separation, effective-window checks, per-item evidence block,
  fail-closed validate-at-load, `catalog_provenance` traceability
  (runtime/catalog_governance.py:41-156) — knowledge governance can be
  its structural sibling.
- Domain-pack front-matter marker + parser + pack validator.
- Eval discipline (machine-checkable only, negative self-checks —
  AGENTS.md §6) and the deterministic-first rule (§5).
- Test fleet: test_knowledge_evidence.py (T1-T9),
  tests/evidence/* invariants+dataset, tests/contracts/* (incl.
  traceability), workflow grounding/catalog-version suites, test_p0_r03.

## 10. Capabilities that must NOT be rebuilt (duplication risks)

| Do NOT build | Because |
|---|---|
| A new retrieval engine / new RAG framework | knowledge/rag/engine.py + externalized rules already fill it; extend, don't replace |
| A second evidence-provider seam | knowledge/evidence/provider.py + loop.py are the single seam (yaml declares it) |
| A vector DB / embedding service | dense interface reserved (engine.py:80-104); not needed at pilot corpus scale; explicitly out of Stage 14 |
| A "real database" migration | stdlib sqlite as chunk index is already the codebase state and sufficient; no Postgres/Redis/queue (Stage-14 boundary) |
| A new product catalog or catalog governance | catalog + R-03 are done; knowledge governance should MIRROR the pattern, not duplicate its code |
| A new provenance system | extend artifact_registry.evidence_refs + the two provenance invariants |
| Scheduler/runtime semantic changes | knowledge stays a service + tool; runtime semantics frozen since v0.1.0 |
| Automatic web crawling / bulk download | forbidden by Stage-14 boundary; ingestion is operator-authored |

## 11. Answers required by the brief (condensed)

- **Audit 5 (authority)**: a deterministic S/A/B/C/D model ALREADY
  exists in policy+rules and is already deterministically applied in
  ranking (DefaultReranker). What's missing is the REGISTRY that makes
  a label verifiable, and a rule that ingest cannot invent labels.
  LLM never decides authority today — keep it that way.
- **Audit 6 (validity)**: Current/Historical/Expired/Future/Unknown
  states DO NOT exist; retrieval must default to as-of-now ACTIVE only,
  with historical access only via explicit as_of (design in the plan).
- **Audit 8 (RAG options)**: Option B (metadata filter → keyword →
  existing sparse search) is the right Stage-14 shape — insurance
  queries are term-precise and window/jurisdiction-constrained;
  embeddings are optional later through the reserved dense interface.
- **Audit 10 (integration)**: knowledge_specialist must stay
  Query→Retrieval→Evidence (its registry entry already restricts it to
  exactly that); reasoning stays with the consuming agents. Current
  code already enforces this — preserve it.
- **Audit 12 (data risk)**: license/robots/status per source recorded
  at ingestion, default UNKNOWN, human-confirmed before any
  production ACTIVE.

**Verdict feeding the plan**: the engine, contracts, grounding,
invariants and eval discipline are solid and reusable; the missing 80%
is GOVERNANCE (documents/versions/sources/licenses/activation) and the
last provenance hop — not retrieval technology.

---

## 12. WeKnora capability mapping (Revision 1)

Decision principle: **if WeKnora already provides a mature capability,
the Insurance Agent must not maintain a second implementation** — but
anything that decides INSURANCE BUSINESS VALIDITY stays agent-side.

| Current self-built capability (code) | Verdict | Rationale |
|---|---|---|
| Document ingestion (`store.ingest_file/dir`) | **REPLACE_BY_WEKNORA** (production path) | WeKnora's upload/parse pipeline (PDF/Word/image) is mature; our path stays ONLY inside the Mock provider for tests |
| Document parsing | **REPLACE_BY_WEKNORA** | we ingest markdown by hand today; real corpora are PDF/Word |
| Chunking (`chunk_markdown`, heading-aware) | **REPLACE_BY_WEKNORA** | WeKnora chunks internally; our chunker remains only as the mock's fixture tooling |
| Keyword search / trigram-BM25 (`SparseRetriever`) | **REPLACE_BY_WEKNORA** for production; **KEEP as MockKnowledgeProvider's engine** | production retrieval goes to WeKnora hybrid; the local engine's second life = offline, deterministic mock (regression must never need a live WeKnora) |
| Embedding (`DenseRetriever` stub) | **REPLACE_BY_WEKNORA** (self-build CANCELLED) | the never-implemented stub is exactly what we no longer need |
| Vector search | **REPLACE_BY_WEKNORA** | ditto |
| Hybrid search + RRF (`rrf_fuse`) | **REPLACE_BY_WEKNORA** | WeKnora hybrid retrieval; RRF hook dies with the dense route |
| Relevance rerank (`DefaultReranker`) | **SPLIT**: relevance half → **REPLACE_BY_WEKNORA**; governance half (source_level weighting, window/authority pruning) → **KEEP** (thin deterministic post-rank) | WeKnora optimizes semantic relevance; it must never define business ordering. The S/A/B/C/D-weighted, rules-externalized post-rank stays ours and runs on PROVIDER-AGNOSTIC results |
| Document storage / KB management | **REPLACE_BY_WEKNORA** | KB lifecycle is WeKnora's core product |
| Knowledge update | **WRAP** | WeKnora versions inside its KB; the agent keeps the governance mirror (version registry, activation, supersede, license) — WeKnora cannot know insurance effective-window semantics |
| Evidence/provider seam (`knowledge/evidence/*`, contracts, attribute grounding) | **KEEP** | this IS the governance + evidence layer, not infrastructure |
| Authority model (S/A/B/C/D) | **KEEP** (agent-side registry canonical; WeKnora metadata = projection only) | §13 below |
| Effective-date / jurisdiction / eligibility | **KEEP** (agent-side) | "WeKnora semantic relevance ≠ insurance business validity" — the load-bearing rule |

### 13. Ownership boundary (one line each side)

- **WeKnora owns "找什么"**: parse, chunk, index, hybrid-retrieve,
  relevance-rank documents that WE uploaded.
- **Insurance Agent owns "什么证据可以用于保险业务决策"**: source
  registry (authority/license/jurisdiction), version + effective-window
  governance, production eligibility (UNKNOWN ⇒ not citable),
  evidence contracts, provenance, domain eval, agent integration.
- **Insurance Agent persistence stays JSON/JSONL + FileLock** — no
  PostgreSQL/SQLite-new/Redis/queue; WeKnora's INTERNAL infrastructure
  (whatever databases it uses) is behind the boundary and is NOT an
  Insurance Agent database migration (plan §14 Deferred Infrastructure).
