# Phase 24 Result — Production Knowledge / WeKnora Productionization

Date: 2026-09-21 · Full regression 494/12/42 all green · Live evaluation 33/33.

## PHASE 24 RESULT
================

Status:

```
PRODUCTION_KNOWLEDGE_READY_WITH_DOCUMENTED_DEBT
```

Architecture:

```
Question
  → KnowledgeService (ONE composition — K001..K004)
  → WeKnoraLiveProvider (pure search endpoint only)
      └─ F-24 re-anchoring: window → canonical registered chunk
  → KnowledgeHit (chunk_id, content, hash)
  → PostgreSQL Governance Registry (authoritative, strict modes)
  → Governance R1..R9 + R2b (deterministic, fail-closed)
  → Evidence (full citation tuple + governance block)
  → Provenance P001–P010 (every hop re-derived)
  → Decision
```

KnowledgeProvider: `knowledge/provider/` — mock (offline) and
WeKnoraLiveProvider under the unchanged `KnowledgeProvider.search()`
contract. Ask/ReAct/`knowledge-chat` structurally unreachable.

WeKnora: v0.8.0 Docker, real HTTP retrieval, verified restart-
persistent (`docker restart` → identical hits, chunk ids, content
hashes). Backup: `pg_dump -U postgres -d WeKnora | gzip` verified
(275 KB) — operator procedure, scheduling deferred.

Governance Registry: PostgreSQL authoritative in strict modes
(HG-24-02); lifecycle state machine DISCOVERED→INGESTED→REGISTERED→
VALIDATED→ACTIVE with guarded transitions; JSON registries remain the
non-strict default (unchanged since 14.3/18).

PostgreSQL: same instance as the Phase 22 business persistence;
knowledge tables extended idempotently (ADD COLUMN IF NOT EXISTS).

Evidence: full citation tuple (source/version/window/authority/
jurisdiction/license/hash/retrieved_at); only governance-ALLOWED hits
become evidence.

Provenance: P001–P010 re-derive every hop against the registry;
validated per-item over live evidence (33/33 suite).

24A Registry:
PASS — `KnowledgeRegistryStore` (knowledge/governance/pg_registry.py),
ingestion pipeline (knowledge/pilot/ingest_registry_pg.py), 16/16 real
documents ACTIVE (6 fixtures + 10 pilot regulations incl. the
78-chunk 互联网保险业务监管办法), idempotent re-run re-verifies,
partial-failure states can never ground evidence (26/26 PG suite).

24B Governance:
PASS — R2 extended (SOURCE_NOT_ACTIVE:<state>), R2b VERSION_AMBIGUOUS
(metadata-driven currency; never version-string ordering), three
distinct hash anchors (chunk/version/document), scope isolation
(GLOBAL_ONLY documented, enforced, tested).

24C WeKnora:
PASS — strict modes require the real provider (HG-24-03, checked
before construction with the policy reason); every provider failure
raises ProviderError (no fallback path exists); health = reachability
only; restart persistence verified; F-24 closed via canonical
re-anchoring.

24D F-16:
PASS — NOT REPRODUCIBLE (the claim does not match the engines, past
or present: R4→life exists since the original commit). Full §35
matrix frozen as regression (47/47); LIMITATIONS.md corrected with a
dated closure addendum. No business logic needed changing.

24E Evaluation:
PASS — dual-mode (mock vs live) decision-level agreement; governance
DENY matrix on real retrieval (expired/future/license/authority/
jurisdiction/unregistered + hash/chunk/registry mutations); N=24 live
retrievals: min 170 / median 218 / p95 306 / max 340 ms; evidence
completeness 1.0; abstention verified. Report:
tmp/p24_live_eval_report.json (NOT committed — contains query text
only, no secrets).

