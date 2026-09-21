# Knowledge Governance — Phase 24B (as implemented)

Deterministic, provider-independent validation of every KnowledgeHit
against the agent-side registry. No LLM, no scores, no provider
identity in any rule. Code: `knowledge/governance/governance.py`.

```
KnowledgeHit ──► validate_hit(hit, ctx, registry)
                   │ R1..R9 (+R2b)
                   ▼
              GovernanceDecision ──► build_evidence_item()
                                        │ full citation tuple
                                        ▼
                                   Evidence ──► provenance P001–P010
```

## Rules (all fail closed; reasons are machine-readable ids)

| Rule | Checks | Deny reason |
|---|---|---|
| R1 | document registered in the agent registry | `REGISTRY_MISS:<doc>` |
| R2 | registration lifecycle is ACTIVE | `SOURCE_RETIRED` / `SOURCE_NOT_ACTIVE:<state>` (uploaded ≠ ACTIVE) |
| R2b | version currency unambiguous at as_of | `VERSION_AMBIGUOUS` |
| R3 | hit version identity matches the registry entry | `VERSION_MISSING` / `VERSION_CONFLICT` |
| R4 | claimed authority matches the registry | `AUTHORITY_MISSING` / `AUTHORITY_CONFLICT` |
| R5 | effective window covers as_of | `WINDOW_FUTURE` / `WINDOW_EXPIRED` / `WINDOW_UNRESOLVED` |
| R6 | jurisdiction governs the query scope | `JURISDICTION_MISMATCH` |
| R7 | license allows production use | `LICENSE_UNKNOWN` / `LICENSE_RESTRICTED` |
| R8 | chunk registered AND content hash matches the anchor | `HASH_MISSING` / `CHUNK_UNREGISTERED` / `HASH_MISMATCH` |
| R9 | content present | `CONTENT_EMPTY` |

Authority hierarchy: `S > A > B > C > D` (registry `authority_level`);
authority is NEVER derived from retrieval scores. The provider's
claimed authority is a PROJECTION the governance re-verifies — if the
backend claims X and the registry says Y, the hit is denied
(HG-24-05).

## Provider boundary (Phase 24C)

- `KnowledgeService` is the ONLY runtime composition (K001–K004).
- STRICT modes (CONTROLLED_PILOT/PRODUCTION) require the real WeKnora
  provider; mock knowledge is refused at construction with the
  HG-24-03 policy reason — no silent fallback exists anywhere.
- Provider failures (connection refused, timeout, 401/403/5xx, wrong
  endpoint, malformed JSON, missing fields) raise ProviderError
  subclasses — never an empty success, never a mock fallback.
- `WeKnoraLiveTransport.health()` is REACHABILITY only: any HTTP
  answer (including 401) proves the service is up; correctness is the
  governance/evidence/provenance path's job. It validates nothing
  about retrieval semantics.
- The WeKnora Ask/ReAct/`knowledge-chat` LLM path is structurally
  unreachable: the provider exposes only the pure-search endpoint
  (`/api/v1/knowledge-search`); verified by the p18/p24 live suites.

## Evidence & provenance

Every allowed hit becomes an evidence item carrying the FULL citation
tuple (source_id, source_name, version_id, version, effective window,
authority, jurisdiction, license, canonical_uri, content_hash,
retrieved_at) plus the governance block (as_of, window status, checked
rules). Provenance (P001–P010) re-derives every hop against the
registry: identity, hit locatability, document resolution, version,
source, governance consistency, hash, jurisdiction, license,
retrieval timestamp. Tamper any byte → hash mismatch → DENY.

## Mode matrix (knowledge path)

| Mode | Provider | Registry | Persistence |
|---|---|---|---|
| DEMO | mock (default) | JSON | JSON |
| EVALUATION | mock (default) | JSON | JSON |
| CONTROLLED_PILOT | real WeKnora REQUIRED | PostgreSQL REQUIRED | PostgreSQL REQUIRED |
| PRODUCTION | real WeKnora REQUIRED | PostgreSQL REQUIRED | PostgreSQL REQUIRED |

In strict modes: WeKnora/PG unavailable or unconfigured → startup
fails. There is no fallback code path (verified by grep-audit and the
mutation tests in tests/runtime/test_p24_*).
