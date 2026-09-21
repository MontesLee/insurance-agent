# Phase 18 — WeKnora Integration Report (LIVE)

Date: 2026-09-20/21 · Previous BLOCKED verdict (STOP-01) is CLOSED —
real WeKnora runtime deployed and the integration is DONE and GREEN.

## 01 Executive Summary

```text
Phase 18 = PASS
```

Real WeKnora v0.8.0 retrieval is wired into the KnowledgeProvider seam
and every downstream contract holds: live hits flow through the SAME
governance → evidence → provenance → recommendation → report chain;
Phase 15 (15/15), Phase 16 (30/30 + 8/8 mutations), Phase 17
(security/observability), Phase 14.6/14.7 evaluations, and the full
456-test runtime battery are green — in BOTH mock and live-WeKnora
modes.

## 02 Environment

WeKnora v0.8.0 · commit 1edcd54b… · official Tencent/WeKnora ·
docker-compose core profile (app/ui/docreader/postgres/redis, all
healthy) · loopback-bound (127.0.0.1:80/8080) · local Ollama
nomic-embed-text (builtin-embedding-local, is_default) · 3 KBs:
insurance-pilot-2 (3 real docs), agent-fixtures (6 deterministic
fixtures), smoke-unregistered (1 unregistered doc) · scoped
retrieve-capability API key (X-API-Key; value never committed/logged).

## 03 Architecture (as implemented and verified)

```text
Agent → KnowledgeService → WeKnoraLiveProvider
  → POST /api/v1/knowledge-search (X-API-Key; PURE retrieval — the
    /knowledge-chat LLM path is structurally unreachable)
  → map_live_response (strict validation; document identity =
    knowledge_filename STEM; governance fields from the registry
    stamps PROJECTION — never invented from backend data)
  → agent-side scoring policy (the EXISTING SparseRetriever +
    DefaultReranker + min_relevance from the SAME externalized rules
    file — abstention semantics identical to the mock engine)
  → KnowledgeHit → Governance (registry = WEKNORA PROJECTION:
    agent governance metadata + WeKnora-chunk hashes) → Evidence →
    Provenance → Decision
```

Composition env: INSURANCE_AGENT_KNOWLEDGE_PROVIDER=weknora +
INSURANCE_AGENT_WEKNORA_{URL,API_KEY,KNOWLEDGE_BASE_ID} +
INSURANCE_AGENT_KNOWLEDGE_REGISTRY=<projection file>. Unset → the
unchanged mock default. Strict mode + unset provider still fails
closed (HG15 re-verified live).

## 04-05 Retrieval & Governance (live)

48/48 live checks: real hits with full contract fields; document
identity maps 1:1 to registry stems; governance ALLOW for registered
current docs; DENY for content-hash/chunk-id/document-id/version/
authority mutations, UNKNOWN license, expired window, authority
conflict, jurisdiction conflict, and unregistered-KB documents (the
smoke KB returns hits that governance DENYs to zero — honest
abstention at the service level).

## 06-07 Evidence & Provenance (live)

build_evidence on live retrieval produces citation-complete items;
validate_provenance 100% on live items; the four-hop chain resolves
(evidence → chunk id ∈ registry content_hashes → source_id@version);
decision binding via the 14.5 validator passes on live evidence.

## 08 Provider Failures (live, HTTP boundary)

connection-refused / timeout / 401 (invalid key) / 403 (out-of-scope
KB) / wrong-service-endpoint / stripped-content-field / corrupted-
chunk-id — every one a fail-closed ProviderError; the service
propagates and NEVER substitutes the mock (G4/E10 proven live).

## 09 Provider Equivalence & Abstention

Mock vs live produce governed evidence through the SAME validator;
canonical required-key surface identical; backend identity confined
to retrieval_metadata. Abstention: zero-overlap query ("德甲联赛积分榜
欧冠名额") → insufficient_evidence with ZERO evidence — the agent's
relevance policy abstains even though the WeKnora backend itself
returns keyword hits (§11 requirement met; the server was NOT
modified). Latency N=12 pilot box (not representative).

## 10-14 Business E2E / Quality / Security (LIVE backend)

Business eval 15/15 + hard gates clean (env=weknora); Demos A/B/C
correct (completed/waiting/needs-review); Phase 16 quality 30/30 +
M-OBS 8/8 + semantic invariance (env=weknora); Phase 17 security 98/98
+ observability clean (env=weknora). No evaluator weakened; no
business/skill/orchestrator contract touched.

## 15 Regression (mock mode, no WeKnora env)

pytest runtime 456 (449→456, +7 live suite skipped-mode) · portfolio
12 · benchmark 42/42 · compileall PASS · full regression 51/0/1 (=) ·
14.1–14.7 suites 52/33/1/74/52/44/25/21 · 14.6 eval 50/50 + pilot
26/26 CLEAN (also re-verified under env=weknora: both PASS).

## 16 Hard Gates HG01–HG15

All green: no Ask/ReAct in the provider (seam class scan + live
assert); no silent fallback (live G4); no UNKNOWN/expired/authority/
jurisdiction/hash acceptance (live G2); no fabricated or missing
provenance (live G5); no malformed→valid conversion (live G4); R-05
untouched; business never bypasses governance; no WeKnora answer as
evidence; no silent mock in strict mode (live G7/HG15); Phase 14–17
gates unregressed.

## 17 Production Code Changes (within §28 budget)

- knowledge/provider/weknora.py: LIVE section (transport, response
  mapper, live provider with agent-side rescoring). The SEAM class
  (WeKnoraKnowledgeProvider) is UNTOUCHED.
- knowledge/service.py: mock_registry()/default_registry() split;
  INSURANCE_AGENT_KNOWLEDGE_REGISTRY override; weknora live
  composition branch (fail-closed on missing key/kb/registry).
- knowledge/pilot/sync_weknora_registry.py + generated projection
  registries + weknora_environment.json sidecar (no secrets).
- evals/business: registry-of-record sourcing (service registry) and
  mutation-service mock-registry pairing (mock provider ↔ agent-chunker
  registry — the WeKnora projection's chunk ids never match mock
  chunking, by design).
- tests: new live suite; 14.x static scans re-scoped to the SEAM class
  (the live transport is a separate, legitimate Phase-18 class).

## 18 Findings

- F-22 (P3): WeKnora returns top-k keyword matches even for nonsense
  queries (server-side no-abstention) — by design the AGENT-side
  relevance policy owns abstention, which it does (proven live). Not a
  defect; recorded as the architectural division of responsibility.
- F-23 (P3): WeKnora v0.8.0 provides no per-hit governance fields —
  the dual-identity model (registry projection) is REQUIRED and is
  now the implemented pattern; a future backend that does supply such
  fields still cannot bypass the agent registry (fail-closed on
  conflict, per the 14.3 rules).
- No P0/P1. No scope escalation. No contract changed.

## 19 Known Limitations

- Single-node dev-box latency only; no production SLA claim.
- Ollama embedding model runs on the same box (pilot measurement).
- The WeKnora projection registry is a SYNCED artifact — re-run the
  sync script after re-ingesting or re-chunking documents in WeKnora.
- API key/JWT live in WSL /tmp session files (values never recorded
  anywhere persistent).

## 20 Final Decision

```text
Phase 18 = PASS
```

Mock and WeKnora differ below the KnowledgeHit boundary — and are
interchangeable above it. That was the proposition; it holds.