Knowledge Tests:
```
tests/runtime/test_p24_governance.py    45/45  (pure unit)
tests/runtime/test_p24_f16_routing.py   47/47  (pure unit)
tests/runtime/test_p24_registry_pg.py   26/26  (real PostgreSQL)
tests/runtime/test_p24_live_eval.py     33/33  (real WeKnora + PG, env-gated)
```

Mutation Tests:
chunk content tamper at rest → CHUNK_TAMPERED (selfcheck); version
hash corruption → VERSION_HASH_MISMATCH; projection drift →
PROJECTION_DRIFT; registration mutations (window/license/jurisdiction)
→ governance DENY with the matching rule id; authority-claim tamper →
AUTHORITY_CONFLICT. All in the PG + live suites above.

Runtime Regression:
```
Runtime:     494 passed  (474 pre-existing + 20 new p24)
Portfolio:   12 passed
Benchmark:   42/42
Compileall:  PASS
p14/p18/p22 knowledge + persistence suites: PASS (no regression)
```

Live WeKnora: 33/33 (full chain incl. provenance, F-24 proof,
DENY matrix, failure injection, latency N≥20, health).

P0: 0
P1: 0
P2: F-09, F-18, F-29 (3)
P3: F-14, F-15, F-17 (3)

F-09:  DEFERRED — Risk artifact evidence_refs is an artifact-contract
       change (schema+engine+evals), orthogonal to knowledge
       productionization; knowledge-side grounding complete.
F-14:  DOCUMENTED — inherent to LLM dialogue; 5-state model is the guard.
F-15:  DEFERRED — gap structured fallback = schema change.
F-16:  CLOSED (NOT REPRODUCIBLE) — chain verified R4→life→TERM_LIFE;
       §35 matrix frozen (47/47); LIMITATIONS corrected.
F-17:  DEFERRED — conflict persistence = schema change.
F-18:  DEFERRED — event hash chain = new infrastructure (scope-controlled).
F-24:  CLOSED — root cause characterized live (window-over-document,
       identity always correct); canonical re-anchoring implemented and
       proven on the 78-chunk regulation; unalignable windows still
       fail closed.
F-29:  DEFERRED — pricing registry (cost=UNKNOWN is honest).

Hard Gates:
```
HG-24-01 PostgreSQL authoritative (strict modes)         PASS (22B, re-verified)
HG-24-02 Registry uses authoritative persistence          PASS (resolve_registry_backend refuses JSON/file in strict)
HG-24-03 No silent Mock fallback in strict modes          PASS (name checked pre-construction, HG-24-03 in message)
HG-24-04 WeKnora Ask/ReAct absent from primary path       PASS (provider surface = search only; grep-audit clean)
HG-24-05 Authority conflicts fail closed                 PASS (AUTHORITY_CONFLICT, live-tested on a real hit)
HG-24-06 License UNKNOWN fails closed                    PASS (LICENSE_UNKNOWN, live case)
HG-24-07 Expired knowledge fails closed                  PASS (WINDOW_EXPIRED, live case)
HG-24-08 Unknown version fails closed                    PASS (VERSION_CONFLICT, R3 unchanged)
HG-24-09 Unknown document fails closed                   PASS (REGISTRY_MISS, live case)
HG-24-10 Unknown chunk fails closed                      PASS (CHUNK_UNREGISTERED, R8 unchanged)
HG-24-11 Hash mismatch fails closed                      PASS (HASH_MISMATCH; unaligned windows)
HG-24-12 Jurisdiction conflict fails closed              PASS (JURISDICTION_MISMATCH, live case)
HG-24-13 F-24 canonical chunk identity verified           PASS (hit.id→registry; re-anchoring; live A/B proof)
HG-24-14 Knowledge lineage complete                      PASS (P001–P010 per live evidence item)
HG-24-15 Partial ingestion cannot become ACTIVE           PASS (§17 case A/B/B2 in PG suite)
HG-24-16 Ingestion idempotent                            PASS (16/16 re-verified on rerun; drift refused)
HG-24-17 Restart preserves active knowledge state         PASS (fresh store reads same state+hash; WeKnora container restart verified)
HG-24-18 Real WeKnora retrieval works                    PASS (33/33 live suite)
HG-24-19 Provider failures fail closed                   PASS (refused/timeout/401/403/500/wrong-endpoint/malformed)
HG-24-20 F-16 routing correct                            PASS (47/47 matrix)
HG-24-21 F-16 changes no Recommendation contract         PASS (zero business-logic changes; tests only)
HG-24-22 No new Business Skill                           PASS (none added)
HG-24-23 No Redis/Queue/Worker                           PASS (none)
HG-24-24 No Kubernetes/Cloud                             PASS (none)
HG-24-25 No LLM Gateway contract change                  PASS (runtime/llm untouched)
HG-24-26 No Evidence/Provenance bypass                   PASS (governance still mandatory; K002 tests green)
HG-24-27 Tenant/global isolation explicit                PASS (scope column; GLOBAL_ONLY documented + tested)
HG-24-28 Mutation tests pass                             PASS (chunk/version/projection/registration mutations)
HG-24-29 Full regression passes                          PASS (494/12/42)
HG-24-30 Compileall passes                               PASS
HG-24-31 Documentation matches implementation            PASS (2 new docs, 4 updated, schema doc current)
HG-24-32 All claims evidence-backed                      PASS (every claim above cites a suite or live artifact)
HG-24-33 No hidden P0/P1 introduced                      PASS (audit grep clean; no new findings)

33/33
```

REAL:
```
WeKnora v0.8.0 live HTTP retrieval · restart persistence verified
Real insurance knowledge pilot (10 regulations/laws, canonical-chunk registered)
PostgreSQL governance registry (lifecycle, hashes, canonical contents)
Governance R1..R9+R2b · Evidence citation tuple · Provenance P001–P010
Strict-mode fail-closed composition (provider + registry + persistence)
Ingestion pipeline with guarded lifecycle + at-rest integrity selfcheck
Real GLM via the Phase 23 gateway (unchanged this phase)
Latency: N=24 live knowledge path, median 218 ms / p95 306 ms
```

MOCK:
```
MockKnowledgeProvider (offline tests, deterministic)
JSON projection registries (non-strict legacy path)
Synthetic fixtures corpus · demo product catalog · demo scenarios
```

NOT_IMPLEMENTED:
```
Redis / Queue / Workers / Kubernetes / Cloud / WeKnora HA
Multi-provider LLM routing · automated key rotation
Scheduled (automated) backups · tenant-scoped knowledge content
LLM response caching · distributed rate limiting
```

NOT_MEASURABLE:
```
Production-scale SLA (single host, no production load)
Production token cost (pricing registry deferred — F-29)
Concurrent throughput (no load test)
```

DEFERRED:
```
F-09 (risk evidence_refs contract) · F-15 (gap fallback schema)
F-17 (conflict persistence) · F-18 (event hash chain)
F-29 (pricing registry) · backup scheduling · WeKnora HA (P26+)
```

Remaining Technical Debt:
3×P2 (F-09, F-18, F-29) + 3×P3 (F-14, F-15, F-17) — none blocking;
all documented in docs/portfolio/LIMITATIONS.md.

Independent Audit (§50, post-implementation):
diff walked file-by-file; grep sweep for fallback/mock/knowledge-chat/
ReAct/TODO/FIXME/bypass over every changed file — only docstrings that
state the ABSENCE of a fallback; no historical audit documents modified
(PHASE_19_FINAL_AUDIT.md untouched); no secrets in source, tests,
fixtures, docs or logs (credentials live in session files outside the
repository; audit events carry metadata only).

Final Status:

```
PRODUCTION_KNOWLEDGE_READY_WITH_DOCUMENTED_DEBT
```

STOP — no Phase 25 without explicit human instruction.
